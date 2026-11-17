@description('Candidate lab region; confirm support and cost before deployment.')
param location string
@minLength(3)
@maxLength(12)
param prefix string
@secure()
param sshPublicKey string
param administrator string = 'laboperator'
@description('Exact Ubuntu image version observed in the approved region; do not use latest.')
param vmImageVersion string
param chatModel string
param chatVersion string
param chatSku string
@minValue(1)
param chatCapacity int
param embeddingModel string = 'text-embedding-3-large'
param embeddingVersion string = '1'
param embeddingSku string
@minValue(1)
param embeddingCapacity int
@description('Explicitly approved platform/package FQDN exceptions; never use *.')
param approvedFqdns array
param vnetPrefix string = '10.74.0.0/16'
param agentPrefix string = '10.74.0.0/24'
param pePrefix string = '10.74.1.0/24'
param adminPrefix string = '10.74.2.0/24'
param firewallPrefix string = '10.74.3.0/26'
param bastionPrefix string = '10.74.4.0/26'
param outsidePrefix string = '10.75.0.0/16'
param outsideSubnetPrefix string = '10.75.0.0/24'

module network 'network.bicep' = {
  name: '${prefix}-network'
  params: {
    location: location
    prefix: prefix
    sshPublicKey: sshPublicKey
    administrator: administrator
    vmImageVersion: vmImageVersion
    approvedFqdns: approvedFqdns
    vnetPrefix: vnetPrefix
    agentPrefix: agentPrefix
    pePrefix: pePrefix
    adminPrefix: adminPrefix
    firewallPrefix: firewallPrefix
    bastionPrefix: bastionPrefix
    outsidePrefix: outsidePrefix
    outsideSubnetPrefix: outsideSubnetPrefix
  }
}
module standard 'standard/main.bicep' = {
  name: '${prefix}-standard'
  params: {
    location: location
    aiServices: prefix
    firstProjectName: 'lab'
    projectDescription: 'Disposable private Foundry IQ verification lab'
    existingVnetResourceId: network.outputs.vnetId
    reuseExistingSubnets: true
    agentSubnetName: 'agents'
    peSubnetName: 'endpoints'
    disableLocalAuth: true
    enableContainerRegistry: true
    developerIpCidr: ''
    modelName: chatModel
    modelVersion: chatVersion
    modelSkuName: chatSku
    modelCapacity: chatCapacity
  }
}
// A nested deployment makes the Standard outputs available as resource-name parameters.
module knowledge 'knowledge-resources.bicep' = {
  name: '${prefix}-knowledge'
  params: {
    accountName: standard.outputs.deployedAccountName
    searchName: standard.outputs.searchName
    storageName: standard.outputs.storageName
    embeddingModel: embeddingModel
    embeddingVersion: embeddingVersion
    embeddingSku: embeddingSku
    embeddingCapacity: embeddingCapacity
  }
}
output config object = {
  project_endpoint: '${knowledge.outputs.accountEndpoint}/api/projects/${standard.outputs.deployedProjectName}'
  project_resource_id: standard.outputs.projectId
  search_endpoint: knowledge.outputs.searchEndpoint
  storage_endpoint: knowledge.outputs.storageEndpoint
  storage_resource_id: knowledge.outputs.storageResourceId
  openai_endpoint: knowledge.outputs.openaiEndpoint
  chat_deployment: chatModel
  chat_model: chatModel
  embedding_deployment: knowledge.outputs.embeddingDeployment
  embedding_model: embeddingModel
  container: knowledge.outputs.containerName
  folder: 'fixtures'
  source: 'grid-policy-ks'
  knowledge_base: 'contoso-grid-kb'
  prompt_connection: 'grid-prompt-mi'
  hosted_connection: 'grid-hosted-identity'
  prompt_agent: 'grid-prompt'
  toolbox: 'grid-knowledge'
}
output acrName string = standard.outputs.registryName
output projectPrincipalId string = standard.outputs.projectPrincipalId
output network object = network.outputs.inventory
