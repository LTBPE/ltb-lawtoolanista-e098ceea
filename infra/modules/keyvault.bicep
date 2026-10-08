@description('Azure region')
param location string

@description('Key Vault name (must be globally unique, 3-24 chars)')
param keyVaultName string

@description('Anthropic API key')
@secure()
param anthropicApiKey string = ''

@description('Microsoft Graph client secret')
@secure()
param graphClientSecret string = ''

@description('Azure SQL connection string')
@secure()
param sqlConnectionString string = ''

@description('Function App managed identity principal ID (for access policy)')
param functionAppPrincipalId string = ''

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enabledForTemplateDeployment: true
    publicNetworkAccess: 'Enabled'
    // SOC2 hardening (2026-10-08): defaultAction changed from 'Allow' to 'Deny'.
    // Safe because this Key Vault is only read via App Service "Key Vault reference"
    // app settings (@Microsoft.KeyVault(SecretUri=...)) in functionapp.bicep, which
    // Azure resolves platform-side and is covered by the AzureServices bypass. If a
    // future change has app code call the Key Vault SDK directly at runtime instead
    // of via app-setting references, this will need a Private Endpoint or VNet rule.
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
  }
}

resource anthropicSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(anthropicApiKey)) {
  parent: keyVault
  name: 'anthropic-api-key'
  properties: {
    value: anthropicApiKey
    attributes: {
      enabled: true
    }
  }
}

resource graphSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(graphClientSecret)) {
  parent: keyVault
  name: 'graph-client-secret'
  properties: {
    value: graphClientSecret
    attributes: {
      enabled: true
    }
  }
}

resource sqlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(sqlConnectionString)) {
  parent: keyVault
  name: 'sql-connection-string'
  properties: {
    value: sqlConnectionString
    attributes: {
      enabled: true
    }
  }
}

// Grant Function App managed identity read access to secrets
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource functionAppKvAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(functionAppPrincipalId)) {
  name: guid(keyVault.id, functionAppPrincipalId, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      keyVaultSecretsUserRoleId
    )
    principalId: functionAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
output anthropicApiKeySecretUri string = !empty(anthropicApiKey) ? anthropicSecret.properties.secretUri : ''
output graphClientSecretSecretUri string = !empty(graphClientSecret) ? graphSecret.properties.secretUri : ''
output sqlConnectionStringSecretUri string = !empty(sqlConnectionString) ? sqlSecret.properties.secretUri : ''
