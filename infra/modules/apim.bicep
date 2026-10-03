// API Management, Consumption tier (first million calls per month free): the single
// entry point for the web apps. One API per service with pass-through operations and the
// shared gateway policy (apim-policy.xml): JWT validation, rate limit, correlation id.
param location string
param tags object
param name string
param publisherEmail string
param publisherName string = 'Chaski Bank'
@description('Backend base URLs: { cuentas, core, ia }.')
param backends object
param entraTenantId string
param entraAudience string
param workspaceId string

resource apim 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: name
  location: location
  tags: tags
  sku: { name: 'Consumption', capacity: 0 }
  identity: { type: 'SystemAssigned' }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

var policy = replace(replace(loadTextContent('apim-policy.xml'), '{tenant}', entraTenantId), '{audience}', entraAudience)
var methods = [ 'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS' ]
var apis = [
  { name: 'cuentas', display: 'Chaski Cuentas API', url: backends.cuentas }
  { name: 'core', display: 'Chaski Core API', url: backends.core }
  { name: 'ia', display: 'Chaski IA API', url: backends.ia }
]

resource api 'Microsoft.ApiManagement/service/apis@2024-05-01' = [for a in apis: {
  parent: apim
  name: a.name
  properties: {
    displayName: a.display
    path: a.name
    serviceUrl: a.url
    protocols: [ 'https' ]
    subscriptionRequired: false
    apiType: 'http'
  }
}]

// Pass-through operations: every route of the service, per HTTP method.
resource ops 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = [for i in range(0, length(apis) * length(methods)): {
  parent: api[i / length(methods)]
  name: toLower('${methods[i % length(methods)]}-all')
  properties: {
    displayName: '${methods[i % length(methods)]} /*'
    method: methods[i % length(methods)]
    urlTemplate: '/*'
  }
}]

resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = [for (a, i) in apis: {
  parent: api[i]
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: policy
  }
  dependsOn: [ ops ]
}]

resource diag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-log-analytics'
  scope: apim
  properties: {
    workspaceId: workspaceId
    logs: [ { categoryGroup: 'allLogs', enabled: true } ]
  }
}

output name string = apim.name
output gatewayUrl string = apim.properties.gatewayUrl
