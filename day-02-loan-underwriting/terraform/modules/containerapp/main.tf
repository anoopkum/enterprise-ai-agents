resource "azurerm_log_analytics_workspace" "this" {
  name                = "${var.env_name}-logs"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = var.is_production ? 90 : 30
  tags                = var.tags
}

resource "azurerm_container_app_environment" "this" {
  name                       = var.env_name
  resource_group_name        = var.resource_group_name
  location                   = var.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  zone_redundancy_enabled    = var.is_production
  tags                       = var.tags
}

resource "azurerm_container_app" "this" {
  name                         = var.app_name
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type = "SystemAssigned"
  }

  registry {
    server   = var.acr_login_server
    identity = "system"
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
      name   = "loan-agent"
      image  = var.container_image
      cpu    = var.is_production ? 2.0 : 1.0
      memory = var.is_production ? "4Gi" : "2Gi"

      env {
        name  = "ENVIRONMENT"
        value = var.environment_name
      }
      env {
        name  = "AI_FOUNDRY_ENDPOINT"
        value = var.ai_foundry_endpoint
      }
      env {
        name  = "AZURE_OPENAI_DEPLOYMENT"
        value = "gpt-4o"
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights-conn-str"
      }

      liveness_probe {
        transport               = "HTTP"
        path                    = "/health"
        port                    = 8000
        initial_delay           = 15
        interval_seconds        = 30
        failure_count_threshold = 3
      }
    }

    min_replicas = var.is_production ? 2 : 0
    max_replicas = var.is_production ? 20 : 3

    http_scale_rule {
      name                = "http-scaling"
      concurrent_requests = "50"
    }
  }

  secret {
    name  = "appinsights-conn-str"
    value = var.app_insights_conn_str
  }
}
