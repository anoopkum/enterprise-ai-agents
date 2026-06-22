resource "azurerm_container_registry" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.is_production ? "Premium" : "Basic"
  admin_enabled       = false
  tags                = var.tags

  dynamic "georeplications" {
    for_each = var.is_production ? [var.secondary_location] : []
    content {
      location                = georeplications.value
      zone_redundancy_enabled = true
    }
  }
}

resource "azurerm_role_assignment" "acr_pull" {
  for_each             = toset(var.pull_principal_ids)
  scope                = azurerm_container_registry.this.id
  role_definition_name = "AcrPull"
  principal_id         = each.value
}
