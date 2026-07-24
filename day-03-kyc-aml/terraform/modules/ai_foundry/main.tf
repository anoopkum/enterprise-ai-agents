# ─────────────────────────────────────────────────────────────────────────────
# Azure AI Foundry Hub + Project
#
# A Foundry hub is the collaboration/governance boundary (backed by a storage
# account + key vault); projects live under it and are where agents, deployments,
# and connections are scoped. The hub REQUIRES both a storage account and a key
# vault, so we create the storage account here and reuse the shared Key Vault.
# ─────────────────────────────────────────────────────────────────────────────

# Storage account that backs the hub (artifacts, prompt flows, uploaded data).
resource "azurerm_storage_account" "hub" {
  name                              = var.storage_account_name
  resource_group_name               = var.resource_group_name
  location                          = var.location
  account_tier                      = "Standard"
  account_replication_type          = var.is_production ? "GRS" : "LRS"
  account_kind                      = "StorageV2"
  min_tls_version                   = "TLS1_2"
  https_traffic_only_enabled        = true
  shared_access_key_enabled         = true
  allow_nested_items_to_be_public   = false
  public_network_access_enabled     = !var.is_production
  infrastructure_encryption_enabled = true
  tags                              = var.tags

  blob_properties {
    delete_retention_policy {
      days = var.is_production ? 30 : 7
    }
  }

  lifecycle {
    ignore_changes = [tags]
  }
}

# The Foundry hub. Identity is required (min 1 identity block) — SystemAssigned so
# the hub can reach its storage/key vault and downstream Cognitive/Search accounts.
resource "azurerm_ai_foundry" "hub" {
  name                = var.name
  location            = var.location
  resource_group_name = var.resource_group_name
  storage_account_id  = azurerm_storage_account.hub.id
  key_vault_id        = var.key_vault_id
  friendly_name       = var.friendly_name
  description         = "KYC/AML compliance automation — multi-format RAG + knowledge graph."

  public_network_access = var.is_production ? "Disabled" : "Enabled"

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

# A project scoped to the hub — where the KYC agent, model deployments, and
# service connections are organised.
resource "azurerm_ai_foundry_project" "project" {
  name               = var.project_name
  location           = azurerm_ai_foundry.hub.location
  ai_services_hub_id = azurerm_ai_foundry.hub.id
  friendly_name      = "KYC/AML Compliance Agent"
  description        = "Day 03 — KYC/AML compliance agent (GPT-4o, AI Search, Document Intelligence, Neo4j)."

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}
