// Key Vault: RBAC only, purge protection, network deny by default.
// Reachable from the Container Apps subnet (service endpoint), from ARM template
// deployments (trusted services) and from the deployer's IP to seed secrets.
param location string
param tags object
param name string
param acaSubnetId string
param workspaceId string
param deployerIp string
param deployerObjectId string
@description('Principal ids that read secrets (Key Vault Secrets User).')
param readerPrincipalIds array

var secretsUser = '4633458b-17de-408a-b874-0445c86b69e6'
var secretsOfficer = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: true
    enabledForTemplateDeployment: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      ipRules: empty(deployerIp) ? [] : [ { value: deployerIp } ]
      virtualNetworkRules: [ { id: acaSubnetId, ignoreMissingVnetServiceEndpoint: false } ]
    }
  }
}

resource readers 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for p in readerPrincipalIds: {
  name: guid(kv.id, p, secretsUser)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsUser)
    principalId: p
    principalType: 'ServicePrincipal'
  }
}]

resource officer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, deployerObjectId, secretsOfficer)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsOfficer)
    principalId: deployerObjectId
    principalType: 'User'
  }
}

resource diag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-log-analytics'
  scope: kv
  properties: {
    workspaceId: workspaceId
    logs: [ { categoryGroup: 'audit', enabled: true } ]
  }
}

output name string = kv.name
output uri string = kv.properties.vaultUri
