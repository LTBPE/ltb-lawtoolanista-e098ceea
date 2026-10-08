@description('Deployment environment name')
param environment string = 'prod'

@description('Azure region for all resources')
param location string = 'westus2'

@description('SQL Server admin login name')
param sqlAdminLogin string = 'courtmonitor-admin'

@description('SQL Server admin password - set at deploy time')
@secure()
param sqlAdminPassword string

@description('Anthropic API key for Claude AI')
@secure()
param anthropicApiKey string = ''

@description('Microsoft Graph tenant ID')
param graphTenantId string = ''

@description('Microsoft Graph client ID')
param graphClientId string = ''

@description('Microsoft Graph client secret')
@secure()
param graphClientSecret string = ''

@description('Optional: Microsoft Entra admin login for the SQL server. Leave empty to skip.')
param sqlAadAdminLogin string = ''

@description('Optional: Microsoft Entra object ID for the SQL AAD admin. Leave empty to skip.')
param sqlAadAdminObjectId string = ''

@description('Optional: additional IP ranges allowed through the SQL server firewall (e.g. office/VPN egress). Each item: {name, startIp, endIp}.')
param sqlAllowedClientIpRanges array = []

var prefix = 'ltbla'
var uniqueSuffix = uniqueString(resourceGroup().id, environment)
var resourcePrefix = '${prefix}-${environment}'

// Storage Account
module storage 'modules/storage.bicep' = {
  name: 'storage-${environment}'
  params: {
    location: location
    storageAccountName: '${prefix}${environment}${take(uniqueSuffix, 8)}'
    blobContainerName: 'court-snapshots'
    crawlQueueName: 'crawl-queue'
    analyzeQueueName: 'analyze-queue'
  }
}

// Azure SQL
module sql 'modules/sql.bicep' = {
  name: 'sql-${environment}'
  params: {
    location: location
    serverName: '${resourcePrefix}-sql-${take(uniqueSuffix, 8)}'
    databaseName: 'ltb-lawtoolanista'
    adminLogin: sqlAdminLogin
    adminPassword: sqlAdminPassword
    aadAdminLogin: sqlAadAdminLogin
    aadAdminObjectId: sqlAadAdminObjectId
    allowedClientIpRanges: sqlAllowedClientIpRanges
  }
}

// Key Vault
module keyvault 'modules/keyvault.bicep' = {
  name: 'keyvault-${environment}'
  params: {
    location: location
    keyVaultName: '${prefix}${take(uniqueSuffix, 10)}'
    anthropicApiKey: anthropicApiKey
    graphClientSecret: graphClientSecret
    sqlConnectionString: sql.outputs.connectionString
  }
}

// Static Web App (frontend)
module staticwebapp 'modules/staticwebapp.bicep' = {
  name: 'staticwebapp-${environment}'
  params: {
    location: location
    staticWebAppName: '${resourcePrefix}-frontend'
  }
}

// Function App
module functionapp 'modules/functionapp.bicep' = {
  name: 'functionapp-${environment}'
  params: {
    location: location
    functionAppName: '${resourcePrefix}-func-${take(uniqueSuffix, 8)}'
    storageAccountName: storage.outputs.storageAccountName
    storageConnectionString: storage.outputs.connectionString
    keyVaultName: keyvault.outputs.keyVaultName
    anthropicApiKeySecretUri: keyvault.outputs.anthropicApiKeySecretUri
    graphClientSecretSecretUri: keyvault.outputs.graphClientSecretSecretUri
    sqlConnectionStringSecretUri: keyvault.outputs.sqlConnectionStringSecretUri
    graphTenantId: graphTenantId
    graphClientId: graphClientId
    frontendUrl: staticwebapp.outputs.defaultHostname
  }
}

// Grant Function App identity access to Key Vault
module keyvaultAccess 'modules/keyvault.bicep' = {
  name: 'keyvault-access-${environment}'
  params: {
    location: location
    keyVaultName: keyvault.outputs.keyVaultName
    anthropicApiKey: anthropicApiKey
    graphClientSecret: graphClientSecret
    sqlConnectionString: sql.outputs.connectionString
    functionAppPrincipalId: functionapp.outputs.principalId
  }
}

output functionAppUrl string = functionapp.outputs.defaultHostname
output staticWebAppUrl string = staticwebapp.outputs.defaultHostname
output keyVaultName string = keyvault.outputs.keyVaultName
output sqlServerFqdn string = sql.outputs.serverFqdn
