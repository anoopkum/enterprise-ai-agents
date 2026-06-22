@description('Container Apps Environment name')
param envName string

@description('Container App name')
param appName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object

@description('Key Vault name for secret references')
param keyVaultName string

@description('Azure AI Foundry endpoint')
param aiFoundryEndpoint string

@description('Environment name for configuration')
param environmentName string

@description('Production flag — controls min/max replicas and CPU/memory')
param isProduction bool

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${envName}-logs'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: isProduction ? 90 : 30
  }
}

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
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
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        corsPolicy: {
          allowedOrigins: ['https://*.azurewebsites.net']
          allowedMethods: ['GET', 'POST']
          allowedHeaders: ['Authorization', 'Content-Type']
        }
      }
    }
    template: {
      containers: [
        {
          name: 'loan-agent'
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: {
            cpu: isProduction ? 2 : 1
            memory: isProduction ? '4Gi' : '2Gi'
          }
          env: [
            {
              name: 'ENVIRONMENT'
              value: environmentName
            }
            {
              name: 'AI_FOUNDRY_ENDPOINT'
              value: aiFoundryEndpoint
            }
            {
              name: 'AZURE_OPENAI_DEPLOYMENT'
              value: 'gpt-4o'
            }
            {
              name: 'MLFLOW_TRACKING_URI'
              value: 'mlruns'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 15
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: {
        minReplicas: isProduction ? 2 : 0
        maxReplicas: isProduction ? 20 : 3
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '50'
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
