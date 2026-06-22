output "endpoint" {
  value = "https://${var.location}.api.azureml.ms/rp/workspaces/subscriptions/placeholder/resourceGroups/placeholder/providers/Microsoft.MachineLearningServices/workspaces/${azurerm_machine_learning_workspace.project.name}"
}
output "project_name"        { value = azurerm_machine_learning_workspace.project.name }
output "hub_id"              { value = azurerm_machine_learning_workspace.hub.id }
output "project_id"          { value = azurerm_machine_learning_workspace.project.id }
output "project_principal_id" { value = azurerm_machine_learning_workspace.project.identity[0].principal_id }
