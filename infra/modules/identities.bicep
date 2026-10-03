// One user-assigned managed identity per workload, plus one for GitHub Actions (OIDC).
// The GitHub identity trusts only this repository's deployment environments.
param location string
param tags object
param prefix string
param githubRepo string
@description('OIDC subject prefix. Repos with immutable-ID subjects use repo:<owner>@<ownerId>/<repo>@<repoId>.')
param githubSubjectPrefix string = 'repo:${githubRepo}'
param githubEnvironments array = [ 'build', 'dev', 'test', 'prod' ]

var workloads = [ 'cuentas', 'core', 'ia', 'web', 'pipeline' ]

resource ids 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = [for w in workloads: {
  name: 'id-${prefix}-${w}'
  location: location
  tags: tags
}]

resource github 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${prefix}-github'
  location: location
  tags: tags
}

// Federated credentials on one identity must be created one at a time.
@batchSize(1)
resource fic 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = [for e in githubEnvironments: {
  parent: github
  name: 'gh-${e}'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: '${githubSubjectPrefix}:environment:${e}'
    audiences: [ 'api://AzureADTokenExchange' ]
  }
}]

// Order matches `workloads`.
output identities object = {
  cuentas: { id: ids[0].id, principalId: ids[0].properties.principalId, clientId: ids[0].properties.clientId }
  core: { id: ids[1].id, principalId: ids[1].properties.principalId, clientId: ids[1].properties.clientId }
  ia: { id: ids[2].id, principalId: ids[2].properties.principalId, clientId: ids[2].properties.clientId }
  web: { id: ids[3].id, principalId: ids[3].properties.principalId, clientId: ids[3].properties.clientId }
  pipeline: { id: ids[4].id, principalId: ids[4].properties.principalId, clientId: ids[4].properties.clientId }
}
output github object = {
  id: github.id
  principalId: github.properties.principalId
  clientId: github.properties.clientId
}
