// Container Apps environment (Consumption workload profile, VNet integrated), the APIs,
// the two web apps and the jobs. Every app scales to zero and reads its secrets as Key
// Vault references with its own managed identity.
//
// usePlaceholderImages=true deploys a public sample image so the infrastructure can be
// created before the first CI/CD build pushes the real images to ACR.
param location string
param tags object
param prefix string
param acaSubnetId string
param workspaceId string
param keyVaultUri string
param acrLoginServer string
param identities object
param githubPrincipalId string
param usePlaceholderImages bool
param imageTag string
param appInsightsConnectionString string
param aiMode string
param entra object
param blobEndpoint string
param openAi object
param githubRepo string

var placeholderImage = 'mcr.microsoft.com/k8se/quickstart:latest'
var contributor = 'b24988ac-6180-42a0-ab88-20f7382dd24c'
var managedIdentityOperator = 'f1a07417-d97a-45cb-824c-7a7467783830'

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${prefix}'
  location: location
  tags: tags
  properties: {
    workloadProfiles: [ { name: 'Consumption', workloadProfileType: 'Consumption' } ]
    vnetConfiguration: { infrastructureSubnetId: acaSubnetId, internal: false }
    appLogsConfiguration: { destination: 'azure-monitor' }
    zoneRedundant: false
  }
}

resource diag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-log-analytics'
  scope: cae
  properties: {
    workspaceId: workspaceId
    logs: [ { categoryGroup: 'allLogs', enabled: true } ]
  }
}

var domain = cae.properties.defaultDomain
var publicUrl = { cuentas: 'https://ca-cuentas-dev.${domain}', core: 'https://ca-core.${domain}', ia: 'https://ca-ia.${domain}' }
var allowedOrigins = 'https://ca-cliente.${domain},https://ca-consola.${domain}'

var commonEnv = [
  { name: 'LOG_LEVEL', value: 'INFO' }
  { name: 'AUTH_MODE', value: 'entra' }
  { name: 'ENTRA_TENANT_ID', value: entra.tenantId }
  { name: 'ENTRA_AUDIENCE', value: entra.audience }
  { name: 'ALLOWED_ORIGINS', value: allowedOrigins }
  { name: 'RATE_LIMIT_PER_MINUTE', value: '300' }
  { name: 'DEMO_MODE', value: 'true' }
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights' }
  { name: 'CUENTAS_API_URL', value: 'http://ca-cuentas-dev' }
  { name: 'CORE_API_URL', value: 'http://ca-core' }
  { name: 'IA_API_URL', value: 'http://ca-ia' }
]

func kvSecret(name string, kvUri string, identityId string) object => {
  name: name
  keyVaultUrl: '${kvUri}secrets/${name}'
  identity: identityId
}

var apis = [
  {
    name: 'ca-cuentas-dev', image: 'chaski/cuentas-api', tag: 'dev', id: 'cuentas', chaskiEnv: 'DEV'
    kvSecrets: [ 'database-url' ]
    env: [ { name: 'SERVICE_NAME', value: 'cuentas-api' } ]
  }
  {
    name: 'ca-cuentas-test', image: 'chaski/cuentas-api', tag: 'test', id: 'cuentas', chaskiEnv: 'TEST'
    kvSecrets: [ 'database-url' ]
    env: [ { name: 'SERVICE_NAME', value: 'cuentas-api' } ]
  }
  {
    name: 'ca-cuentas-prod', image: 'chaski/cuentas-api', tag: 'prod', id: 'cuentas', chaskiEnv: 'PROD'
    kvSecrets: [ 'database-url' ]
    env: [ { name: 'SERVICE_NAME', value: 'cuentas-api' } ]
  }
  {
    name: 'ca-core', image: 'chaski/core-api', tag: imageTag, id: 'core', chaskiEnv: 'DEV'
    kvSecrets: [ 'database-url', 'analytics-db-url', 'fraud-webhook-secret', 'chaski-services-cert' ]
    env: [
      { name: 'SERVICE_NAME', value: 'core-api' }
      { name: 'ANALYTICS_DB_URL', secretRef: 'analytics-db-url' }
      { name: 'ANALYTICS_DIALECT', value: 'postgres' }
      { name: 'FRAUD_WEBHOOK_SECRET', secretRef: 'fraud-webhook-secret' }
      { name: 'KEY_VAULT_URL', value: keyVaultUri }
      { name: 'BLOB_ACCOUNT_URL', value: blobEndpoint }
      { name: 'BLOB_CONTAINER', value: 'kyc' }
      { name: 'AZURE_SUBSCRIPTION_ID', value: subscription().subscriptionId }
      { name: 'AZURE_RESOURCE_GROUP', value: resourceGroup().name }
      { name: 'PIPELINE_JOB_NAME', value: 'caj-pipeline' }
      { name: 'GITHUB_REPO', value: githubRepo }
      { name: 'ENTRA_SERVICE_CLIENT_ID', value: entra.servicesClientId }
      { name: 'ENTRA_SERVICE_CERTIFICATE', secretRef: 'chaski-services-cert' }
    ]
  }
  {
    name: 'ca-ia', image: 'chaski/ia-api', tag: imageTag, id: 'ia', chaskiEnv: 'DEV'
    kvSecrets: [ 'database-url', 'analytics-db-url', 'nl2sql-db-url' ]
    env: [
      { name: 'SERVICE_NAME', value: 'ia-api' }
      { name: 'AI_MODE', value: aiMode }
      { name: 'ANALYTICS_DB_URL', secretRef: 'analytics-db-url' }
      { name: 'NL2SQL_DB_URL', secretRef: 'nl2sql-db-url' }
      { name: 'ANALYTICS_DIALECT', value: 'postgres' }
      { name: 'AZURE_OPENAI_ENDPOINT', value: openAi.endpoint }
      { name: 'AZURE_OPENAI_DEPLOYMENT', value: openAi.deployment }
      { name: 'AZURE_OPENAI_API_VERSION', value: '2025-04-01-preview' }
      { name: 'AZURE_OPENAI_REASONING_EFFORT', value: 'minimal' }
      { name: 'CONTENT_SAFETY_ENDPOINT', value: openAi.contentSafetyEndpoint }
      { name: 'DOCINTEL_ENDPOINT', value: openAi.docIntelEndpoint }
    ]
  }
]

var webs = [
  { name: 'ca-cliente', image: 'chaski/cliente', clientId: entra.clienteClientId }
  { name: 'ca-consola', image: 'chaski/consola', clientId: entra.consolaClientId }
]

resource apiApps 'Microsoft.App/containerApps@2024-03-01' = [for a in apis: {
  name: a.name
  location: location
  tags: union(tags, { service: a.image })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identities[a.id].id}': {} }
  }
  properties: {
    environmentId: cae.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: a.name == 'ca-cuentas-prod' ? 'Multiple' : 'Single'
      ingress: {
        external: true
        targetPort: usePlaceholderImages ? 80 : 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [ { server: acrLoginServer, identity: identities[a.id].id } ]
      secrets: concat(
        map(a.kvSecrets, s => kvSecret(s, keyVaultUri, identities[a.id].id)),
        [ { name: 'appinsights', value: appInsightsConnectionString } ]
      )
    }
    template: {
      containers: [
        {
          name: 'app'
          image: usePlaceholderImages ? placeholderImage : '${acrLoginServer}/${a.image}:${a.tag}'
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: concat(commonEnv, a.env, [
            { name: 'CHASKI_ENV', value: a.chaskiEnv }
            { name: 'AZURE_CLIENT_ID', value: identities[a.id].clientId }
          ])
          probes: usePlaceholderImages ? [] : [
            { type: 'Liveness', httpGet: { path: '/health', port: 8000 }, periodSeconds: 30 }
            { type: 'Readiness', httpGet: { path: '/ready', port: 8000 }, periodSeconds: 15 }
          ]
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 2 }
    }
  }
}]

resource webApps 'Microsoft.App/containerApps@2024-03-01' = [for w in webs: {
  name: w.name
  location: location
  tags: union(tags, { service: w.image })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identities.web.id}': {} }
  }
  properties: {
    environmentId: cae.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: usePlaceholderImages ? 80 : 8080
        transport: 'auto'
        allowInsecure: false
      }
      registries: [ { server: acrLoginServer, identity: identities.web.id } ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: usePlaceholderImages ? placeholderImage : '${acrLoginServer}/${w.image}:${imageTag}'
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'CHASKI_AUTH_MODE', value: 'entra' }
            { name: 'CHASKI_ENV', value: 'DEV' }
            { name: 'CHASKI_CUENTAS_API_URL', value: publicUrl.cuentas }
            { name: 'CHASKI_CORE_API_URL', value: publicUrl.core }
            { name: 'CHASKI_IA_API_URL', value: publicUrl.ia }
            { name: 'CHASKI_ENTRA_CLIENT_ID', value: w.clientId }
            { name: 'CHASKI_ENTRA_TENANT_ID', value: entra.tenantId }
            { name: 'CHASKI_ENTRA_API_SCOPE', value: entra.apiScope }
          ]
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
}]

// Jobs: database migrations + seed (manual) and the data pipeline (manual for now;
// the nightly cron is added with the data phase).
var jobs = [
  {
    name: 'caj-migrate', image: 'chaski/tools', hasImage: true
    // Roles first (no init hook in managed PostgreSQL), then schema, then synthetic data.
    command: [ 'sh', '-c', 'python db/bootstrap_roles.py && alembic -c db/alembic.ini upgrade head && python -m chaski_simulator --reset' ]
    kvSecrets: [ 'migrations-database-url', 'pg-app-password', 'pg-readonly-password' ]
    env: [
      { name: 'MIGRATIONS_DATABASE_URL', secretRef: 'migrations-database-url' }
      { name: 'CHASKI_APP_DB_PASSWORD', secretRef: 'pg-app-password' }
      { name: 'CHASKI_READONLY_DB_PASSWORD', secretRef: 'pg-readonly-password' }
    ]
  }
  {
    // The pipeline image arrives with the data phase; until then it keeps the sample image.
    name: 'caj-pipeline', image: 'chaski/pipeline', hasImage: false
    command: []
    kvSecrets: [ 'database-url' ]
    env: [
      { name: 'DATABASE_URL', secretRef: 'database-url' }
      { name: 'BLOB_ACCOUNT_URL', value: blobEndpoint }
    ]
  }
]

resource jobRes 'Microsoft.App/jobs@2024-03-01' = [for j in jobs: {
  name: j.name
  location: location
  tags: union(tags, { service: j.image })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identities.pipeline.id}': {} }
  }
  properties: {
    environmentId: cae.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 0
      manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
      registries: [ { server: acrLoginServer, identity: identities.pipeline.id } ]
      secrets: map(j.kvSecrets, s => kvSecret(s, keyVaultUri, identities.pipeline.id))
    }
    template: {
      containers: [
        {
          name: 'job'
          image: usePlaceholderImages || !j.hasImage ? placeholderImage : '${acrLoginServer}/${j.image}:${imageTag}'
          command: usePlaceholderImages || !j.hasImage ? null : j.command
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: concat(j.env, [ { name: 'AZURE_CLIENT_ID', value: identities.pipeline.clientId } ])
        }
      ]
    }
  }
}]

// core-api may start the pipeline job (button "Ejecutar pipeline") and nothing else.
resource coreStartsPipeline 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(jobRes[1].id, identities.core.principalId, contributor)
  scope: jobRes[1]
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributor)
    principalId: identities.core.principalId
    principalType: 'ServicePrincipal'
  }
}

// GitHub Actions deploys only the three cuentas-api apps.
resource ghDeploy 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for i in range(0, 3): {
  name: guid(apiApps[i].id, githubPrincipalId, contributor)
  scope: apiApps[i]
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributor)
    principalId: githubPrincipalId
    principalType: 'ServicePrincipal'
  }
}]

// Updating an app is a linked write on its environment (managedEnvironments/join).
// A minimal custom role grants just that instead of Contributor on the environment.
resource joinRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, 'chaski-cae-join')
  properties: {
    roleName: 'CHASKI Container Apps environment joiner (${resourceGroup().name})'
    description: 'Read and join the CHASKI Container Apps environment; used by GitHub Actions deploys.'
    type: 'CustomRole'
    assignableScopes: [ resourceGroup().id ]
    permissions: [
      {
        actions: [
          'Microsoft.App/managedEnvironments/read'
          'Microsoft.App/managedEnvironments/join/action'
        ]
      }
    ]
  }
}

resource ghJoin 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cae.id, githubPrincipalId, joinRole.id)
  scope: cae
  properties: {
    roleDefinitionId: joinRole.id
    principalId: githubPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource cuentasIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: last(split(identities.cuentas.id, '/'))
}

resource ghIdentityOperator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cuentasIdentity.id, githubPrincipalId, managedIdentityOperator)
  scope: cuentasIdentity
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', managedIdentityOperator)
    principalId: githubPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output environmentName string = cae.name
output defaultDomain string = domain
output urls object = {
  cliente: 'https://ca-cliente.${domain}'
  consola: 'https://ca-consola.${domain}'
  cuentasDev: publicUrl.cuentas
  cuentasTest: 'https://ca-cuentas-test.${domain}'
  cuentasProd: 'https://ca-cuentas-prod.${domain}'
  core: publicUrl.core
  ia: publicUrl.ia
}
