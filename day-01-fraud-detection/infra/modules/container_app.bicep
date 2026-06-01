param envName string
param appName string
param location string
param tags object
param keyVaultName string
param cosmosEndpoint string
param eventHubNamespace string
param aiFoundryConnectionString string

var containerImage = 'ghcr.io/anoopkum/enterprise-ai-agents/fraud-detection:latest'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'law-${envName}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
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
        external: false  // internal only; fronted by API Management
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      secrets: [
        {
          name: 'cosmos-endpoint'
          keyVaultUrl: 'https://${keyVaultName}${environment().suffixes.keyvaultDns}/secrets/cosmos-connection-string'
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
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'COSMOS_DB_ENDPOINT', value: cosmosEndpoint }
            { name: 'COSMOS_DB_NAME', value: 'frauddb' }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: 'gpt-4o' }
            { name: 'AI_FOUNDRY_CONNECTION_STRING', secretRef: 'ai-foundry-conn' }
            { name: 'ENVIRONMENT', value: 'production' }
            { name: 'EVENT_HUB_NAMESPACE', value: eventHubNamespace }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 2
        maxReplicas: 20
        rules: [
          {
            name: 'http-scale'
            http: { metadata: { concurrentRequests: '10' } }
          }
        ]
      }
    }
  }
}

output url string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output principalId string = containerApp.identity.principalId
