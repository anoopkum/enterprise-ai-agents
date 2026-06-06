param hubName string
param projectName string
param location string
param tags object
param keyVaultId string
param isProduction bool

// Dev: gpt-4o-mini 10K TPM, public network → minimal cost (pay-per-token only)
// Staging/Prod: gpt-4o 50K TPM, private endpoints → higher capacity + isolation
var modelName = isProduction ? 'gpt-4o' : 'gpt-4o-mini'
// gpt-4o 2024-08-06 is deprecated; use 2024-11-20 (latest stable as of 2026)
var modelVersion = isProduction ? '2024-11-20' : '2024-07-18'
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

// Primary model deployment — gpt-4o-mini in dev, gpt-4o in staging/prod
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

// Secondary gpt-4o deployment for staging (enables showcase with full reasoning quality)
// Only deployed when !isProduction so dev keeps minimal cost; staging gets both models
resource gpt4oStagingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = if (!isProduction) {
  parent: openAiAccount
  name: 'gpt-4o'
  dependsOn: [modelDeployment]
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-11-20'
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
  sku: {
    name: 'GlobalStandard'
    capacity: 30
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
// AgentsClient endpoint: the project's agentsEndpointUri (full path including workspace)
// agentsEndpointUri is not exposed in the 2024-04-01 Bicep schema — construct it from known format
output aiFoundryEndpoint string = 'https://${location}.api.azureml.ms/agents/v1.0/subscriptions/${subscription().subscriptionId}/resourceGroups/${resourceGroup().name}/providers/Microsoft.MachineLearningServices/workspaces/${aiProject.name}'
// Connection string for AI Foundry SDK
output connectionString string = '${aiHub.properties.discoveryUrl};${subscription().subscriptionId};${resourceGroup().name};${aiProject.name}'
