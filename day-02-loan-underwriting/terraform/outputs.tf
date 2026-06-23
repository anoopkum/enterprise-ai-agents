output "container_app_url" {
  value = module.containerapp.url
}

output "ai_foundry_endpoint" {
  value = var.ai_foundry_endpoint
}

output "key_vault_name" {
  value = module.keyvault.name
}

output "acr_login_server" {
  value = module.acr.login_server
}

output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "estimated_monthly_cost" {
  value = local.is_production ? "~$2,800/mo" : (local.is_staging ? "~$950/mo" : "~$600/mo")
}
