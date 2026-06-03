param namespaceName string
param location string
param tags object
param keyVaultName string
param isProduction bool
param utcNowValue string = utcNow()

// Dev/Staging: Standard tier (~$52/mo) — no VNet isolation, no geo-DR
// Prod:        Premium tier (~$330/mo) — private endpoints, 99.9% SLA, geo-DR
// NOTE: capacity is only valid for Premium tier; omit (null) for Standard to avoid BadRequest
var skuName = isProduction ? 'Premium' : 'Standard'
var skuTier = isProduction ? 'Premium' : 'Standard'

resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: namespaceName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
    capacity: isProduction ? 1 : null
  }
  properties: {
    publicNetworkAccess: isProduction ? 'Disabled' : 'Enabled'
    minimumTlsVersion: '1.2'
    zoneRedundant: isProduction
  }
}

resource fraudAlertsQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'fraud-alerts'
  properties: {
    lockDuration: 'PT5M'
    maxSizeInMegabytes: 1024  // Minimum valid value; prod uses same (Standard tier max without Premium)
    requiresDuplicateDetection: true
    duplicateDetectionHistoryTimeWindow: 'PT10M'
    maxDeliveryCount: isProduction ? 3 : 2
    deadLetteringOnMessageExpiration: true
    defaultMessageTimeToLive: isProduction ? 'P1D' : 'PT1H'
  }
}

resource reviewQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'review-queue'
  properties: {
    lockDuration: 'PT5M'
    maxSizeInMegabytes: 1024  // Minimum valid value; prod uses same (Standard tier max without Premium)
    maxDeliveryCount: isProduction ? 5 : 2
    defaultMessageTimeToLive: isProduction ? 'P7D' : 'PT4H'
  }
}

resource sbConnectionSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  name: '${keyVaultName}/servicebus-connection-string'
  properties: {
    value: serviceBusNamespace.listKeys().primaryConnectionString
    attributes: {
      enabled: true
      exp: isProduction
        ? dateTimeToEpoch(dateTimeAdd(utcNowValue, 'P1Y'))
        : dateTimeToEpoch(dateTimeAdd(utcNowValue, 'P90D'))
    }
  }
}

output namespaceName string = serviceBusNamespace.name
output fraudAlertsQueueName string = fraudAlertsQueue.name
output reviewQueueName string = reviewQueue.name
