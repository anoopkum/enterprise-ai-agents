resource "azurerm_key_vault" "kv" { #checkov:skip=CKV_AZURE_109:Private endpoint requires VNet integration outside scope of this sandbox #checkov:skip=CKV2_AZURE_32:Private endpoint requires VNet integration outside scope of this sandbox
  name                          = var.name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  tenant_id                     = var.tenant_id
  sku_name                      = "standard"
  tags                          = var.tags
  rbac_authorization_enabled    = true
  soft_delete_retention_days    = var.is_production ? 90 : 7
  purge_protection_enabled      = true
  public_network_access_enabled = !var.is_production

  network_acls {
    default_action = var.is_production ? "Deny" : "Allow"
    bypass         = "AzureServices"
    ip_rules       = []
  }

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_role_assignment" "kv_admin" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = var.admin_object_id
}
