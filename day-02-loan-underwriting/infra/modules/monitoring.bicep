@description('Application Insights name')
param name string

@description('Azure region')
param location string

@description('Resource tags')
param tags object

@description('Key Vault name for storing the connection string secret')
param keyVaultName string

@description('Production flag — enables higher retention and alerts')
param isProduction bool

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${name}-workspace'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: isProduction ? 90 : 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: name
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    RetentionInDays: isProduction ? 90 : 30
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

resource highDeclineRateAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = if (isProduction) {
  name: '${name}-high-decline-rate'
  location: 'global'
  tags: tags
  properties: {
    description: 'Alert when loan decline rate exceeds 80% in a 15-minute window — may indicate model drift'
    severity: 2
    enabled: true
    scopes: [appInsights.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'DeclineRate'
          metricName: 'requests/failed'
          operator: 'GreaterThan'
          threshold: 100
          timeAggregation: 'Count'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    autoMitigate: true
    actions: []
  }
}

resource kvRef 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource appInsightsSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kvRef
  name: 'applicationinsights-connection-string'
  properties: {
    value: appInsights.properties.ConnectionString
  }
}

output instrumentationKey string = appInsights.properties.InstrumentationKey
output connectionString string = appInsights.properties.ConnectionString
output id string = appInsights.id
