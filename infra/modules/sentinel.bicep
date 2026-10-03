// Microsoft Sentinel on log-<prefix> (Phase 11.3) and an operations workbook (11.1).
//
// Sentinel starts a 31-day free trial on the workspace; the sentinel-offboard workflow
// removes it automatically before the trial ends (FinOps). The workspace keeps its daily
// ingestion cap, so the analysed volume stays small.
//
// Analytics rules (each creates an incident):
//   1. Brute force against the APIs: many 401 from one IP at the API Management gateway.
//   2. Key Vault secret read by an identity that is not a CHASKI workload or the admin.
//   3. Burst of 403 at the APIs (privilege probing, e.g. Marketing opening Clientes).
//   4. RBAC role assignment created in the subscription (Activity log, from bootstrap.bicep).
param tags object
param workspaceName string
@description('Object ids allowed to read Key Vault secrets (workloads and the admin).')
param allowedSecretReaders array

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: workspaceName
}

resource onboarding 'Microsoft.SecurityInsights/onboardingStates@2024-03-01' = {
  scope: law
  name: 'default'
  properties: {}
}

var allowedList = join(map(allowedSecretReaders, id => '"${id}"'), ', ')

var rules = [
  {
    name: 'chaski-api-brute-force'
    displayName: 'CHASKI · Fuerza bruta contra las APIs (tokens inválidos)'
    description: 'Una misma IP recibió 5 o más respuestas 401 del gateway de APIs en 15 minutos.'
    severity: 'Medium'
    tactics: [ 'CredentialAccess' ]
    query: 'AzureDiagnostics\n| where ResourceProvider == "MICROSOFT.APIMANAGEMENT" and Category == "GatewayLogs"\n| extend codigo = toint(column_ifexists("responseCode_d", 0)), ip = tostring(column_ifexists("callerIpAddress_s", "")), api = tostring(column_ifexists("apiId_s", ""))\n| where codigo == 401\n| summarize intentos = count(), apis = make_set(api) by ip\n| where intentos >= 5'
  }
  {
    name: 'chaski-keyvault-unexpected-reader'
    displayName: 'CHASKI · Secreto leído por una identidad no autorizada'
    description: 'Key Vault entregó un secreto a una identidad que no es un workload de CHASKI ni el administrador.'
    severity: 'High'
    tactics: [ 'CredentialAccess' ]
    query: 'AzureDiagnostics\n| where ResourceProvider == "MICROSOFT.KEYVAULT" and OperationName == "SecretGet"\n| extend lector = tostring(coalesce(column_ifexists("identity_claim_oid_g", ""), column_ifexists("identity_claim_http_schemas_microsoft_com_identity_claims_objectidentifier_g", "")))\n| where isnotempty(lector) and lector !in (${allowedList})\n| summarize lecturas = count(), secretos = make_set(tostring(column_ifexists("id_s", ""))) by lector, CallerIPAddress'
  }
  {
    name: 'chaski-forbidden-burst'
    displayName: 'CHASKI · Ráfaga de accesos denegados (403)'
    description: 'Muchos 403 desde una IP: un usuario intenta abrir módulos o datos fuera de su rol.'
    severity: 'Medium'
    tactics: [ 'PrivilegeEscalation' ]
    query: 'AppRequests\n| where ResultCode == "403"\n| summarize denegados = count(), rutas = make_set(Name) by ClientIP, AppRoleName\n| where denegados >= 10'
  }
  {
    name: 'chaski-rbac-change'
    displayName: 'CHASKI · Nueva asignación de roles RBAC en la suscripción'
    description: 'Se creó una asignación de roles: revisar que corresponda a un despliegue aprobado.'
    severity: 'Low'
    tactics: [ 'Persistence', 'PrivilegeEscalation' ]
    query: 'union isfuzzy=true (AzureActivity\n| where OperationNameValue =~ "MICROSOFT.AUTHORIZATION/ROLEASSIGNMENTS/WRITE" and ActivityStatusValue == "Success"\n| project TimeGenerated, Caller, CallerIpAddress, ResourceGroup, _ResourceId)'
  }
]

resource alertRules 'Microsoft.SecurityInsights/alertRules@2024-03-01' = [for r in rules: {
  scope: law
  name: r.name
  kind: 'Scheduled'
  properties: {
    displayName: r.displayName
    description: r.description
    severity: r.severity
    enabled: true
    query: r.query
    queryFrequency: 'PT15M'
    queryPeriod: 'PT15M'
    triggerOperator: 'GreaterThan'
    triggerThreshold: 0
    suppressionDuration: 'PT1H'
    suppressionEnabled: false
    tactics: r.tactics
    incidentConfiguration: {
      createIncident: true
      groupingConfiguration: {
        enabled: false
        reopenClosedIncident: false
        lookbackDuration: 'PT5H'
        matchingMethod: 'AllEntities'
      }
    }
  }
  dependsOn: [ onboarding ]
}]

// Operations workbook over the workspace (requests, p95 latency, errors, dependencies).
var workbookContent = {
  version: 'Notebook/1.0'
  items: [
    {
      type: 1
      content: { json: '# CHASKI · Operación\nTráfico, latencia, errores y dependencias de las APIs (Application Insights).' }
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        title: 'Requests por servicio'
        query: 'AppRequests | summarize requests = count() by AppRoleName, bin(TimeGenerated, 1h) | render timechart'
        size: 0
        timeContext: { durationMs: 86400000 }
        queryType: 0
        resourceType: 'microsoft.operationalinsights/workspaces'
        visualization: 'timechart'
      }
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        title: 'Latencia p95 (ms) por servicio'
        query: 'AppRequests | summarize p95 = percentile(DurationMs, 95) by AppRoleName, bin(TimeGenerated, 1h) | render timechart'
        size: 0
        timeContext: { durationMs: 86400000 }
        queryType: 0
        resourceType: 'microsoft.operationalinsights/workspaces'
        visualization: 'timechart'
      }
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        title: 'Tasa de errores (%) por servicio'
        query: 'AppRequests | summarize errores = 100.0 * countif(Success == false) / count() by AppRoleName | order by errores desc'
        size: 0
        timeContext: { durationMs: 86400000 }
        queryType: 0
        resourceType: 'microsoft.operationalinsights/workspaces'
        visualization: 'barchart'
      }
    }
    {
      type: 3
      content: {
        version: 'KqlItem/1.0'
        title: 'Dependencias (PostgreSQL, Azure OpenAI, Key Vault...)'
        query: 'AppDependencies | summarize llamadas = count(), p95_ms = percentile(DurationMs, 95), fallos = countif(Success == false) by Type, Target | order by llamadas desc'
        size: 0
        timeContext: { durationMs: 86400000 }
        queryType: 0
        resourceType: 'microsoft.operationalinsights/workspaces'
        visualization: 'table'
      }
    }
  ]
}

resource workbook 'Microsoft.Insights/workbooks@2023-06-01' = {
  name: guid(law.id, 'chaski-operacion')
  location: resourceGroup().location
  tags: tags
  kind: 'shared'
  properties: {
    displayName: 'CHASKI · Operación'
    category: 'workbook'
    sourceId: law.id
    serializedData: string(workbookContent)
  }
}
