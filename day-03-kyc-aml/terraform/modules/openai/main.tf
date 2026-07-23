# Azure OpenAI — GPT-4.1 (reasoning, vision-enabled) + text-embedding-3-large.
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

  # Managed identity so the account can be reached keyless via Azure AD.
  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_cognitive_deployment" "gpt41" {
  name                 = var.chat_deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "gpt-4.1"
    version = var.gpt41_version
  }

  # azurerm 4.x: the `scale` block was replaced by a `sku` block.
  sku {
    name     = "Standard"
    capacity = var.is_production ? 100 : 30
  }
}

resource "azurerm_cognitive_deployment" "embeddings" {
  name                 = var.embed_deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "text-embedding-3-large"
    version = var.embed_version
  }

  sku {
    name     = "Standard"
    capacity = var.is_production ? 120 : 50
  }

  # Deploy models one at a time — the account serialises deployment operations.
  depends_on = [azurerm_cognitive_deployment.gpt41]
}

resource "azurerm_key_vault_secret" "openai_key" {
  name         = "azure-openai-api-key"
  value        = azurerm_cognitive_account.openai.primary_access_key
  key_vault_id = var.key_vault_id
  content_type = "api-key"
}

resource "azurerm_key_vault_secret" "openai_endpoint" {
  name         = "azure-openai-endpoint"
  value        = azurerm_cognitive_account.openai.endpoint
  key_vault_id = var.key_vault_id
  content_type = "endpoint-url"
}
