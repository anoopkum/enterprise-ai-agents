terraform {
  required_version = ">= 1.7"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "4.81.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
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

# Suffix for globally-unique names (storage account).
resource "random_string" "suffix" {
  length  = 6
  lower   = true
  upper   = false
  numeric = true
  special = false
}

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
  tenant_id           = data.azurerm_client_config.current.tenant_id
  is_production       = local.is_production
}

# ─── Azure AI Document Intelligence — OCR for scanned IDs / PDFs (the core ask) ───
module "doc_intelligence" {
  source              = "./modules/doc_intelligence"
  account_name        = "di-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  key_vault_id        = module.keyvault.id
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
  key_vault_id        = module.keyvault.id
  is_production       = local.is_production
  sku                 = var.search_sku
}

# ─── Azure OpenAI — GPT-4.1 + text-embedding-3-large ───
module "openai" {
  source              = "./modules/openai"
  account_name        = "oai-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  key_vault_id        = module.keyvault.id
  is_production       = local.is_production
}

# ─── Azure AI Foundry — Hub + Project (central AI workspace for the KYC agent) ───
# The hub owns a storage account + Key Vault; the project scopes the agent, model
# deployments, and connections to Search / OpenAI / Document Intelligence.
module "ai_foundry" {
  source              = "./modules/ai_foundry"
  name                = "aih-${local.prefix}"
  project_name        = "proj-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  key_vault_id        = module.keyvault.id
  is_production       = local.is_production

  # Storage account: 3-24 lowercase alphanumeric, globally unique.
  storage_account_name = substr("st${replace(local.prefix, "-", "")}${random_string.suffix.result}", 0, 24)
}

# ─── Grant the Foundry hub identity access to the AI back-ends (keyless auth) ───
# The hub's system-assigned identity calls OpenAI, Document Intelligence, and Search
# via Azure AD instead of stored keys — the managed-identity path the app uses in prod.
resource "azurerm_role_assignment" "foundry_to_openai" {
  scope                = module.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = module.ai_foundry.hub_principal_id
}

resource "azurerm_role_assignment" "foundry_to_docintel" {
  scope                = module.doc_intelligence.id
  role_definition_name = "Cognitive Services User"
  principal_id         = module.ai_foundry.hub_principal_id
}

resource "azurerm_role_assignment" "foundry_to_search" {
  scope                = module.search.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = module.ai_foundry.hub_principal_id
}

# ─── Neo4j Aura (knowledge graph) is a managed SaaS provisioned outside Terraform.
# We only store its connection secrets in Key Vault so the app reads them uniformly.
resource "azurerm_key_vault_secret" "neo4j_uri" {
  count        = var.neo4j_uri == "" ? 0 : 1
  name         = "neo4j-uri"
  value        = var.neo4j_uri
  key_vault_id = module.keyvault.id
}

resource "azurerm_key_vault_secret" "neo4j_password" {
  count        = var.neo4j_password == "" ? 0 : 1
  name         = "neo4j-password"
  value        = var.neo4j_password
  key_vault_id = module.keyvault.id
}
