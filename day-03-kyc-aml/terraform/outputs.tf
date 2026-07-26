output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "doc_intelligence_endpoint" {
  description = "Set DOC_INTELLIGENCE_ENDPOINT to this value."
  value       = module.doc_intelligence.endpoint
}

output "search_endpoint" {
  description = "Set AZURE_SEARCH_ENDPOINT to this value."
  value       = module.search.endpoint
}

output "azure_openai_endpoint" {
  description = "Set AZURE_OPENAI_ENDPOINT to this value (embeddings client)."
  value       = module.foundry.account_endpoint
}

output "ai_foundry_project_endpoint" {
  description = "Set AI_FOUNDRY_ENDPOINT to this value (Agents SDK)."
  value       = module.foundry.project_endpoint
}

output "openai_chat_deployment" {
  value = module.foundry.chat_deployment
}

output "openai_embed_deployment" {
  value = module.foundry.embed_deployment
}

output "key_vault_name" {
  value = module.keyvault.name
}

output "ai_foundry_account_name" {
  value = module.foundry.account_name
}

output "ai_foundry_project_name" {
  value = module.foundry.project_name
}

output "estimated_monthly_cost" {
  description = "Rough Azure spend; Neo4j Aura billed separately by Neo4j."
  value       = local.is_production ? "~$2,400/mo (Azure) + Aura Pro" : "~$450/mo (Azure) + Aura Free"
}
