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

# ─── Grant the Foundry account identity access to the external back-ends (keyless) ───
# The models live on the Foundry account itself, so no OpenAI role is needed here.
# Document Intelligence and Search are separate resources the agent calls via Azure AD.
resource "azurerm_role_assignment" "foundry_to_docintel" {
  scope                = module.doc_intelligence.id
  role_definition_name = "Cognitive Services User"
  principal_id         = module.foundry.account_principal_id
}

resource "azurerm_role_assignment" "foundry_to_search" {
  scope                = module.search.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = module.foundry.account_principal_id
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
