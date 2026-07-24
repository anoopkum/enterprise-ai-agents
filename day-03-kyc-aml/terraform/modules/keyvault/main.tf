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

# The principal actually running `terraform apply` (the CI service principal, or a
# local user) must have data-plane write access to store secrets. This is an
# RBAC-authorization vault, so that means a role assignment — not an access
# policy — and `admin_object_id` (the human operator) is not necessarily the
# deploying principal. Scoped to Secrets Officer: least privilege for writing
# secrets, without the full-vault reach of Administrator.
resource "azurerm_role_assignment" "kv_deployer_secrets" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = var.deployer_object_id
}

# RBAC assignments take time to propagate to the data plane; writing a secret in
# the same apply that creates the grant races that propagation and 403s. Pause
# after the grants so the first secret write sees the permission. The vault id is
# carried through as a trigger and re-exported (secrets_key_vault_id) so secret
# writers get a real data dependency on the elapsed wait — while control-plane
# consumers (e.g. the AI Foundry hub) keep using the ungated `id` and create in
# parallel.
resource "time_sleep" "kv_rbac_propagation" {
  depends_on      = [azurerm_role_assignment.kv_deployer_secrets, azurerm_role_assignment.kv_admin]
  create_duration = "120s"

  triggers = {
    kv_id = azurerm_key_vault.kv.id
  }
}
