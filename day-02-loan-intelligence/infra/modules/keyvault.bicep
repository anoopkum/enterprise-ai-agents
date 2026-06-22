@description('Key Vault name')
param name string

@description('Azure region')
param location string

@description('Resource tags')
param tags object

@description('Azure AD Object ID for admin role assignment')
param adminObjectId string

@description('Production flag — enables soft delete purge protection')
param isProduction bool

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: isProduction ? 90 : 7
    enablePurgeProtection: isProduction ? true : null
    networkAcls: {
      defaultAction: isProduction ? 'Deny' : 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource adminRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, adminObjectId, 'Key Vault Administrator')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '00482a5a-887f-4fb3-b363-3b7fe8e74483')
    principalId: adminObjectId
    principalType: 'User'
  }
}

output id string = keyVault.id
output name string = keyVault.name
output uri string = keyVault.properties.vaultUri
