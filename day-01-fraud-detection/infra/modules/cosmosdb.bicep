param accountName string
param location string
param tags object
param keyVaultName string

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-02-15-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: true
      }
    ]
    enableAutomaticFailover: true
    enableMultipleWriteLocations: false
    publicNetworkAccess: 'Disabled'
    networkAclBypass: 'AzureServices'
    disableKeyBasedMetadataWriteAccess: true
  }
}

resource fraudDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-02-15-preview' = {
  parent: cosmosAccount
  name: 'frauddb'
  properties: {
    resource: { id: 'frauddb' }
    options: { autoscaleSettings: { maxThroughput: 4000 } }
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
      defaultTtl: 7776000  // 90 days
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
      defaultTtl: 31536000  // 1 year audit retention
    }
  }
}

// Store connection string in Key Vault
resource cosmosSecretPrimary 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  name: '${keyVaultName}/cosmos-connection-string'
  properties: {
    value: cosmosAccount.listConnectionStrings().connectionStrings[0].connectionString
  }
}

output endpoint string = cosmosAccount.properties.documentEndpoint
output accountName string = cosmosAccount.name
