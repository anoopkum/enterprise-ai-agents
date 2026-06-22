resource "azurerm_container_registry" "acr" {
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

  lifecycle {
    ignore_changes = [tags]
  }
}
