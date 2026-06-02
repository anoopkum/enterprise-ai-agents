param hubName string
param projectName string
param location string
param tags object
param keyVaultId string
param isProduction bool

// Dev: gpt-4o-mini, 10K TPM, public network → ~$0/mo fixed (pay-per-token only)
// Prod: gpt-4o, 50K TPM GlobalStandard, private endpoints → ~$0/mo fixed (pay-per-token)
// Network isolation cost: private endpoints + managed VNet add ~$40-80/mo in prod
var modelName = isProduction ? 'gpt-4o' : 'gpt-4o-mini'
var modelVersion = isProduction ? '2024-08-06' : '2024-07-18'
var tpmCapacity = isProduction ? 50 : 10  // Thousands of tokens per minute
var networkAccess = isProduction ? 'Disabled' : 'Enabled'
var isolationMode = isProduction ? 'AllowOnlyApprovedOutbound' : 'Disabled'

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
    publicNetworkAccess: networkAccess
    // Dev: no managed network isolation (saves ~$40/mo in VNet costs)
    // Prod: allow only approved outbound for compliance
    managedNetwork: isProduction ? {
      isolationMode: isolationMode
    } : {
      isolationMode: 'Disabled'
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
    publicNetworkAccess: networkAccess
  }
}

// Model deployment: gpt-4o-mini (dev) or gpt-4o (prod)
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  name: '${hubName}/${modelName}'
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
    capacity: tpmCapacity  // 10K TPM dev vs 50K TPM prod
  }
}

output hubName string = aiHub.name
output projectName string = aiProject.name
output hubId string = aiHub.id
output projectId string = aiProject.id
output modelDeploymentName string = modelName
// Connection string pattern for AI Foundry SDK
output connectionString string = '${aiHub.properties.discoveryUrl};${subscription().subscriptionId};${resourceGroup().name};${aiProject.name}'
