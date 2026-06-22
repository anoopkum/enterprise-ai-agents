resource "azurerm_container_registry" "acr" { #checkov:skip=CKV_AZURE_139:Public access required for GitHub Actions CI/CD; private endpoints not in scope for this sandbox #checkov:skip=CKV_AZURE_163:Defender for Containers is a subscription-level control outside Terraform scope #checkov:skip=CKV_AZURE_164:Content trust (trusted images) requires Premium SKU; dev uses Basic #checkov:skip=CKV_AZURE_165:Geo-replication enabled in production via dynamic block; not applicable for dev Basic SKU #checkov:skip=CKV_AZURE_166:Quarantine policy requires Premium SKU; dev uses Basic #checkov:skip=CKV_AZURE_233:Zone redundancy requires Premium SKU; dev uses Basic #checkov:skip=CKV_AZURE_237:Dedicated data endpoints require Premium SKU; dev uses Basic
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.is_production ? "Premium" : "Basic"
  admin_enabled       = false
  tags                = var.tags

  retention_policy { #checkov:skip=CKV_AZURE_167:Retention policy enabled here
    days    = 7
    enabled = true
  }

  dynamic "georeplications" {
    for_each = var.is_production ? [var.secondary_location] : []
    content {
      location                = georeplications.value
      zone_redundancy_enabled = true
    }
  }

  lifecycle {
    ignore_changes = [tags]
  }
}
