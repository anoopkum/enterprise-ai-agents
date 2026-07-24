output "endpoint" { value = azurerm_cognitive_account.openai.endpoint }
output "id" { value = azurerm_cognitive_account.openai.id }
output "chat_deployment" { value = azurerm_cognitive_deployment.chat.name }
output "embed_deployment" { value = azurerm_cognitive_deployment.embeddings.name }
