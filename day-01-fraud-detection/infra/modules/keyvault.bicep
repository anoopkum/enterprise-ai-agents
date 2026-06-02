param name string
param location string
param tags object
param adminObjectId string
param isProduction bool

// Dev: soft-delete 7 days (minimum), purge protection off (allows manual cleanup)
// Prod: soft-delete 90 days, purge protection on (compliance requirement)
var softDeleteRetentionDays = isProduction ? 90 : 7
var enablePurgeProtection = isProduction  // false in dev = can delete+recreate freely

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'  // Same SKU both envs — standard is cheapest
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: softDeleteRetentionDays
    enablePurgeProtection: enablePurgeProtection
    // Dev: public access to avoid private endpoint cost; Prod: locked down
    publicNetworkAccess: isProduction ? 'Disabled' : 'Enabled'
    networkAcls: isProduction ? {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
    } : {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource adminRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, adminObjectId, 'Key Vault Administrator')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '00482a5a-887f-4fb3-b363-3b7fe8e74483'  // Key Vault Administrator
    )
    principalId: adminObjectId
    principalType: 'User'
  }
}

output id string = keyVault.id
output name string = keyVault.name
output uri string = keyVault.properties.vaultUri
