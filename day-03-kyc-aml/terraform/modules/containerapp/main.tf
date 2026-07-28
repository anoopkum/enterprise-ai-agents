# ─── Log Analytics — the Container App Environment ships stdout/stderr here ───
resource "azurerm_log_analytics_workspace" "law" {
  name                = "${var.env_name}-logs"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = var.is_production ? 90 : 30
  tags                = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_container_app_environment" "env" {
  name                       = var.env_name
  resource_group_name        = var.resource_group_name
  location                   = var.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
  tags                       = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

# The app is provisioned as a SHELL: a placeholder image, no registry, no runtime
# env, no secrets. The real image (from ACR, by digest), the ACR registry binding,
# the runtime env vars, and the Neo4j Key-Vault-reference secrets are ALL set
# out-of-band by the deploy workflow's `az containerapp` steps.
#
# Why not declare the image / registry / KV secrets here? A hard bootstrap
# ordering: every role the app's identity needs (AcrPull to pull a private image,
# Key Vault Secrets User to resolve a KV reference, Cognitive Services roles for
# the models) is granted to `identity.principal_id` — which does not exist until
# the app itself is created. So the app must exist BEFORE its roles do, and at
# first-create it therefore cannot pull a private image or read a KV secret. The
# placeholder shell + post-provision CLI wiring (after role propagation) is how
# day-01/02 break that chicken-and-egg. `ignore_changes` on template / ingress /
# registry / secret then stops the next `terraform apply` from reverting what the
# CLI set.
resource "azurerm_container_app" "app" {
  name                         = var.app_name
  container_app_environment_id = azurerm_container_app_environment.env.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type = "SystemAssigned"
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    container {
      name   = "kyc-aml"
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
      cpu    = var.is_production ? 1.0 : 0.5
      memory = var.is_production ? "2Gi" : "1Gi"
    }

    min_replicas = var.is_production ? 1 : 0
    max_replicas = var.is_production ? 3 : 1
  }

  lifecycle {
    ignore_changes = [tags, template, ingress, registry, secret, identity]
  }
}
