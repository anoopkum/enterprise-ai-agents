output "url" { value = "https://${azurerm_container_app.app.ingress[0].fqdn}" }
output "fqdn" { value = azurerm_container_app.app.ingress[0].fqdn }
output "name" { value = azurerm_container_app.app.name }
output "principal_id" { value = azurerm_container_app.app.identity[0].principal_id }
