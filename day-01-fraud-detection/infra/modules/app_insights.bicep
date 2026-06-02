param name string
param location string
param tags object
param keyVaultName string
param isProduction bool

// Dev: 7-day retention, daily cap 0.5GB → near-zero cost
// Prod: 90-day retention, no cap → ~$45/mo
var retentionDays = isProduction ? 90 : 7

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'law-${name}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: retentionDays
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    workspaceCapping: isProduction ? {
      dailyQuotaGb: -1
    } : {
      dailyQuotaGb: json('0.5')  // Hard cap 500MB/day in dev
    }
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
    RetentionInDays: retentionDays
    // Dev: allow public ingestion (no private endpoint cost)
    publicNetworkAccessForIngestion: isProduction ? 'Disabled' : 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
    // Sampling: reduce telemetry volume in dev
    SamplingPercentage: isProduction ? 100 : 10
  }
}

resource appiConnectionSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  name: '${keyVaultName}/appinsights-connection-string'
  properties: {
    value: appInsights.properties.ConnectionString
    attributes: {
      enabled: true
      exp: isProduction
        ? dateTimeToEpoch(dateTimeAdd(utcNow(), 'P1Y'))
        : dateTimeToEpoch(dateTimeAdd(utcNow(), 'P90D'))
    }
  }
}

output name string = appInsights.name
output connectionString string = appInsights.properties.ConnectionString
output instrumentationKey string = appInsights.properties.InstrumentationKey
