terraform {
  required_version = ">= 1.7"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "4.81.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }

  # Configure via `terraform init -backend-config=...` or set your own backend.
  backend "azurerm" {
    resource_group_name  = "rg-tfstate-kyc"
    storage_account_name = "stkycamltfstate"
    container_name       = "tfstate"
    key                  = "kyc-aml.tfstate"
  }
}

provider "azurerm" {
  # azurerm 4.x requires the subscription explicitly. Supply via ARM_SUBSCRIPTION_ID
  # env var (CI / local az login) — never hard-code it here.
  subscription_id = var.subscription_id

  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    cognitive_account {
      purge_soft_delete_on_destroy = false
    }
  }
}

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.prefix}"
  location = var.location
  tags     = local.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

module "keyvault" {
  source              = "./modules/keyvault"
  name                = "kv-${substr(replace(local.prefix, "-", ""), 0, 21)}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  admin_object_id     = var.admin_object_id
  # The principal executing this apply (CI service principal or local user) —
  # granted Secrets Officer so it can write the secrets below into the RBAC vault.
  deployer_object_id = data.azurerm_client_config.current.object_id
  tenant_id          = data.azurerm_client_config.current.tenant_id
  is_production      = local.is_production
}

# ─── Azure AI Document Intelligence — OCR for scanned IDs / PDFs (the core ask) ───
module "doc_intelligence" {
  source              = "./modules/doc_intelligence"
  account_name        = "di-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  key_vault_id        = module.keyvault.secrets_key_vault_id
  is_production       = local.is_production
  sku_name            = var.doc_intelligence_sku
}

# ─── Azure AI Search — vector DB for the regulatory KB ───
module "search" {
  source              = "./modules/search"
  name                = "srch-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  key_vault_id        = module.keyvault.secrets_key_vault_id
  is_production       = local.is_production
  sku                 = var.search_sku
}

# ─── Azure AI Foundry (FDP) — one AIServices account that hosts the models AND
# contains the project. Replaces the old split of a standalone Azure OpenAI resource
# + a classic AI Foundry hub + a backing storage account. GPT-4o + embeddings are
# deployed ON this account, so no cross-resource connection is needed. ───
module "foundry" {
  source              = "./modules/foundry"
  account_name        = "aif-${local.prefix}"
  project_name        = "proj-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  key_vault_id        = module.keyvault.secrets_key_vault_id
  is_production       = local.is_production
}

# ─── Azure Container Registry — holds the KYC/AML runtime image ───
# The deploy workflow pushes the built image here; the Container App pulls it
# keyless via its managed identity (AcrPull below). No admin credentials.
module "acr" {
  source              = "./modules/acr"
  name                = "acr${substr(replace(local.prefix, "-", ""), 0, 47)}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  is_production       = local.is_production
}

# ─── Azure Container Apps — runs the FastAPI KYC/AML service ───
# Provisioned as a shell (placeholder image); the deploy workflow sets the real
# image + env + Neo4j KV-reference secrets via `az containerapp` after the role
# assignments below propagate. See modules/containerapp for the ordering rationale.
module "containerapp" {
  source              = "./modules/containerapp"
  env_name            = "cae-${local.prefix}"
  app_name            = "ca-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  is_production       = local.is_production
}

# ─── Role assignments — the app's managed identity authenticates keyless to every
# back-end. Grants live on the CONTAINER APP's identity because the app is the
# runtime caller: embeddings.py, vector_store.py and ocr.py all use
# DefaultAzureCredential from inside the container, and llm.py drives the Foundry
# Agents SDK against the project endpoint. ───

# Pull the private image from ACR.
resource "azurerm_role_assignment" "ca_to_acr" {
  scope                = module.acr.id
  role_definition_name = "AcrPull"
  principal_id         = module.containerapp.principal_id
}

# Read the Neo4j URI/password Key Vault references (the only non-AAD dependency).
resource "azurerm_role_assignment" "ca_to_kv" {
  scope                = module.keyvault.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = module.containerapp.principal_id
}

# Embeddings — the AzureOpenAI client hits the account's OpenAI endpoint
# (…cognitiveservices.azure.com) with the cognitiveservices token scope.
resource "azurerm_role_assignment" "ca_to_foundry_openai" {
  scope                = module.foundry.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = module.containerapp.principal_id
}

# Chat/reasoning — the Agents SDK creates and runs agents against the Foundry
# PROJECT endpoint. "Azure AI User" (a.k.a. Foundry User) is the data-plane role
# for creating and interacting with agents. Pinned by GUID because the role was
# renamed (Azure AI User → Foundry User) and the display name is mid-rollout.
resource "azurerm_role_assignment" "ca_to_foundry_agents" {
  scope              = module.foundry.id
  role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/53ca6127-db72-4b80-b1b0-d745d6d5456d"
  principal_id       = module.containerapp.principal_id
}

# Search — hybrid retrieval reads/writes documents in the regulatory-KB index (data plane).
resource "azurerm_role_assignment" "ca_to_search" {
  scope                = module.search.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = module.containerapp.principal_id
}

# Search (control plane) — the app CREATES the KB index at startup (ensure_index).
# Data Contributor only covers documents; creating/updating an index definition
# needs Search Service Contributor.
resource "azurerm_role_assignment" "ca_to_search_service" {
  scope                = module.search.id
  role_definition_name = "Search Service Contributor"
  principal_id         = module.containerapp.principal_id
}

# Document Intelligence — OCR for scanned IDs/PDFs via Azure AD.
resource "azurerm_role_assignment" "ca_to_docintel" {
  scope                = module.doc_intelligence.id
  role_definition_name = "Cognitive Services User"
  principal_id         = module.containerapp.principal_id
}

# ─── Neo4j Aura (knowledge graph) is a managed SaaS provisioned outside Terraform.
# We only store its connection secrets in Key Vault so the app reads them uniformly.
resource "azurerm_key_vault_secret" "neo4j_uri" {
  count        = var.neo4j_uri == "" ? 0 : 1
  name         = "neo4j-uri"
  value        = var.neo4j_uri
  key_vault_id = module.keyvault.secrets_key_vault_id
  content_type = "endpoint-url"
}

resource "azurerm_key_vault_secret" "neo4j_password" {
  count        = var.neo4j_password == "" ? 0 : 1
  name         = "neo4j-password"
  value        = var.neo4j_password
  key_vault_id = module.keyvault.secrets_key_vault_id
  content_type = "password"
}
