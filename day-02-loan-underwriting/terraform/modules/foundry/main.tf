resource "azurerm_storage_account" "hub" {
  name                     = replace("st${var.hub_name}", "-", "")
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = var.is_production ? "GRS" : "LRS"
  tags                     = var.tags
}

resource "azurerm_application_insights" "hub" {
  name                = "${var.hub_name}-appi"
  resource_group_name = var.resource_group_name
  location            = var.location
  application_type    = "web"
  tags                = var.tags
}

resource "azurerm_machine_learning_workspace" "hub" {
  name                          = var.hub_name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  tags                          = var.tags
  kind                          = "Hub"
  key_vault_id                  = var.key_vault_id
  storage_account_id            = azurerm_storage_account.hub.id
  application_insights_id       = azurerm_application_insights.hub.id
  sku_name                      = "Basic"
  public_network_access_enabled = !var.is_production

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_machine_learning_workspace" "project" {
  name                    = var.project_name
  resource_group_name     = var.resource_group_name
  location                = var.location
  tags                    = var.tags
  kind                    = "Project"
  sku_name                = "Basic"
  hub_id                  = azurerm_machine_learning_workspace.hub.id
  storage_account_id      = azurerm_storage_account.hub.id
  application_insights_id = azurerm_application_insights.hub.id
  key_vault_id            = var.key_vault_id

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_role_assignment" "project_openai" {
  scope                = var.openai_id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_machine_learning_workspace.project.identity[0].principal_id
}
