output "hub_id" {
  value = azurerm_ai_foundry.hub.id
}

output "hub_name" {
  value = azurerm_ai_foundry.hub.name
}

output "hub_discovery_url" {
  value = azurerm_ai_foundry.hub.discovery_url
}

output "hub_principal_id" {
  description = "System-assigned identity of the hub — grant it access to Search / OpenAI / Document Intelligence."
  value       = azurerm_ai_foundry.hub.identity[0].principal_id
}

output "project_id" {
  value = azurerm_ai_foundry_project.project.id
}

output "project_name" {
  value = azurerm_ai_foundry_project.project.name
}

output "project_principal_id" {
  value = azurerm_ai_foundry_project.project.identity[0].principal_id
}

output "storage_account_id" {
  value = azurerm_storage_account.hub.id
}
