@description('Azure OpenAI account name')
param accountName string

@description('Azure region')
param location string

@description('Resource tags')
param tags object

@description('Key Vault name for storing the API key secret')
param keyVaultName string

@description('Production flag — enables higher capacity and zone redundancy')
param isProduction bool

resource openAI 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: isProduction ? 'S0' : 'S0'
  }
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: isProduction ? 'Disabled' : 'Enabled'
    networkAcls: {
      defaultAction: isProduction ? 'Deny' : 'Allow'
    }
  }
}

resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openAI
  name: 'gpt-4o'
  sku: {
    name: 'GlobalStandard'
    capacity: isProduction ? 100 : 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-11-20'
    }
  }
}

resource kvRef 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource openAIKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kvRef
  name: 'azure-openai-api-key'
  properties: {
    value: openAI.listKeys().key1
  }
}

output endpoint string = openAI.properties.endpoint
output id string = openAI.id
