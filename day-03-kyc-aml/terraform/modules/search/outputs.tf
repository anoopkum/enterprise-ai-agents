output "endpoint" { value = "https://${azurerm_search_service.search.name}.search.windows.net" }
output "id" { value = azurerm_search_service.search.id }
output "name" { value = azurerm_search_service.search.name }
output "principal_id" { value = azurerm_search_service.search.identity[0].principal_id }
