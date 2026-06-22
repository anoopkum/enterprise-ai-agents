resource "azurerm_cognitive_account" "openai" {
  name                          = var.account_name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  kind                          = "OpenAI"
  sku_name                      = "S0"
  tags                          = var.tags
  custom_subdomain_name         = var.account_name
  public_network_access_enabled = !var.is_production

  network_acls {
    default_action = var.is_production ? "Deny" : "Allow"
  }
}

resource "azurerm_cognitive_deployment" "gpt4o" {
  name                 = "gpt-4o"
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-11-20"
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.is_production ? 100 : 30
  }
}

resource "azurerm_key_vault_secret" "openai_key" {
  name         = "azure-openai-api-key"
  value        = azurerm_cognitive_account.openai.primary_access_key
  key_vault_id = var.key_vault_id
}
