// Log Analytics (30-day retention, daily ingestion cap to protect the budget) and
// workspace-based Application Insights.
param location string
param tags object
param prefix string
@description('Daily ingestion cap in GB; ingestion stops for the day when reached.')
param dailyQuotaGb string = '0.15'

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${prefix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    workspaceCapping: { dailyQuotaGb: json(dailyQuotaGb) }
    features: { enableLogAccessUsingOnlyResourcePermissions: true }
  }
}

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${prefix}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: law.id
    IngestionMode: 'LogAnalytics'
  }
}

output workspaceId string = law.id
output appInsightsConnectionString string = appi.properties.ConnectionString
