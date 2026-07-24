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

output "openai_endpoint" {
  description = "Set AI_FOUNDRY_ENDPOINT to this value."
  value       = module.openai.endpoint
}

output "openai_chat_deployment" {
  value = module.openai.chat_deployment
}

output "openai_embed_deployment" {
  value = module.openai.embed_deployment
}

output "key_vault_name" {
  value = module.keyvault.name
}

output "ai_foundry_hub_name" {
  value = module.ai_foundry.hub_name
}

output "ai_foundry_project_name" {
  value = module.ai_foundry.project_name
}

output "ai_foundry_hub_discovery_url" {
  description = "Foundry hub discovery URL — set as AI_FOUNDRY_ENDPOINT / project connection."
  value       = module.ai_foundry.hub_discovery_url
}

output "estimated_monthly_cost" {
  description = "Rough Azure spend; Neo4j Aura billed separately by Neo4j."
  value       = local.is_production ? "~$2,400/mo (Azure) + Aura Pro" : "~$450/mo (Azure) + Aura Free"
}
