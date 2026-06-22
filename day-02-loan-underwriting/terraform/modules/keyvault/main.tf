resource "azurerm_key_vault" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  tenant_id           = var.tenant_id
  sku_name            = "standard"
  tags                = var.tags

  enable_rbac_authorization   = true
  soft_delete_retention_days  = var.is_production ? 90 : 7
  purge_protection_enabled    = var.is_production

  network_acls {
    default_action = var.is_production ? "Deny" : "Allow"
    bypass         = "AzureServices"
  }
}

resource "azurerm_role_assignment" "admin" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = var.admin_object_id
}
