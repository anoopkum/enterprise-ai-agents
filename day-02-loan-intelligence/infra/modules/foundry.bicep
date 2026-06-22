@description('AI Foundry Hub name')
param hubName string

@description('AI Foundry Project name')
param projectName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object

@description('Key Vault resource ID — attached to the Hub')
param keyVaultId string

@description('Azure OpenAI endpoint to connect as a Hub connection')
param openAIEndpoint string

@description('Production flag')
param isProduction bool

resource aiHub 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: hubName
  location: location
  tags: tags
  kind: 'Hub'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    friendlyName: 'Loan Intelligence AI Hub'
    keyVault: keyVaultId
    publicNetworkAccess: isProduction ? 'Disabled' : 'Enabled'
  }
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
}

resource aiProject 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: projectName
  location: location
  tags: tags
  kind: 'Project'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    friendlyName: 'Loan Credit Intelligence Project'
    hubResourceId: aiHub.id
  }
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
}

output aiFoundryEndpoint string = 'https://${location}.api.azureml.ms'
output projectName string = aiProject.name
output hubId string = aiHub.id
output projectId string = aiProject.id
output projectPrincipalId string = aiProject.identity.principalId
