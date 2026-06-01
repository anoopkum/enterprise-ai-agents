@description('Environment name (dev/staging/prod)')
param environment string = 'dev'

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Project identifier prefix')
param projectName string = 'fraud-agent'

@description('Azure AD Object ID for Key Vault access policy')
param adminObjectId string

var prefix = '${projectName}-${environment}'
var tags = {
  project: projectName
  environment: environment
  managedBy: 'bicep'
  day: '01'
  agent: 'fraud-detection'
}

// ─── Key Vault ───────────────────────────────────────────────────────────────
module keyVault 'modules/keyvault.bicep' = {
  name: 'keyVaultDeploy'
  params: {
    name: 'kv-${prefix}'
    location: location
    tags: tags
    adminObjectId: adminObjectId
  }
}

// ─── Cosmos DB ───────────────────────────────────────────────────────────────
module cosmosDb 'modules/cosmosdb.bicep' = {
  name: 'cosmosDbDeploy'
  params: {
    accountName: 'cosmos-${prefix}'
    location: location
    tags: tags
    keyVaultName: keyVault.outputs.name
  }
}

// ─── Event Hub ───────────────────────────────────────────────────────────────
module eventHub 'modules/eventhub.bicep' = {
  name: 'eventHubDeploy'
  params: {
    namespaceName: 'evhns-${prefix}'
    hubName: 'transactions'
    location: location
    tags: tags
    keyVaultName: keyVault.outputs.name
  }
}

// ─── Service Bus ─────────────────────────────────────────────────────────────
module serviceBus 'modules/servicebus.bicep' = {
  name: 'serviceBusDeploy'
  params: {
    namespaceName: 'sb-${prefix}'
    location: location
    tags: tags
    keyVaultName: keyVault.outputs.name
  }
}

// ─── Azure AI Foundry (AI Hub + Project) ─────────────────────────────────────
module aiFoundry 'modules/ai_foundry.bicep' = {
  name: 'aiFoundryDeploy'
  params: {
    hubName: 'aihub-${prefix}'
    projectName: 'proj-${prefix}'
    location: location
    tags: tags
    keyVaultId: keyVault.outputs.id
  }
}

// ─── Container Apps Environment + App ────────────────────────────────────────
module containerApp 'modules/container_app.bicep' = {
  name: 'containerAppDeploy'
  params: {
    envName: 'cae-${prefix}'
    appName: 'ca-${prefix}'
    location: location
    tags: tags
    keyVaultName: keyVault.outputs.name
    cosmosEndpoint: cosmosDb.outputs.endpoint
    eventHubNamespace: eventHub.outputs.namespaceName
    aiFoundryConnectionString: aiFoundry.outputs.connectionString
  }
}

// ─── Application Insights ────────────────────────────────────────────────────
module appInsights 'modules/app_insights.bicep' = {
  name: 'appInsightsDeploy'
  params: {
    name: 'appi-${prefix}'
    location: location
    tags: tags
    keyVaultName: keyVault.outputs.name
  }
}

output containerAppUrl string = containerApp.outputs.url
output aiFoundryProjectName string = aiFoundry.outputs.projectName
output cosmosDbEndpoint string = cosmosDb.outputs.endpoint
output eventHubNamespace string = eventHub.outputs.namespaceName
