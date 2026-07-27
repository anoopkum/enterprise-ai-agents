# Account (OpenAI-compatible) endpoint — used by the AzureOpenAI embeddings client
# with the cognitiveservices token scope. Form: https://<subdomain>.cognitiveservices.azure.com/
output "account_endpoint" {
  value = azurerm_cognitive_account.foundry.endpoint
}

# Foundry PROJECT endpoint — used by the Agents SDK (AgentsClient). The azurerm
# project resource doesn't surface this, so it's constructed from the documented
# form: https://<resource>.services.ai.azure.com/api/projects/<project-name>
# (custom_subdomain_name == account_name).
output "project_endpoint" {
  value = "https://${var.account_name}.services.ai.azure.com/api/projects/${azurerm_cognitive_account_project.project.name}"
}

output "id" {
  value = azurerm_cognitive_account.foundry.id
}

output "account_name" {
  value = azurerm_cognitive_account.foundry.name
}

output "project_name" {
  value = azurerm_cognitive_account_project.project.name
}

output "chat_deployment" {
  value = azurerm_cognitive_deployment.chat.name
}

output "embed_deployment" {
  value = azurerm_cognitive_deployment.embeddings.name
}

# System-assigned identity of the Foundry account — grant it access to the
# external back-ends (Search / Document Intelligence) for keyless calls.
output "account_principal_id" {
  value = azurerm_cognitive_account.foundry.identity[0].principal_id
}
