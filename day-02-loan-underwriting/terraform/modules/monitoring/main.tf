resource "azurerm_log_analytics_workspace" "law" {
  name                = "${var.name}-workspace"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = var.is_production ? 90 : 30
  tags                = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_application_insights" "appi" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  workspace_id        = azurerm_log_analytics_workspace.law.id
  application_type    = "web"
  retention_in_days   = var.is_production ? 90 : 30
  tags                = var.tags

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_monitor_metric_alert" "high_decline_rate" {
  count               = var.is_production ? 1 : 0
  name                = "${var.name}-high-decline-rate"
  resource_group_name = var.resource_group_name
  scopes              = [azurerm_application_insights.appi.id]
  description         = "Alert when loan decline rate exceeds threshold — may indicate model drift"
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"
  auto_mitigate       = true
  tags                = var.tags

  criteria {
    metric_namespace = "microsoft.insights/components"
    metric_name      = "requests/failed"
    aggregation      = "Count"
    operator         = "GreaterThan"
    threshold        = 100
  }
}

resource "azurerm_key_vault_secret" "appinsights_conn_str" {
  name         = "applicationinsights-connection-string"
  value        = azurerm_application_insights.appi.connection_string
  key_vault_id = var.key_vault_id
}
