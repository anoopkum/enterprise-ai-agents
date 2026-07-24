output "id" { value = azurerm_key_vault.kv.id }
output "name" { value = azurerm_key_vault.kv.name }
output "uri" { value = azurerm_key_vault.kv.vault_uri }

# Same vault id, but only resolvable after the RBAC-propagation wait. Secret
# writers use THIS as their key_vault_id so their create waits for the grant;
# control-plane consumers keep using `id` and are not delayed.
output "secrets_key_vault_id" {
  description = "Key Vault id gated behind RBAC propagation — use as key_vault_id for secret writes."
  value       = time_sleep.kv_rbac_propagation.triggers["kv_id"]
}
