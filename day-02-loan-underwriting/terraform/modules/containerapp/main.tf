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
    target_port      = 80
    transport        = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    container {
      name   = "loan-agent"
      image  = var.container_image
      cpu    = var.is_production ? 2.0 : 1.0
      memory = var.is_production ? "4Gi" : "2Gi"
    }

    min_replicas = 0
    max_replicas = var.is_production ? 20 : 3
  }

  secret {
    name  = "appinsights-conn-str"
    value = var.app_insights_conn_str
  }

  lifecycle {
    # ml-deploy manages image, port, env vars, scaling rules, and registry after initial creation
    ignore_changes = [tags, template, ingress, registry, secret]
  }
}
