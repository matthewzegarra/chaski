// ADLS Gen2 for the data lake (bronze/silver/gold/quarantine) and KYC images.
// Entra ID only (no shared keys), TLS 1.2, no public blobs, network deny by default.
param location string
param tags object
param name string
param acaSubnetId string
param workspaceId string
param deployerIp string
param pipelinePrincipalId string
param corePrincipalId string

var blobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var containers = [ 'bronze', 'silver', 'gold', 'quarantine', 'kyc' ]

resource st 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      ipRules: empty(deployerIp) ? [] : [ { value: deployerIp, action: 'Allow' } ]
      virtualNetworkRules: [ { id: acaSubnetId, action: 'Allow' } ]
    }
  }
}

resource blob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: st
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

resource cont 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for c in containers: {
  parent: blob
  name: c
  properties: { publicAccess: 'None' }
}]

// Pipeline writes the whole lake; core-api only the kyc container.
resource pipelineRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(st.id, pipelinePrincipalId, blobDataContributor)
  scope: st
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributor)
    principalId: pipelinePrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource kycContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' existing = {
  parent: blob
  name: 'kyc'
}

resource coreRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(st.id, 'kyc', corePrincipalId, blobDataContributor)
  scope: kycContainer
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributor)
    principalId: corePrincipalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [ cont ]
}

resource diag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-log-analytics'
  scope: blob
  properties: {
    workspaceId: workspaceId
    logs: [
      { category: 'StorageWrite', enabled: true }
      { category: 'StorageDelete', enabled: true }
    ]
  }
}

output name string = st.name
output blobEndpoint string = st.properties.primaryEndpoints.blob
