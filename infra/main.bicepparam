using 'main.bicep'

// Non-secret values only. deployerIp / deployerObjectId / deployerUpn are passed by
// infra/scripts/deploy.ps1 at run time; nothing personal or secret is stored here.
param location = 'westus'
param environmentName = 'dev'
param owner = 'matthew'
param deployerIp = ''
param deployerObjectId = ''
param deployerUpn = ''

// Identity tenant (infra/entra/setup-entra.ps1 output). Ids, not secrets.
param entra = {
  tenantId: '726ac36b-6173-4e55-9c87-bb6683d2b02c'
  audience: 'c386a571-a8b4-4de7-a54a-4e58adc7ff45'
  apiScope: 'api://c386a571-a8b4-4de7-a54a-4e58adc7ff45/access_as_user'
  clienteClientId: 'cea85c07-0b4a-4764-884a-dffdd431e08f'
  consolaClientId: 'a99a8665-b857-42fc-ab54-5aa796ed2536'
}
