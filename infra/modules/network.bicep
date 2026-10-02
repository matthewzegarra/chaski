// Virtual network: one subnet for Container Apps, one delegated to PostgreSQL.
// Data services are reached through free service endpoints instead of Private Endpoints
// (each Private Endpoint costs ~USD 7/month); see docs/DECISIONS.md.
param location string
param tags object
param prefix string

var addressSpace = '10.40.0.0/16'

resource nsgAca 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-${prefix}-aca'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource nsgPg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-${prefix}-pg'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'allow-postgres-from-aca'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.40.0.0/23'
          sourcePortRange: '*'
          destinationAddressPrefix: '10.40.2.0/24'
          destinationPortRange: '5432'
        }
      }
      {
        name: 'deny-vnet-inbound'
        properties: {
          priority: 4000
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${prefix}'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: [ addressSpace ] }
    subnets: [
      {
        name: 'snet-aca'
        properties: {
          addressPrefix: '10.40.0.0/23'
          networkSecurityGroup: { id: nsgAca.id }
          delegations: [
            { name: 'aca', properties: { serviceName: 'Microsoft.App/environments' } }
          ]
          serviceEndpoints: [
            { service: 'Microsoft.KeyVault' }
            { service: 'Microsoft.Storage' }
            { service: 'Microsoft.Sql' }
            { service: 'Microsoft.CognitiveServices' }
          ]
        }
      }
      {
        name: 'snet-pg'
        properties: {
          addressPrefix: '10.40.2.0/24'
          networkSecurityGroup: { id: nsgPg.id }
          delegations: [
            { name: 'pg', properties: { serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers' } }
          ]
        }
      }
    ]
  }
}

// Private DNS zone required by PostgreSQL Flexible Server with VNet integration.
resource pgDns 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: '${prefix}.private.postgres.database.azure.com'
  location: 'global'
  tags: tags
}

resource pgDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: pgDns
  name: 'link-${vnet.name}'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet.id }
  }
}

output vnetId string = vnet.id
output acaSubnetId string = vnet.properties.subnets[0].id
output pgSubnetId string = vnet.properties.subnets[1].id
output pgDnsZoneId string = pgDns.id
