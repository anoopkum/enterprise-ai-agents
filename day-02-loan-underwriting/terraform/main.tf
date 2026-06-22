terraform {
  required_version = ">= 1.7"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.53"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-tfstate-loan"
    storage_account_name = "stloanunderwritingtf"
    container_name       = "tfstate"
    key                  = "loan-underwriting.tfstate"
  }
}

provider "azurerm" {
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
  name                = "kv-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  admin_object_id     = var.admin_object_id
  tenant_id           = data.azurerm_client_config.current.tenant_id
  is_production       = local.is_production
}

module "acr" {
  source              = "./modules/acr"
  name                = replace("acr${local.prefix}", "-", "")
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  is_production       = local.is_production
}

resource "azurerm_role_assignment" "ca_acr_pull" {
  scope                = module.acr.id
  role_definition_name = "AcrPull"
  principal_id         = module.containerapp.principal_id
}

module "openai" {
  source              = "./modules/openai"
  account_name        = "oai-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  key_vault_id        = module.keyvault.id
  is_production       = local.is_production
}

module "foundry" {
  source              = "./modules/foundry"
  hub_name            = "aihub-lu-${var.environment}"
  project_name        = "proj-lu-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  key_vault_id        = module.keyvault.id
  openai_id           = module.openai.id
  is_production       = local.is_production
}

module "monitoring" {
  source              = "./modules/monitoring"
  name                = "appi-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
  key_vault_id        = module.keyvault.id
  is_production       = local.is_production
}

import {
  to = module.containerapp.azurerm_container_app.app
  id = "/subscriptions/27320543-d2ea-4fd5-b361-0145cc56934b/resourceGroups/rg-loan-underwriting-dev/providers/Microsoft.App/containerApps/ca-loan-underwriting-dev"
}

module "containerapp" {
  source                = "./modules/containerapp"
  env_name              = "cae-${local.prefix}"
  app_name              = "ca-${local.prefix}"
  resource_group_name   = azurerm_resource_group.main.name
  location              = var.location
  tags                  = local.tags
  key_vault_id          = module.keyvault.id
  ai_foundry_endpoint   = module.foundry.endpoint
  app_insights_conn_str = module.monitoring.connection_string
  environment_name      = var.environment
  container_image       = var.container_image
  acr_login_server      = "${replace("acr${local.prefix}", "-", "")}.azurecr.io"
  is_production         = local.is_production

  depends_on = [module.keyvault, module.foundry, module.monitoring]
}

resource "azurerm_role_assignment" "ca_kv_secrets" {
  scope                = module.keyvault.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = module.containerapp.principal_id
}
