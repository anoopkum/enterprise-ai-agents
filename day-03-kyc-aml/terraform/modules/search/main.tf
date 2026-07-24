# Azure AI Search — vector DB for the regulatory KB (hybrid BM25 + vector,
# semantic reranker). The index itself is created by the app at ingestion time.
resource "azurerm_search_service" "search" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku
  tags                = var.tags

  # Semantic reranker (free tier allows a small quota; standard for prod).
  semantic_search_sku = var.is_production ? "standard" : "free"

  # Managed identity so the app authenticates without keys in prod.
  local_authentication_enabled = !var.is_production
  authentication_failure_mode  = "http403"

  identity {
    type = "SystemAssigned"
  }

  public_network_access_enabled = !var.is_production

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_key_vault_secret" "search_endpoint" {
  name         = "azure-search-endpoint"
  value        = "https://${azurerm_search_service.search.name}.search.windows.net"
  key_vault_id = var.key_vault_id
  content_type = "endpoint-url"
}

resource "azurerm_key_vault_secret" "search_key" {
  name         = "azure-search-admin-key"
  value        = azurerm_search_service.search.primary_key
  key_vault_id = var.key_vault_id
  content_type = "api-key"
}
