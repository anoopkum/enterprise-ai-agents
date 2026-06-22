output "url"          { value = "https://${azurerm_container_app.this.ingress[0].fqdn}" }
output "principal_id" { value = azurerm_container_app.this.identity[0].principal_id }
output "fqdn"         { value = azurerm_container_app.this.ingress[0].fqdn }
