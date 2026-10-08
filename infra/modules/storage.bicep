@description('Azure region')
param location string

@description('Storage account name (must be globally unique, 3-24 lowercase alphanum)')
param storageAccountName string

@description('Blob container name for page snapshots')
param blobContainerName string = 'court-snapshots'

@description('Queue name for crawl jobs')
param crawlQueueName string = 'crawl-queue'

@description('Queue name for analysis jobs')
param analyzeQueueName string = 'analyze-queue'

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    // SOC2 note (2026-10-08): defaultAction is intentionally left 'Allow'.
    // This account is AzureWebJobsStorage for a Function App on a Consumption
    // (Y1) plan. Consumption plans can't use VNet Integration/Private Endpoint
    // to reach the Functions host's own storage account, so setting
    // defaultAction to 'Deny' here would break the Function App outright
    // (confirmed against an equivalent account in production, see SOC2 Risk
    // Register R-014/R-015). Locking this down requires first moving the
    // Function App to a Premium (Elastic Premium) plan.
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource blobContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: blobContainerName
  properties: {
    publicAccess: 'None'
  }
}

resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource crawlQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-01-01' = {
  parent: queueService
  name: crawlQueueName
}

resource analyzeQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-01-01' = {
  parent: queueService
  name: analyzeQueueName
}

var storageConnectionString = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=core.windows.net'

output storageAccountName string = storageAccount.name
output connectionString string = storageConnectionString
output resourceId string = storageAccount.id
