param hubName string
param projectName string
param location string
param tags object
param keyVaultId string
param isProduction bool

// Dev: gpt-4o-mini 10K TPM, public network → minimal cost (pay-per-token only)
// Prod: gpt-4o 50K TPM, private endpoints → higher capacity + isolation
var modelName = isProduction ? 'gpt-4o' : 'gpt-4o-mini'
var modelVersion = isProduction ? '2024-08-06' : '2024-07-18'
var tpmCapacity = isProduction ? 50 : 10
var networkAccess = isProduction ? 'Disabled' : 'Enabled'

// Azure OpenAI account (hosts model deployments)
resource openAiAccount 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: 'oai-${hubName}'
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: 'oai-${hubName}'
    publicNetworkAccess: networkAccess
    disableLocalAuth: false
  }
}

// Model deployment on the OpenAI account
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openAiAccount
  name: modelName
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
  sku: {
    name: 'GlobalStandard'
    capacity: tpmCapacity
  }
}

// AI Foundry Hub (orchestration layer, linked to the OpenAI account)
resource aiHub 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: hubName
  location: location
  tags: tags
  kind: 'Hub'
  identity: { type: 'SystemAssigned' }
  properties: {
    description: 'AI Foundry Hub for Enterprise AI Agents'
    friendlyName: hubName
    keyVault: keyVaultId
    publicNetworkAccess: networkAccess
    managedNetwork: isProduction ? {
      isolationMode: 'AllowOnlyApprovedOutbound'
    } : {
      isolationMode: 'Disabled'
    }
  }
}

// AI Foundry Project
resource aiProject 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: projectName
  location: location
  tags: tags
  kind: 'Project'
  identity: { type: 'SystemAssigned' }
  properties: {
    description: 'Day 01 - Fraud Detection Agent Project'
    friendlyName: 'Fraud Detection Agent'
    hubResourceId: aiHub.id
    publicNetworkAccess: networkAccess
  }
}

output hubName string = aiHub.name
output projectName string = aiProject.name
output hubId string = aiHub.id
output projectId string = aiProject.id
output modelDeploymentName string = modelName
output openAiEndpoint string = openAiAccount.properties.endpoint
// Connection string for AI Foundry SDK
output connectionString string = '${aiHub.properties.discoveryUrl};${subscription().subscriptionId};${resourceGroup().name};${aiProject.name}'
