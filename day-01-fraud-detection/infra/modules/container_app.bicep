param envName string
param appName string
param location string
param tags object
param keyVaultName string
param cosmosEndpoint string
param eventHubNamespace string
param aiFoundryEndpoint string  // Azure OpenAI endpoint URL for AgentsClient
@secure()
param aiFoundryConnectionString string
param environmentName string
param isProduction bool

var containerImage = 'ghcr.io/anoopkum/enterprise-ai-agents/fraud-detection:latest'

// Dev: 0.25 vCPU / 0.5Gi, min 0 replicas (scales to zero = zero idle cost)
// Staging: 0.5 vCPU / 1Gi, min 1 replica
// Prod: 0.5 vCPU / 1Gi, min 2 replicas for HA
var cpuCores = isProduction ? '0.5' : '0.25'
var memoryGi = isProduction ? '1Gi' : '0.5Gi'
var minReplicas = isProduction ? 2 : (environmentName == 'staging' ? 1 : 0)
var maxReplicas = isProduction ? 20 : (environmentName == 'staging' ? 5 : 3)
var logRetentionDays = isProduction ? 30 : 30  // PerGB2018 minimum is 30 days

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'law-${envName}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: logRetentionDays
    // Daily cap prevents runaway log ingestion cost in dev
    workspaceCapping: isProduction ? {
      dailyQuotaGb: -1  // Unlimited in prod
    } : {
      dailyQuotaGb: json('0.5')  // 500MB/day cap in dev (~$1.50/mo max)
    }
  }
}

resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    // Zone redundancy: prod only
    zoneRedundant: isProduction
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    environmentId: containerAppEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: !isProduction  // Dev: external for easy testing; Prod: internal
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      secrets: [
        {
          name: 'cosmos-endpoint'
          keyVaultUrl: 'https://${keyVaultName}${az.environment().suffixes.keyvaultDns}/secrets/cosmos-connection-string'
          identity: 'system'
        }
        {
          name: 'ai-foundry-conn'
          value: aiFoundryConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'fraud-agent'
          image: containerImage
          resources: {
            cpu: json(cpuCores)
            memory: memoryGi
          }
          env: [
            { name: 'COSMOS_DB_ENDPOINT', value: cosmosEndpoint }
            { name: 'COSMOS_DB_NAME', value: 'frauddb' }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: isProduction ? 'gpt-4o' : 'gpt-4o-mini' }
            { name: 'AI_FOUNDRY_ENDPOINT', value: aiFoundryEndpoint }
            { name: 'AI_FOUNDRY_CONNECTION_STRING', secretRef: 'ai-foundry-conn' }
            { name: 'ENVIRONMENT', value: environmentName }
            { name: 'EVENT_HUB_NAMESPACE', value: eventHubNamespace }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: isProduction ? 30 : 60
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: isProduction ? 10 : 30
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                // Prod: scale at 10 concurrent; Dev: scale at 5
                concurrentRequests: isProduction ? '10' : '5'
              }
            }
          }
        ]
      }
    }
  }
}

output url string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output principalId string = containerApp.identity.principalId
