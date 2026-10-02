// API Management, Consumption tier (first million calls per month free). APIs and the
// validate-jwt / rate-limit / CORS policies are added in the deployment phase.
param location string
param tags object
param name string
param publisherEmail string
param publisherName string = 'Chaski Bank'

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

output name string = apim.name
output gatewayUrl string = apim.properties.gatewayUrl
