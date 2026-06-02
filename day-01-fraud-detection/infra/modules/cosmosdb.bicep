param accountName string
param location string
param tags object
param keyVaultName string
param isProduction bool
param utcNowValue string = utcNow()

// Dev/Staging: 400 RU manual, no zone-redundancy, no failover → ~$60/mo
// Prod:        4000 RU autoscale, zone-redundant, auto-failover → ~$1,100/mo
var zoneRedundant = isProduction
var enableAutomaticFailover = isProduction
var backupPolicy = isProduction ? {
  type: 'Periodic'
  periodicModeProperties: {
    backupIntervalInMinutes: 240
    backupRetentionIntervalInHours: 720
    backupStorageRedundancy: 'Geo'
  }
} : {
  type: 'Periodic'
  periodicModeProperties: {
    backupIntervalInMinutes: 1440  // Daily backup in dev
    backupRetentionIntervalInHours: 48
    backupStorageRedundancy: 'Local'
  }
}

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-02-15-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: {
      defaultConsistencyLevel: isProduction ? 'Session' : 'Eventual'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: zoneRedundant
      }
    ]
    enableAutomaticFailover: enableAutomaticFailover
    enableMultipleWriteLocations: false
    // Dev uses public access to avoid private endpoint cost (~$7/mo each)
    publicNetworkAccess: isProduction ? 'Disabled' : 'Enabled'
    networkAclBypass: 'AzureServices'
    disableKeyBasedMetadataWriteAccess: true
    backupPolicy: backupPolicy
  }
}

resource fraudDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-02-15-preview' = {
  parent: cosmosAccount
  name: 'frauddb'
  properties: {
    resource: { id: 'frauddb' }
    options: isProduction ? {
      autoscaleSettings: { maxThroughput: 4000 }
    } : {
      throughput: 400
    }
  }
}

resource transactionsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: fraudDb
  name: 'transactions'
  properties: {
    resource: {
      id: 'transactions'
      partitionKey: { paths: ['/customer_id'], kind: 'Hash' }
      indexingPolicy: {
        indexingMode: 'consistent'
        includedPaths: [{ path: '/customer_id/?' }, { path: '/timestamp/?' }, { path: '/status/?' }]
        excludedPaths: [{ path: '/*' }]
      }
      defaultTtl: isProduction ? 7776000 : 604800  // Prod: 90d | Dev: 7d
    }
  }
}

resource blacklistsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: fraudDb
  name: 'blacklists'
  properties: {
    resource: {
      id: 'blacklists'
      partitionKey: { paths: ['/type'], kind: 'Hash' }
      defaultTtl: -1
    }
  }
}

resource decisionsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: fraudDb
  name: 'decisions'
  properties: {
    resource: {
      id: 'decisions'
      partitionKey: { paths: ['/transaction_id'], kind: 'Hash' }
      defaultTtl: isProduction ? 31536000 : 604800  // Prod: 1yr | Dev: 7d
    }
  }
}

resource cosmosSecretPrimary 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  name: '${keyVaultName}/cosmos-connection-string'
  properties: {
    value: cosmosAccount.listConnectionStrings().connectionStrings[0].connectionString
    attributes: {
      enabled: true
      // Secret expiry: 90 days in dev to prompt rotation, 1yr in prod
      exp: isProduction
        ? dateTimeToEpoch(dateTimeAdd(utcNowValue, 'P1Y'))
        : dateTimeToEpoch(dateTimeAdd(utcNowValue, 'P90D'))
    }
  }
}

output endpoint string = cosmosAccount.properties.documentEndpoint
output accountName string = cosmosAccount.name
