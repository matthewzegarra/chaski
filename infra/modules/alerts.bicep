// Azure Monitor alerts, all routed to one e-mail action group (~USD 1.2/month in total):
//   - API failures and latency: metric alerts on Application Insights (every service reports there)
//   - ingestion pipeline with quarantined rows or a crash: log alert on the job console logs
//   - burst of 401/403 responses (possible credential stuffing / privilege probing): log alert
// Budget alerts live at subscription level (chaski-budget).
param tags object
param prefix string
param alertEmail string
param appInsightsId string
param workspaceId string

resource ag 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${prefix}'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'chaski'
    enabled: true
    emailReceivers: [ { name: 'equipo', emailAddress: alertEmail, useCommonAlertSchema: true } ]
  }
}

var metricAlerts = [
  {
    name: 'alert-${prefix}-api-failures'
    description: 'Las APIs de CHASKI devolvieron errores (5xx o requests fallidos).'
    severity: 1
    window: 'PT5M'
    metric: 'requests/failed'
    aggregation: 'Count'
    threshold: 5
  }
  {
    name: 'alert-${prefix}-api-latency'
    description: 'La latencia promedio de las APIs supera 3 segundos.'
    severity: 2
    window: 'PT15M'
    metric: 'requests/duration'
    aggregation: 'Average'
    threshold: 3000
  }
]

resource metric 'Microsoft.Insights/metricAlerts@2018-03-01' = [for a in metricAlerts: {
  name: a.name
  location: 'global'
  tags: tags
  properties: {
    description: a.description
    severity: a.severity
    enabled: true
    scopes: [ appInsightsId ]
    evaluationFrequency: 'PT5M'
    windowSize: a.window
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'criterion'
          criterionType: 'StaticThresholdCriterion'
          metricNamespace: 'microsoft.insights/components'
          metricName: a.metric
          timeAggregation: a.aggregation
          operator: 'GreaterThan'
          threshold: a.threshold
        }
      ]
    }
    actions: [ { actionGroupId: ag.id } ]
  }
}]

var logAlerts = [
  {
    name: 'alert-${prefix}-pipeline'
    description: 'El pipeline de ingesta envió registros a cuarentena o terminó con error.'
    severity: 2
    query: 'ContainerAppConsoleLogs | where JobName startswith "caj-pipeline" | where (Log has "pipeline_run_finished" and Log has "CON_ALERTAS") or Log has "Traceback"'
    threshold: 0
  }
  {
    name: 'alert-${prefix}-denied-burst'
    description: 'Ráfaga de accesos denegados (401/403): posible abuso de credenciales o escalamiento de privilegios.'
    severity: 1
    query: 'AppRequests | where ResultCode in ("401", "403")'
    threshold: 20
  }
]

resource logs 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = [for a in logAlerts: {
  name: a.name
  location: resourceGroup().location
  tags: tags
  properties: {
    description: a.description
    severity: a.severity
    enabled: true
    scopes: [ workspaceId ]
    evaluationFrequency: 'PT15M'
    windowSize: 'PT15M'
    autoMitigate: true
    criteria: {
      allOf: [
        {
          query: a.query
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: a.threshold
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
    actions: { actionGroups: [ ag.id ] }
  }
}]

output actionGroupId string = ag.id
