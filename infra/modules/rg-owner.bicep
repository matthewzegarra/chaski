// Owner on this resource group only, for the GitHub IaC identity: the Bicep creates role
// assignments and a custom role inside rg-chaski, which Contributor cannot do.
param principalId string

var owner = '8e3af657-a8ff-443c-a75c-2fe8c4bcb635'

resource ownerOnRg 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, principalId, owner)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', owner)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
