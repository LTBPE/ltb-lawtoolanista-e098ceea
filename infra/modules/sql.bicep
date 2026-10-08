@description('Azure region')
param location string

@description('SQL Server name (must be globally unique)')
param serverName string

@description('Database name')
param databaseName string = 'court-monitor'

@description('SQL admin login')
param adminLogin string

@description('SQL admin password')
@secure()
param adminPassword string

@description('Optional: Microsoft Entra admin login (UPN or group name) for this SQL server. Leave empty to skip — additive, no behavior change if unset.')
param aadAdminLogin string = ''

@description('Optional: Microsoft Entra object ID matching aadAdminLogin. Leave empty to skip.')
param aadAdminObjectId string = ''

@description('Optional: additional named IP ranges to allow (e.g. office/VPN egress IPs), on top of the AllowAzureServices rule. Each item: {name, startIp, endIp}.')
param allowedClientIpRanges array = []

// SOC2 hardening (2026-10-08): publicNetworkAccess stays 'Enabled' and the
// AllowAzureServices rule below is intentionally kept. This server backs a
// Function App on a Consumption (Y1) plan, which cannot use VNet Integration /
// Private Endpoint to reach SQL privately without a plan-tier upgrade to
// Premium (Elastic Premium) — see SOC2 Risk Register R-014/R-015 for the
// equivalent storage-account constraint. Tracked as an accepted risk pending
// that plan decision. Do not flip publicNetworkAccess to 'Disabled' or remove
// AllowAzureServices without first confirming the Function App has a private
// network path to this server, or the app will lose database connectivity.
resource sqlServer 'Microsoft.Sql/servers@2023-02-01-preview' = {
  name: serverName
  location: location
  properties: {
    administratorLogin: adminLogin
    administratorLoginPassword: adminPassword
    version: '12.0'
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

// Allow Azure services to connect. Note: startIp/endIp = 0.0.0.0 is Azure's
// special sentinel for "allow Azure-hosted resources," not a literal open-to-
// the-internet rule — but it does allow any Azure resource in any tenant with
// valid SQL credentials to attempt a connection, which is broader than ideal.
resource allowAzureServices 'Microsoft.Sql/servers/firewallRules@2023-02-01-preview' = {
  parent: sqlServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

@batchSize(1)
resource clientIpFirewallRules 'Microsoft.Sql/servers/firewallRules@2023-02-01-preview' = [for range in allowedClientIpRanges: {
  parent: sqlServer
  name: range.name
  properties: {
    startIpAddress: range.startIp
    endIpAddress: range.endIp
  }
}]

resource aadAdmin 'Microsoft.Sql/servers/administrators@2023-02-01-preview' = if (!empty(aadAdminObjectId)) {
  parent: sqlServer
  name: 'ActiveDirectory'
  properties: {
    administratorType: 'ActiveDirectory'
    login: aadAdminLogin
    sid: aadAdminObjectId
    tenantId: subscription().tenantId
  }
}

resource sqlDatabase 'Microsoft.Sql/servers/databases@2023-02-01-preview' = {
  parent: sqlServer
  name: databaseName
  location: location
  sku: {
    name: 'Basic'
    tier: 'Basic'
    capacity: 5
  }
  properties: {
    collation: 'SQL_Latin1_General_CP1_CI_AS'
    maxSizeBytes: 2147483648  // 2 GB
    zoneRedundant: false
    readScale: 'Disabled'
    requestedBackupStorageRedundancy: 'Local'
  }
}

var connectionString = 'Driver={ODBC Driver 18 for SQL Server};Server=tcp:${sqlServer.properties.fullyQualifiedDomainName},1433;Database=${databaseName};Uid=${adminLogin};Pwd=${adminPassword};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'

output serverFqdn string = sqlServer.properties.fullyQualifiedDomainName
output databaseName string = sqlDatabase.name
output connectionString string = connectionString
