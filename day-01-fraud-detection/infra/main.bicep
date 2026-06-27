@description('Environment name: dev | staging | prod')
@allowed(['dev', 'staging', 'prod'])
param environment string = 'dev'

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Project identifier prefix')
param projectName string = 'fraud-agent'

@description('Azure AD Object ID for Key Vault admin role')
param adminObjectId string

@description('Principal type for Key Vault admin role assignment: User or ServicePrincipal')
@allowed(['User', 'ServicePrincipal'])
param adminPrincipalType string = 'User'

// Single flag that gates every cost-sensitive setting below
var isProduction = environment == 'prod'
var isStaging    = environment == 'staging'

var prefix = '${projectName}-${environment}'
var tags = {
  project: projectName
  environment: environment
  managedBy: 'bicep'
  day: '01'
  agent: 'fraud-detection'
  costCenter: isProduction ? 'prod-banking' : 'dev-test'
}

// ─── Key Vault ───────────────────────────────────────────────────────────────
module keyVault 'modules/keyvault.bicep' = {
  name: 'keyVaultDeploy'
  params: {
    name: 'kv-fd-${environment}'
    location: location
    tags: tags
    adminObjectId: adminObjectId
    adminPrincipalType: adminPrincipalType
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
    isProduction: isProduction
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
    isProduction: isProduction
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
    isProduction: isProduction
  }
}

// ─── Azure AI Foundry ─────────────────────────────────────────────────────────
module aiFoundry 'modules/ai_foundry.bicep' = {
  name: 'aiFoundryDeploy'
  params: {
    hubName: 'aihub-${prefix}'
    projectName: 'proj-${prefix}'
    location: location
    tags: tags
    keyVaultId: keyVault.outputs.id
    isProduction: isProduction
  }
}

// ─── Container Apps ───────────────────────────────────────────────────────────
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
    aiFoundryEndpoint: aiFoundry.outputs.aiFoundryEndpoint
    aiFoundryConnectionString: aiFoundry.outputs.connectionString
    environmentName: environment
    isProduction: isProduction
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
    isProduction: isProduction
  }
}

output containerAppUrl string = containerApp.outputs.url
output aiFoundryProjectName string = aiFoundry.outputs.projectName
output cosmosDbEndpoint string = cosmosDb.outputs.endpoint
output eventHubNamespace string = eventHub.outputs.namespaceName
output estimatedMonthlyCost string = isProduction ? '~$3,275/mo' : (isStaging ? '~$1,200/mo' : '~$800/mo')
