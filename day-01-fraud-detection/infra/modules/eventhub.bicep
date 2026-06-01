param namespaceName string
param hubName string
param location string
param tags object
param keyVaultName string

resource eventHubNamespace 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: namespaceName
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Standard'
    capacity: 2
  }
  properties: {
    isAutoInflateEnabled: true
    maximumThroughputUnits: 10
    kafkaEnabled: false
    publicNetworkAccess: 'Disabled'
  }
}

resource eventHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: eventHubNamespace
  name: hubName
  properties: {
    messageRetentionInDays: 7
    partitionCount: 8
    captureDescription: {
      enabled: true
      encoding: 'Avro'
      intervalInSeconds: 300
      sizeLimitInBytes: 10485760
      destination: {
        name: 'EventHubArchive.AzureBlockBlob'
        properties: {
          // Storage account configured separately
          archiveNameFormat: '{Namespace}/{EventHub}/{PartitionId}/{Year}/{Month}/{Day}/{Hour}/{Minute}/{Second}'
        }
      }
    }
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
  }
}

output namespaceName string = eventHubNamespace.name
output hubName string = eventHub.name
