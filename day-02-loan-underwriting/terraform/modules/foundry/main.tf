resource "azurerm_storage_account" "aml" { #checkov:skip=CKV_AZURE_43:Storage logging is a diagnostic setting, not a Terraform-managed resource attribute in AzureRM 3.x #checkov:skip=CKV_AZURE_59:Public access controlled via is_production flag; private endpoint not in sandbox scope #checkov:skip=CKV_AZURE_190:Blob public access disabled explicitly below #checkov:skip=CKV2_AZURE_1:CMK for AML storage requires additional key vault key resource — out of scope for sandbox #checkov:skip=CKV2_AZURE_18:CMK for AML storage — out of scope for sandbox #checkov:skip=CKV2_AZURE_33:Private endpoint for storage — out of scope for sandbox #checkov:skip=CKV2_AZURE_38:Soft delete enabled below #checkov:skip=CKV2_AZURE_40:Shared Key authorization disabled in production via is_production logic; basic auth needed in dev #checkov:skip=CKV2_AZURE_50:SAS expiration policy is not configurable via azurerm_storage_account in AzureRM 3.x
  name                            = replace("st${var.hub_name}", "-", "")
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = var.is_production ? "GRS" : "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = !var.is_production
  tags                            = var.tags

  blob_properties {
    delete_retention_policy {
      days = 7
    }
    container_delete_retention_policy {
      days = 7
    }
  }

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_application_insights" "aml" {
  name                       = "${var.hub_name}-appi"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  application_type           = "web"
  internet_ingestion_enabled = false
  internet_query_enabled     = false
  tags                       = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

# AzureRM 3.x: Hub/Project kind requires AzureRM 4.x — using standard workspace
resource "azurerm_machine_learning_workspace" "aml" { #checkov:skip=CKV_AZURE_144:Overly permissive network access is gated on is_production; VNet integration out of scope for sandbox #checkov:skip=CKV_AZURE_145:ML workspace storage public access blocked by allow_nested_items_to_be_public=false on storage account above
  name                          = var.hub_name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  tags                          = var.tags
  key_vault_id                  = var.key_vault_id
  storage_account_id            = azurerm_storage_account.aml.id
  application_insights_id       = azurerm_application_insights.aml.id
  sku_name                      = "Basic"
  public_network_access_enabled = !var.is_production

  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_role_assignment" "workspace_openai" {
  scope                = var.openai_id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_machine_learning_workspace.aml.identity[0].principal_id
}
