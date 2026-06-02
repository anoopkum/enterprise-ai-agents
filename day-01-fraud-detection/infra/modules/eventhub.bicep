param namespaceName string
param hubName string
param location string
param tags object
param keyVaultName string
param isProduction bool
param utcNowValue string = utcNow()

// Dev/Staging: Basic tier, 1 TU, 1 partition, no capture → ~$11/mo
// Prod:        Standard tier, 2 TU, 8 partitions, auto-inflate, capture → ~$280/mo
var skuName = isProduction ? 'Standard' : 'Basic'
var skuTier = isProduction ? 'Standard' : 'Basic'
var throughputUnits = isProduction ? 2 : 1
var partitionCount = isProduction ? 8 : 2
var messageRetentionDays = isProduction ? 7 : 1  // Basic max is 1 day

resource eventHubNamespace 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: namespaceName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
    capacity: throughputUnits
  }
  properties: {
    isAutoInflateEnabled: isProduction        // Auto-inflate only on Standard
    maximumThroughputUnits: isProduction ? 10 : 0
    kafkaEnabled: false
    publicNetworkAccess: isProduction ? 'Disabled' : 'Enabled'
    zoneRedundant: isProduction
  }
}

resource eventHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: eventHubNamespace
  name: hubName
  properties: {
    messageRetentionInDays: messageRetentionDays
    partitionCount: partitionCount
    // Capture is Standard-only — omit entirely in dev (API rejects {enabled:false} without destination)
    captureDescription: isProduction ? {
      enabled: true
      encoding: 'Avro'
      intervalInSeconds: 300
      sizeLimitInBytes: 10485760
      destination: {
        name: 'EventHubArchive.AzureBlockBlob'
        properties: {
          archiveNameFormat: '{Namespace}/{EventHub}/{PartitionId}/{Year}/{Month}/{Day}/{Hour}/{Minute}/{Second}'
        }
      }
    } : null
  }
}

resource sendAuthRule 'Microsoft.EventHub/namespaces/eventhubs/authorizationRules@2024-01-01' = {
  parent: eventHub
  name: 'SendOnly'
  properties: { rights: ['Send'] }
}

resource listenAuthRule 'Microsoft.EventHub/namespaces/eventhubs/authorizationRules@2024-01-01' = {
  parent: eventHub
  name: 'ListenOnly'
  properties: { rights: ['Listen'] }
}

resource ehConnectionSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  name: '${keyVaultName}/eventhub-connection-string'
  properties: {
    value: listenAuthRule.listKeys().primaryConnectionString
    attributes: {
      enabled: true
      exp: isProduction
        ? dateTimeToEpoch(dateTimeAdd(utcNowValue, 'P1Y'))
        : dateTimeToEpoch(dateTimeAdd(utcNowValue, 'P90D'))
    }
  }
}

output namespaceName string = eventHubNamespace.name
output hubName string = eventHub.name
