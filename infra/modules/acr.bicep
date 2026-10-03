// Container registry (Basic). No admin user: workloads pull with their managed
// identity (AcrPull) and GitHub Actions pushes with OIDC (AcrPush).
param location string
param tags object
param name string
param workspaceId string
param pullPrincipalIds array
param pushPrincipalId string

var acrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var acrPush = '8311e382-0749-4cb8-b61a-304f252e45ec'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

resource pull 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for p in pullPrincipalIds: {
  name: guid(acr.id, p, acrPull)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPull)
    principalId: p
    principalType: 'ServicePrincipal'
  }
}]

resource push 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, pushPrincipalId, acrPush)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPush)
    principalId: pushPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource diag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-log-analytics'
  scope: acr
  properties: {
    workspaceId: workspaceId
    logs: [ { categoryGroup: 'audit', enabled: true } ]
  }
}

output name string = acr.name
output loginServer string = acr.properties.loginServer
