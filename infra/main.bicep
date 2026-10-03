// CHASKI infrastructure (Phase 2). Subscription scope: creates rg-chaski and everything
// inside it. Deployed in two stages by infra/scripts/deploy.ps1:
//   stage 1 (deployWorkloads=false): network, monitoring, identities, Key Vault,
//            storage, ACR, AI services
//   (the script then seeds the generated secrets into Key Vault)
//   stage 2 (deployWorkloads=true):  PostgreSQL, Azure SQL, Container Apps, APIM
targetScope = 'subscription'

@allowed([ 'westus', 'northcentralus', 'canadacentral', 'mexicocentral', 'chilecentral' ])
param location string = 'westus'
param resourceGroupName string = 'rg-chaski'
param environmentName string = 'dev'
param owner string
param prefix string = 'chaski'

param deployWorkloads bool = false
param usePlaceholderImages bool = true
param imageTag string = 'dev'
@allowed([ 'mock', 'azure' ])
param aiMode string = 'mock'

@description('Public IP of the person deploying (Key Vault/Storage/SQL/AI firewalls).')
param deployerIp string
@description('Object id of the person deploying (Key Vault Secrets Officer, SQL admin).')
param deployerObjectId string
param deployerUpn string

param githubRepo string = 'Matthewzegarra0312/chaski'
@description('GitHub OIDC subject prefix (this repo uses immutable owner/repo ids).')
param githubSubjectPrefix string = 'repo:Matthewzegarra0312@119908185/chaski@1401839661'
@description('Entra ID values from infra/entra/.out/entra.json (identity tenant).')
param entra object

var tags = {
  project: 'chaski'
  owner: owner
  env: environmentName
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

// Globally unique, stable per subscription + resource group.
var suffix = take(uniqueString(subscription().id, resourceGroupName), 6)
var kvName = 'kv-${prefix}-${suffix}'
var apimName = 'apim-${prefix}-${suffix}'

module network 'modules/network.bicep' = {
  scope: rg
  name: 'network'
  params: { location: location, tags: tags, prefix: prefix }
}

module monitoring 'modules/monitoring.bicep' = {
  scope: rg
  name: 'monitoring'
  params: { location: location, tags: tags, prefix: prefix }
}

module identities 'modules/identities.bicep' = {
  scope: rg
  name: 'identities'
  params: { location: location, tags: tags, prefix: prefix, githubRepo: githubRepo, githubSubjectPrefix: githubSubjectPrefix }
}

module keyvault 'modules/keyvault.bicep' = {
  scope: rg
  name: 'keyvault'
  params: {
    location: location
    tags: tags
    name: kvName
    acaSubnetId: network.outputs.acaSubnetId
    workspaceId: monitoring.outputs.workspaceId
    deployerIp: deployerIp
    deployerObjectId: deployerObjectId
    readerPrincipalIds: [
      identities.outputs.identities.cuentas.principalId
      identities.outputs.identities.core.principalId
      identities.outputs.identities.ia.principalId
      identities.outputs.identities.pipeline.principalId
    ]
  }
}

module storage 'modules/storage.bicep' = {
  scope: rg
  name: 'storage'
  params: {
    location: location
    tags: tags
    name: 'st${prefix}${suffix}'
    acaSubnetId: network.outputs.acaSubnetId
    workspaceId: monitoring.outputs.workspaceId
    deployerIp: deployerIp
    pipelinePrincipalId: identities.outputs.identities.pipeline.principalId
    corePrincipalId: identities.outputs.identities.core.principalId
  }
}

module acr 'modules/acr.bicep' = {
  scope: rg
  name: 'acr'
  params: {
    location: location
    tags: tags
    name: 'acr${prefix}${suffix}'
    workspaceId: monitoring.outputs.workspaceId
    pullPrincipalIds: [
      identities.outputs.identities.cuentas.principalId
      identities.outputs.identities.core.principalId
      identities.outputs.identities.ia.principalId
      identities.outputs.identities.web.principalId
      identities.outputs.identities.pipeline.principalId
    ]
    pushPrincipalId: identities.outputs.github.principalId
  }
}

module ai 'modules/ai.bicep' = {
  scope: rg
  name: 'ai'
  params: {
    location: location
    tags: tags
    prefix: prefix
    suffix: suffix
    acaSubnetId: network.outputs.acaSubnetId
    deployerIp: deployerIp
    iaPrincipalId: identities.outputs.identities.ia.principalId
  }
}

// ---------------------------------------------------------------- stage 2
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  scope: rg
  name: kvName
}

module postgres 'modules/postgres.bicep' = if (deployWorkloads) {
  scope: rg
  name: 'postgres'
  params: {
    location: location
    tags: tags
    name: 'psql-${prefix}-${suffix}'
    subnetId: network.outputs.pgSubnetId
    privateDnsZoneId: network.outputs.pgDnsZoneId
    workspaceId: monitoring.outputs.workspaceId
    adminPassword: kv.getSecret('pg-admin-password')
  }
}

module sql 'modules/sql.bicep' = if (deployWorkloads) {
  scope: rg
  name: 'sql'
  params: {
    location: location
    tags: tags
    name: 'sql-${prefix}-${suffix}'
    acaSubnetId: network.outputs.acaSubnetId
    deployerIp: deployerIp
    adminLogin: deployerUpn
    adminObjectId: deployerObjectId
  }
}

module apps 'modules/containerapps.bicep' = if (deployWorkloads) {
  scope: rg
  name: 'containerapps'
  params: {
    location: location
    tags: tags
    prefix: prefix
    acaSubnetId: network.outputs.acaSubnetId
    workspaceId: monitoring.outputs.workspaceId
    keyVaultUri: keyvault.outputs.uri
    acrLoginServer: acr.outputs.loginServer
    identities: identities.outputs.identities
    githubPrincipalId: identities.outputs.github.principalId
    usePlaceholderImages: usePlaceholderImages
    imageTag: imageTag
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    aiMode: aiMode
    entra: entra
    blobEndpoint: storage.outputs.blobEndpoint
    githubRepo: githubRepo
    apiGatewayUrl: 'https://${apimName}.azure-api.net'
    openAi: {
      endpoint: ai.outputs.openAiEndpoint
      deployment: ai.outputs.openAiDeployment
      contentSafetyEndpoint: ai.outputs.contentSafetyEndpoint
      docIntelEndpoint: ai.outputs.docIntelEndpoint
    }
  }
  dependsOn: [ postgres ]
}

module apim 'modules/apim.bicep' = if (deployWorkloads) {
  scope: rg
  name: 'apim'
  params: {
    location: location
    tags: tags
    name: apimName
    publisherEmail: deployerUpn
    backends: {
      cuentas: apps!.outputs.urls.cuentasDev
      core: apps!.outputs.urls.core
      ia: apps!.outputs.urls.ia
    }
    entraTenantId: entra.tenantId
    entraAudience: entra.audience
    workspaceId: monitoring.outputs.workspaceId
  }
}

module alerts 'modules/alerts.bicep' = if (deployWorkloads) {
  scope: rg
  name: 'alerts'
  params: {
    tags: tags
    prefix: prefix
    alertEmail: deployerUpn
    appInsightsId: monitoring.outputs.appInsightsId
    workspaceId: monitoring.outputs.workspaceId
  }
}

output resourceGroup string = rg.name
output keyVaultName string = keyvault.outputs.name
output acrName string = acr.outputs.name
output acrLoginServer string = acr.outputs.loginServer
output postgresServerName string = 'psql-${prefix}-${suffix}'
output githubClientId string = identities.outputs.github.clientId
output urls object = deployWorkloads ? apps!.outputs.urls : {}
output apiGatewayUrl string = deployWorkloads ? apim!.outputs.gatewayUrl : ''
