// PostgreSQL Flexible Server (Burstable B1ms) with VNet integration only: no public
// endpoint. Migrations and seed run from a Container Apps job inside the VNet.
param location string
param tags object
param name string
param subnetId string
param privateDnsZoneId string
param workspaceId string
param adminLogin string = 'chaski_admin'
@secure()
param adminPassword string
@description('GitHub ops identity that starts/stops the server on a schedule.')
param opsPrincipalId string

resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: name
  location: location
  tags: tags
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: adminLogin
    administratorLoginPassword: adminPassword
    authConfig: { passwordAuth: 'Enabled', activeDirectoryAuth: 'Disabled' }
    storage: { storageSizeGB: 32, autoGrow: 'Disabled' }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: {
      delegatedSubnetResourceId: subnetId
      privateDnsZoneArmResourceId: privateDnsZoneId
      publicNetworkAccess: 'Disabled'
    }
  }
}

resource db 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: pg
  name: 'chaski'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

resource tls 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: pg
  name: 'ssl_min_protocol_version'
  properties: { value: 'TLSv1.2', source: 'user-override' }
}

// Azure only allows extensions listed here; migration 0001 needs pgcrypto.
resource extensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: pg
  name: 'azure.extensions'
  properties: { value: 'PGCRYPTO', source: 'user-override' }
  dependsOn: [ tls ]
}

// Scheduled start/stop (pg-schedule workflow): a custom role with just those actions,
// assigned on this server only.
resource startStopRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, 'chaski-pg-start-stop')
  properties: {
    roleName: 'CHASKI PostgreSQL start/stop (${resourceGroup().name})'
    description: 'Read, start and stop the CHASKI PostgreSQL flexible server.'
    type: 'CustomRole'
    assignableScopes: [ resourceGroup().id ]
    permissions: [
      {
        actions: [
          'Microsoft.DBforPostgreSQL/flexibleServers/read'
          'Microsoft.DBforPostgreSQL/flexibleServers/start/action'
          'Microsoft.DBforPostgreSQL/flexibleServers/stop/action'
        ]
      }
    ]
  }
}

resource opsStartStop 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(pg.id, opsPrincipalId, startStopRole.id)
  scope: pg
  properties: {
    roleDefinitionId: startStopRole.id
    principalId: opsPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource diag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-log-analytics'
  scope: pg
  properties: {
    workspaceId: workspaceId
    logs: [ { category: 'PostgreSQLLogs', enabled: true } ]
  }
}

output name string = pg.name
output fqdn string = pg.properties.fullyQualifiedDomainName
