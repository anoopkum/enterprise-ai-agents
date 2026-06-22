output "endpoint" {
  value = "https://${var.location}.api.azureml.ms/rp/workspaces/subscriptions/placeholder/resourceGroups/${var.resource_group_name}/providers/Microsoft.MachineLearningServices/workspaces/${azurerm_machine_learning_workspace.hub.name}"
}
output "workspace_name"      { value = azurerm_machine_learning_workspace.hub.name }
output "hub_id"              { value = azurerm_machine_learning_workspace.hub.id }
output "workspace_principal_id" { value = azurerm_machine_learning_workspace.hub.identity[0].principal_id }
