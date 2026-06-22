output "container_app_url" {
  description = "Container App HTTPS endpoint"
  value       = module.containerapp.url
}

output "ai_foundry_endpoint" {
  description = "Azure AI Foundry project endpoint"
  value       = module.foundry.endpoint
}

output "key_vault_name" {
  description = "Key Vault name"
  value       = module.keyvault.name
}

output "resource_group_name" {
  description = "Resource group name"
  value       = azurerm_resource_group.main.name
}

output "acr_login_server" {
  description = "ACR login server for docker push"
  value       = module.acr.login_server
}

output "estimated_monthly_cost" {
  description = "Rough monthly cost estimate"
  value       = local.is_production ? "~$2,800/mo" : (local.is_staging ? "~$950/mo" : "~$600/mo")
}
