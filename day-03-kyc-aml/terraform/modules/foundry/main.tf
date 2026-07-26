# ─────────────────────────────────────────────────────────────────────────────
# Azure AI Foundry (FDP) — single-resource design
#
# One `kind = AIServices` Cognitive Services account both HOSTS the model
# deployments (gpt-4o + text-embedding-3-large) AND contains the Foundry project
# (agents / threads / runs). This replaces the older split of a standalone Azure
# OpenAI resource + a classic AI Foundry hub + a backing storage account:
#   - no separate model host (deployments live on this account)
#   - no classic hub (project_management_enabled turns this account into a Foundry)
#   - no backing storage account (basic agent state uses the account's own storage)
#
# Confirmed pure-AzureRM per learn.microsoft.com/azure/ai-foundry/how-to/create-resource-terraform
# — AzAPI is only needed for connections / capability-hosts, which we don't use
# because the models are deployed ON this account (no cross-resource connection).
# ─────────────────────────────────────────────────────────────────────────────

resource "azurerm_cognitive_account" "foundry" {
  name                = var.account_name
  resource_group_name = var.resource_group_name
  location            = var.location
  kind                = "AIServices"
  sku_name            = "S0"
  tags                = var.tags

  # Custom subdomain is REQUIRED for stateful Foundry work (agent service) and for
  # the token-based (Entra ID) data-plane endpoints the app uses.
  custom_subdomain_name = var.account_name

  # Turns this AIServices account into a Foundry resource that can own projects.
  project_management_enabled = true

  public_network_access_enabled = !var.is_production

  network_acls {
    default_action = var.is_production ? "Deny" : "Allow"
  }

  # System-assigned identity so the account (and downstream project) reach Search /
  # Document Intelligence keyless via Azure AD — the managed-identity path in prod.
  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    ignore_changes = [tags]
  }
}

# The Foundry project — a child of the account. Agents, threads, and runs are
# scoped here; there is no separate hub or storage account to provision.
resource "azurerm_cognitive_account_project" "project" {
  name                 = var.project_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id
  location             = azurerm_cognitive_account.foundry.location

  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    ignore_changes = [tags]
  }
}

# ─── Model deployments on the SAME account ───
resource "azurerm_cognitive_deployment" "chat" {
  name                 = var.chat_deployment_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = var.chat_model_name
    version = var.chat_model_version
  }

  sku {
    name     = "Standard"
    capacity = var.is_production ? 100 : 30
  }
}

resource "azurerm_cognitive_deployment" "embeddings" {
  name                 = var.embed_deployment_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = "text-embedding-3-large"
    version = var.embed_version
  }

  sku {
    name     = "Standard"
    capacity = var.is_production ? 120 : 50
  }

  # The account serialises deployment operations — deploy one at a time.
  depends_on = [azurerm_cognitive_deployment.chat]
}

# ─── Key Vault secrets (operator/reference; app auth is keyless via managed identity) ───
resource "azurerm_key_vault_secret" "openai_key" {
  name         = "azure-openai-api-key"
  value        = azurerm_cognitive_account.foundry.primary_access_key
  key_vault_id = var.key_vault_id
  content_type = "api-key"
}

resource "azurerm_key_vault_secret" "openai_endpoint" {
  name         = "azure-openai-endpoint"
  value        = azurerm_cognitive_account.foundry.endpoint
  key_vault_id = var.key_vault_id
  content_type = "endpoint-url"
}
