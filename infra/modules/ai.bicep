// Azure OpenAI (gpt-5-mini, GlobalStandard), Content Safety (F0) and Document
// Intelligence (F0). Keys disabled: ia-api authenticates with its managed identity.
param location string
param tags object
param prefix string
param suffix string
param acaSubnetId string
param deployerIp string
param iaPrincipalId string
param modelName string = 'gpt-5-mini'
param modelVersion string = '2025-08-07'
@description('Capacity in thousands of tokens per minute.')
param modelCapacity int = 30

var openAiUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var cognitiveUser = 'a97b65f3-24c7-4388-baec-2e87135dc908'

var networkAcls = {
  defaultAction: 'Deny'
  ipRules: empty(deployerIp) ? [] : [ { value: deployerIp } ]
  virtualNetworkRules: [ { id: acaSubnetId, ignoreMissingVnetServiceEndpoint: false } ]
}

resource aoai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'oai-${prefix}-${suffix}'
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: 'oai-${prefix}-${suffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    networkAcls: networkAcls
  }
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aoai
  name: modelName
  sku: { name: 'GlobalStandard', capacity: modelCapacity }
  properties: {
    model: { format: 'OpenAI', name: modelName, version: modelVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource safety 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'cs-${prefix}-${suffix}'
  location: location
  tags: tags
  kind: 'ContentSafety'
  sku: { name: 'F0' }
  properties: {
    customSubDomainName: 'cs-${prefix}-${suffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    networkAcls: networkAcls
  }
}

resource docintel 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'di-${prefix}-${suffix}'
  location: location
  tags: tags
  kind: 'FormRecognizer'
  sku: { name: 'F0' }
  properties: {
    customSubDomainName: 'di-${prefix}-${suffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    networkAcls: networkAcls
  }
}

resource roleAoai 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aoai.id, iaPrincipalId, openAiUser)
  scope: aoai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUser)
    principalId: iaPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource roleSafety 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(safety.id, iaPrincipalId, cognitiveUser)
  scope: safety
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveUser)
    principalId: iaPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource roleDocintel 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(docintel.id, iaPrincipalId, cognitiveUser)
  scope: docintel
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveUser)
    principalId: iaPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output openAiEndpoint string = aoai.properties.endpoint
output openAiDeployment string = deployment.name
output contentSafetyEndpoint string = safety.properties.endpoint
output docIntelEndpoint string = docintel.properties.endpoint
