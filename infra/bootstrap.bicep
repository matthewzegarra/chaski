// Bootstrap of the GitHub IaC identity (id-<prefix>-github-infra), applied ONCE by a person
// with Owner on the subscription, after main.bicep has created the identity:
//
//   ./infra/scripts/deploy.ps1 -Stage bootstrap
//
// It is kept out of main.bicep on purpose: the identity that applies main.bicep from GitHub
// must not be able to grant permissions to itself.
//   - subscription: custom role limited to deployments and the resource group
//   - rg-chaski:    Owner (the Bicep creates role assignments and custom roles inside it)
targetScope = 'subscription'

param resourceGroupName string = 'rg-chaski'
param prefix string = 'chaski'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' existing = {
  name: resourceGroupName
}

resource iacIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  scope: rg
  name: 'id-${prefix}-github-infra'
}

resource iacRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(subscription().id, 'chaski-iac-deployer')
  properties: {
    roleName: 'CHASKI IaC deployer (subscription deployments)'
    description: 'Create subscription-scoped deployments and the CHASKI resource group.'
    type: 'CustomRole'
    assignableScopes: [ subscription().id ]
    permissions: [
      {
        actions: [
          'Microsoft.Resources/deployments/*'
          'Microsoft.Resources/subscriptions/read'
          'Microsoft.Resources/subscriptions/resourceGroups/read'
          'Microsoft.Resources/subscriptions/resourceGroups/write'
        ]
      }
    ]
  }
}

resource iacOnSubscription 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, 'id-${prefix}-github-infra', iacRole.id)
  properties: {
    roleDefinitionId: iacRole.id
    principalId: iacIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

module iacOnRg 'modules/rg-owner.bicep' = {
  scope: rg
  name: 'iac-rg-owner'
  params: { principalId: iacIdentity.properties.principalId }
}
