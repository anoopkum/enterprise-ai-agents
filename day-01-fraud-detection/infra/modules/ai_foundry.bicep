param hubName string
param projectName string
param location string
param tags object
param keyVaultId string

// Azure AI Foundry Hub
resource aiHub 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: hubName
  location: location
  tags: tags
  kind: 'Hub'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: 'AI Foundry Hub for Enterprise AI Agents'
    friendlyName: hubName
    keyVault: keyVaultId
    publicNetworkAccess: 'Disabled'
    managedNetwork: {
      isolationMode: 'AllowOnlyApprovedOutbound'
    }
  }
}

// Azure AI Foundry Project
resource aiProject 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: projectName
  location: location
  tags: tags
  kind: 'Project'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: 'Day 01 - Fraud Detection Agent Project'
    friendlyName: 'Fraud Detection Agent'
    hubResourceId: aiHub.id
    publicNetworkAccess: 'Disabled'
  }
}

// GPT-4o model deployment
resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  name: '${hubName}/gpt-4o'
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-08-06'
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
  sku: {
    name: 'GlobalStandard'
    capacity: 50
  }
}

output hubName string = aiHub.name
output projectName string = aiProject.name
output hubId string = aiHub.id
output projectId string = aiProject.id
// Connection string pattern for AI Foundry SDK
output connectionString string = '${aiHub.properties.discoveryUrl};${subscription().subscriptionId};${resourceGroup().name};${aiProject.name}'
