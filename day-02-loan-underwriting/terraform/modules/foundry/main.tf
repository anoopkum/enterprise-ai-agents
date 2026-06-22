resource "azurerm_storage_account" "aml" {
  name                     = replace("st${var.hub_name}", "-", "")
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = var.is_production ? "GRS" : "LRS"
  tags                     = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_application_insights" "aml" {
  name                       = "${var.hub_name}-appi"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  application_type           = "web"
  internet_ingestion_enabled = false
  internet_query_enabled     = false
  tags                       = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

# AzureRM 3.x: Hub/Project kind requires AzureRM 4.x — using standard workspace
resource "azurerm_machine_learning_workspace" "aml" {
  name                          = var.hub_name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  tags                          = var.tags
  key_vault_id                  = var.key_vault_id
  storage_account_id            = azurerm_storage_account.aml.id
  application_insights_id       = azurerm_application_insights.aml.id
  sku_name                      = "Basic"
  public_network_access_enabled = !var.is_production

  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_role_assignment" "workspace_openai" {
  scope                = var.openai_id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_machine_learning_workspace.aml.identity[0].principal_id
}
