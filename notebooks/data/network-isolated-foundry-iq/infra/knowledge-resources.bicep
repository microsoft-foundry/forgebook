param accountName string
param searchName string
param storageName string
param embeddingModel string
param embeddingVersion string
param embeddingSku string
@minValue(1)
param embeddingCapacity int
param blobContainerName string = 'grid-policies'

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}
resource search 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: searchName
}
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageName
}
resource embeddings 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: account
  name: embeddingModel
  sku: {
    name: embeddingSku
    capacity: embeddingCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModel
      version: embeddingVersion
    }
  }
}
resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  name: '${storage.name}/default/${blobContainerName}'
  properties: { publicAccess: 'None' }
}
resource blobLink 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2025-05-01' = {
  parent: search
  name: 'blob-ingestion'
  properties: {
    privateLinkResourceId: storage.id
    groupId: 'blob'
    requestMessage: 'Disposable lab: native private Blob ingestion'
  }
}
resource modelLink 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2025-05-01' = {
  parent: search
  name: 'private-models'
  properties: {
    privateLinkResourceId: account.id
    groupId: 'openai_account'
    requestMessage: 'Disposable lab: private embeddings and KB planning'
  }
}
// Search's system identity, not the notebook or project identity, performs ingestion.
resource blobReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(container.id, search.id, 'reader')
  scope: container
  properties: {
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
    )
  }
}
resource modelUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, search.id, 'model-user')
  scope: account
  properties: {
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'a97b65f3-24c7-4388-baec-2e87135dc908'
    )
  }
}

output accountEndpoint string = 'https://${account.name}.services.ai.azure.com'
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output storageEndpoint string = storage.properties.primaryEndpoints.blob
output storageResourceId string = storage.id
output openaiEndpoint string = 'https://${account.name}.openai.azure.com'
output embeddingDeployment string = embeddings.name
output containerName string = blobContainerName
