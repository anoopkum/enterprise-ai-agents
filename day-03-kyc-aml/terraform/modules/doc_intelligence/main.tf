# Azure AI Document Intelligence (Form Recognizer) — OCR for scanned IDs & PDFs.
# Used by the ingestion layer's prebuilt-idDocument / prebuilt-layout models.
resource "azurerm_cognitive_account" "docintel" {
  name                          = var.account_name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  kind                          = "FormRecognizer"
  sku_name                      = var.sku_name
  tags                          = var.tags
  custom_subdomain_name         = var.account_name
  public_network_access_enabled = !var.is_production

  network_acls {
    default_action = var.is_production ? "Deny" : "Allow"
  }

  # Managed identity so the account can be reached keyless via Azure AD.
  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    ignore_changes = [tags]
  }
}

# Store the key so the app can read it from Key Vault (managed identity in prod).
resource "azurerm_key_vault_secret" "docintel_key" {
  name         = "doc-intelligence-key"
  value        = azurerm_cognitive_account.docintel.primary_access_key
  key_vault_id = var.key_vault_id
  content_type = "api-key"
}

resource "azurerm_key_vault_secret" "docintel_endpoint" {
  name         = "doc-intelligence-endpoint"
  value        = azurerm_cognitive_account.docintel.endpoint
  key_vault_id = var.key_vault_id
  content_type = "endpoint-url"
}
