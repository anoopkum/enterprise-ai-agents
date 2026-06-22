@description('Environment name: dev | staging | prod')
@allowed(['dev', 'staging', 'prod'])
param environment string = 'dev'

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Project identifier prefix')
param projectName string = 'loan-agent'

@description('Azure AD Object ID for Key Vault admin role')
param adminObjectId string

var isProduction = environment == 'prod'
var isStaging    = environment == 'staging'

var prefix = '${projectName}-${environment}'
var tags = {
  project: projectName
  environment: environment
  managedBy: 'bicep'
  day: '02'
  agent: 'loan-credit-intelligence'
  costCenter: isProduction ? 'prod-banking' : 'dev-test'
}

// ─── Key Vault ───────────────────────────────────────────────────────────────
module keyVault 'modules/keyvault.bicep' = {
  name: 'keyVaultDeploy'
  params: {
    name: 'kv-${prefix}'
    location: location
    tags: tags
    adminObjectId: adminObjectId
    isProduction: isProduction
  }
}

// ─── Azure OpenAI ────────────────────────────────────────────────────────────
module openAI 'modules/openai.bicep' = {
  name: 'openAIDeploy'
  params: {
    accountName: 'oai-${prefix}'
    location: location
    tags: tags
    keyVaultName: keyVault.outputs.name
    isProduction: isProduction
  }
}

// ─── Azure AI Foundry ────────────────────────────────────────────────────────
module aiFoundry 'modules/foundry.bicep' = {
  name: 'aiFoundryDeploy'
  params: {
    hubName: 'aihub-${prefix}'
    projectName: 'proj-${prefix}'
    location: location
    tags: tags
    keyVaultId: keyVault.outputs.id
    openAIEndpoint: openAI.outputs.endpoint
    isProduction: isProduction
  }
}

// ─── Azure Container Apps ─────────────────────────────────────────────────────
module containerApp 'modules/containerapp.bicep' = {
  name: 'containerAppDeploy'
  params: {
    envName: 'cae-${prefix}'
    appName: 'ca-${prefix}'
    location: location
    tags: tags
    keyVaultName: keyVault.outputs.name
    aiFoundryEndpoint: aiFoundry.outputs.aiFoundryEndpoint
    environmentName: environment
    isProduction: isProduction
  }
}

// ─── Azure Monitor / Application Insights ────────────────────────────────────
module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoringDeploy'
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
output keyVaultName string = keyVault.outputs.name
output estimatedMonthlyCost string = isProduction ? '~$2,800/mo' : (isStaging ? '~$950/mo' : '~$600/mo')
