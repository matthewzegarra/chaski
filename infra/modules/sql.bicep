// Azure SQL for the analytical DW (gold). Free offer (serverless, auto-pause when the
// monthly free limit is used up, so it never bills). Entra ID authentication only.
param location string
param tags object
param name string
param acaSubnetId string
param deployerIp string
@description('Entra admin (user principal name) in the subscription tenant.')
param adminLogin string
param adminObjectId string

resource sql 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: name
  location: location
  tags: tags
  properties: {
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      azureADOnlyAuthentication: true
      login: adminLogin
      sid: adminObjectId
      tenantId: subscription().tenantId
      principalType: 'User'
    }
  }
}

resource dw 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sql
  name: 'sqldb-chaski-dw'
  location: location
  tags: tags
  sku: { name: 'GP_S_Gen5', tier: 'GeneralPurpose', family: 'Gen5', capacity: 2 }
  properties: {
    useFreeLimit: true
    freeLimitExhaustionBehavior: 'AutoPause'
    autoPauseDelay: 60
    minCapacity: json('0.5')
    maxSizeBytes: 34359738368
    requestedBackupStorageRedundancy: 'Local'
  }
}

resource vnetRule 'Microsoft.Sql/servers/virtualNetworkRules@2023-08-01-preview' = {
  parent: sql
  name: 'allow-aca-subnet'
  properties: { virtualNetworkSubnetId: acaSubnetId }
}

resource deployerRule 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = if (!empty(deployerIp)) {
  parent: sql
  name: 'allow-deployer'
  properties: { startIpAddress: deployerIp, endIpAddress: deployerIp }
}

output name string = sql.name
output fqdn string = sql.properties.fullyQualifiedDomainName
output database string = dw.name
