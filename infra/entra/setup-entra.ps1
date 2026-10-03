<#
.SYNOPSIS
  Phase 1 (Identity): creates the CHASKI app registrations, App Roles, demo users and
  role assignments in the Entra ID tenant that holds the bank's identities.

.DESCRIPTION
  Idempotent: every object is looked up by name before it is created, so the script can
  be re-run safely. By default it runs in PLAN mode (prints what it would do, changes
  nothing). Pass -Apply to make the changes.

  Uses the personal Azure CLI profile (AZURE_CONFIG_DIR=%USERPROFILE%\.azure-personal),
  which is signed in to the identity tenant. Infrastructure lives in a different
  tenant/subscription (UTP Azure for Students); nothing here creates billable resources:
  Entra ID Free covers app registrations, users and App Roles.

  What it creates
    chaski-api       API app: identifier api://<appId>, scope access_as_user, the 9 App
                     Roles, v2 access tokens, directory extension customer_id emitted
                     as an optional claim, user assignment required.
    chaski-cliente   SPA (Chaski App) with redirect URIs; delegated access to chaski-api.
    chaski-consola   SPA (Control Center) with redirect URIs; delegated access to chaski-api.
    chaski-services  Daemon identity holding the Operaciones *application* role, used for
                     service-to-service calls. It gets NO secret here: a federated
                     credential trusting the Container Apps managed identity is added in
                     the infrastructure phase (secretless, cross-tenant).
    Users            admin, operaciones, atencion, riesgos, fraude, direccion, marketing,
                     ti (staff) and cliente1..3 (customers), each assigned its App Role.
                     Temporary random passwords with forced change at first sign-in are
                     written to a file OUTSIDE the repo; they are never printed.

.EXAMPLE
  ./infra/entra/setup-entra.ps1                       # plan only
  ./infra/entra/setup-entra.ps1 -Apply                # create everything
  ./infra/entra/setup-entra.ps1 -Apply -CustomerIds 'uuid1','uuid2','uuid3'
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$TenantId = '726ac36b-6173-4e55-9c87-bb6683d2b02c',
    [string]$Domain = 'matthewzegarra0312gmail.onmicrosoft.com',
    # Redirect URIs per SPA; the Container Apps URLs are appended once they exist.
    [string[]]$ClienteRedirectUris = @('http://localhost:3000'),
    [string[]]$ConsolaRedirectUris = @('http://localhost:3001'),
    # core.customers ids for cliente1..3 (deterministic seed); optional.
    [string[]]$CustomerIds = @(),
    [string]$CredentialsFile = (Join-Path $env:USERPROFILE 'chaski-entra-demo-users.txt'),
    [string]$OutputFile = (Join-Path $PSScriptRoot '.out/entra.json')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$env:AZURE_CONFIG_DIR = Join-Path $env:USERPROFILE '.azure-personal'
$az = 'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd'
if (-not (Test-Path $az)) { $az = 'az' }
$graph = 'https://graph.microsoft.com/v1.0'
$tmp = Join-Path ([IO.Path]::GetTempPath()) 'chaski-entra'
New-Item -ItemType Directory -Force $tmp | Out-Null

# Stable GUIDs so re-runs never duplicate roles or scopes.
$ScopeId = '6f1b3c1e-2a54-4d0f-9b3c-7c2e1a9d0a01'
$Roles = [ordered]@{
    Admin       = @{ id = '0c3a6b1e-1f00-4a8e-9d01-000000000001'; members = @('User');                desc = 'Administración total de CHASKI' }
    Operaciones = @{ id = '0c3a6b1e-1f00-4a8e-9d01-000000000002'; members = @('User', 'Application'); desc = 'Centro de Operaciones (también identidad de servicio)' }
    Atencion    = @{ id = '0c3a6b1e-1f00-4a8e-9d01-000000000003'; members = @('User');                desc = 'Atención al cliente, KYC y quejas' }
    Riesgos     = @{ id = '0c3a6b1e-1f00-4a8e-9d01-000000000004'; members = @('User');                desc = 'Decisión de préstamos y cartera' }
    Fraude      = @{ id = '0c3a6b1e-1f00-4a8e-9d01-000000000005'; members = @('User');                desc = 'Chaski Guard' }
    Direccion   = @{ id = '0c3a6b1e-1f00-4a8e-9d01-000000000006'; members = @('User');                desc = 'Chaski Insights (dirección)' }
    Marketing   = @{ id = '0c3a6b1e-1f00-4a8e-9d01-000000000007'; members = @('User');                desc = 'Chaski Insights (marketing, sin PII)' }
    TI          = @{ id = '0c3a6b1e-1f00-4a8e-9d01-000000000008'; members = @('User');                desc = 'Pipelines, salud de IA, seguridad y DevOps' }
    Cliente     = @{ id = '0c3a6b1e-1f00-4a8e-9d01-000000000009'; members = @('User');                desc = 'Cliente de Chaski App' }
}
$Users = @(
    @{ nick = 'admin';       name = 'Ana Admin';            role = 'Admin' }
    @{ nick = 'operaciones'; name = 'Oscar Operaciones';    role = 'Operaciones' }
    @{ nick = 'atencion';    name = 'Andrea Atención';      role = 'Atencion' }
    @{ nick = 'riesgos';     name = 'Rosa Riesgos';         role = 'Riesgos' }
    @{ nick = 'fraude';      name = 'Fernando Fraude';      role = 'Fraude' }
    @{ nick = 'direccion';   name = 'Diana Dirección';      role = 'Direccion' }
    @{ nick = 'marketing';   name = 'Mario Marketing';      role = 'Marketing' }
    @{ nick = 'ti';          name = 'Tomás TI';             role = 'TI' }
    @{ nick = 'cliente1';    name = 'Cliente Demo 1';       role = 'Cliente'; customer = 0 }
    @{ nick = 'cliente2';    name = 'Cliente Demo 2';       role = 'Cliente'; customer = 1 }
    @{ nick = 'cliente3';    name = 'Cliente Demo 3';       role = 'Cliente'; customer = 2 }
)

function Step([string]$msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }
function Plan([string]$msg) { Write-Host "  [plan] $msg" -ForegroundColor Yellow }
function Done([string]$msg) { Write-Host "  [ok]   $msg" -ForegroundColor Green }

function Invoke-Az {
    $out = & $az @args --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "az $($args -join ' ') failed ($LASTEXITCODE)" }
    if ($out) { return ($out | Out-String | ConvertFrom-Json) }
}

function Invoke-Graph([string]$Method, [string]$Path, $Body = $null) {
    $azArgs = @('rest', '--method', $Method, '--url', "$graph$Path", '--headers', 'Content-Type=application/json')
    if ($null -ne $Body) {
        $f = Join-Path $tmp ("body-{0}.json" -f [guid]::NewGuid())
        $Body | ConvertTo-Json -Depth 12 | Set-Content -Path $f -Encoding utf8
        $azArgs += @('--body', "@$f")
    }
    try { return Invoke-Az @azArgs } finally { if ($null -ne $Body) { Remove-Item $f -ErrorAction SilentlyContinue } }
}

function Get-App([string]$Name) {
    $r = Invoke-Graph GET "/applications?`$filter=displayName eq '$Name'"
    return @($r.value) | Select-Object -First 1
}

function Ensure-App([string]$Name) {
    $app = Get-App $Name
    if ($app) { Done "$Name exists (appId $($app.appId))"; return $app }
    if (-not $Apply) { Plan "create app registration $Name (single tenant)"; return $null }
    $app = Invoke-Graph POST '/applications' @{ displayName = $Name; signInAudience = 'AzureADMyOrg' }
    Done "$Name created (appId $($app.appId))"
    return $app
}

function Ensure-Sp($app) {
    $r = Invoke-Graph GET "/servicePrincipals?`$filter=appId eq '$($app.appId)'"
    $sp = @($r.value) | Select-Object -First 1
    if ($sp) { return $sp }
    $sp = Invoke-Graph POST '/servicePrincipals' @{ appId = $app.appId }
    Done "service principal for $($app.displayName)"
    return $sp
}

function New-TempPassword {
    $chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#%*-_'
    $bytes = [byte[]]::new(20)
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return (-join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })) + 'a9!'
}

# ---------------------------------------------------------------- 0. guard rails
Step '0. Tenant check'
$acct = Invoke-Az account show
if ($acct.tenantId -ne $TenantId) {
    throw "Signed in to tenant $($acct.tenantId), expected $TenantId. Run: `$env:AZURE_CONFIG_DIR='$env:AZURE_CONFIG_DIR'; az login --use-device-code --allow-no-subscriptions"
}
Done "tenant $TenantId as $($acct.user.name)"
if (-not $Apply) { Write-Host '  PLAN mode: nothing will be changed. Re-run with -Apply.' -ForegroundColor Yellow }

# ---------------------------------------------------------------- 1. chaski-api
Step '1. chaski-api (resource app: roles, scope, claims)'
$api = Ensure-App 'chaski-api'
$appRoles = foreach ($k in $Roles.Keys) {
    @{ id = $Roles[$k].id; value = $k; displayName = $k; description = $Roles[$k].desc
       allowedMemberTypes = @($Roles[$k].members); isEnabled = $true }
}
if ($api) {
    if ($Apply) {
        Invoke-Graph PATCH "/applications/$($api.id)" @{
            identifierUris = @("api://$($api.appId)")
            appRoles       = @($appRoles)
            api            = @{
                requestedAccessTokenVersion = 2
                oauth2PermissionScopes      = @(@{
                    id = $ScopeId; value = 'access_as_user'; type = 'User'; isEnabled = $true
                    adminConsentDisplayName = 'Acceder a CHASKI como el usuario'
                    adminConsentDescription = 'Permite a las apps de CHASKI llamar a las APIs en nombre del usuario.'
                    userConsentDisplayName  = 'Acceder a CHASKI'
                    userConsentDescription  = 'Permite a la app usar CHASKI en tu nombre.'
                })
            }
        } | Out-Null
        Done 'identifier api://<appId>, 9 App Roles, scope access_as_user, v2 tokens'
    } else { Plan "identifier api://$($api.appId), 9 App Roles, scope access_as_user, v2 tokens" }
} else { Plan 'identifier api://<appId>, 9 App Roles, scope access_as_user, v2 tokens' }

# Directory extension customer_id (on the resource app) + optional claim in access tokens.
$extName = $null
if ($api) {
    $exts = Invoke-Graph GET "/applications/$($api.id)/extensionProperties"
    $ext = @($exts.value | Where-Object { $_.name -like '*_customer_id' }) | Select-Object -First 1
    if (-not $ext -and $Apply) {
        $ext = Invoke-Graph POST "/applications/$($api.id)/extensionProperties" @{ name = 'customer_id'; dataType = 'String'; targetObjects = @('User') }
        Done "directory extension $($ext.name)"
    }
    if ($ext) {
        $extName = $ext.name
        if ($Apply) {
            Invoke-Graph PATCH "/applications/$($api.id)" @{
                optionalClaims = @{ accessToken = @(@{ name = $extName; source = 'user'; essential = $false; additionalProperties = @() }) }
            } | Out-Null
            Done "optional claim $extName in access tokens"
        }
    } else { Plan 'directory extension customer_id + optional claim in access tokens' }
} else { Plan 'directory extension customer_id + optional claim in access tokens' }

$apiSp = $null
if ($api -and $Apply) {
    $apiSp = Ensure-Sp $api
    Invoke-Graph PATCH "/servicePrincipals/$($apiSp.id)" @{ appRoleAssignmentRequired = $true } | Out-Null
    Done 'user assignment required (only users with a role get tokens)'
} else { Plan 'service principal for chaski-api with appRoleAssignmentRequired=true' }

# ---------------------------------------------------------------- 2. SPAs
Step '2. SPAs chaski-cliente and chaski-consola'
$spas = @{}
foreach ($spa in @(@{ name = 'chaski-cliente'; uris = $ClienteRedirectUris }, @{ name = 'chaski-consola'; uris = $ConsolaRedirectUris })) {
    $app = Ensure-App $spa.name
    if ($app -and $api -and $Apply) {
        Invoke-Graph PATCH "/applications/$($app.id)" @{
            spa                    = @{ redirectUris = @($spa.uris) }
            requiredResourceAccess = @(@{ resourceAppId = $api.appId; resourceAccess = @(@{ id = $ScopeId; type = 'Scope' }) })
        } | Out-Null
        $spaSp = Ensure-Sp $app
        $grants = Invoke-Graph GET "/oauth2PermissionGrants?`$filter=clientId eq '$($spaSp.id)' and resourceId eq '$($apiSp.id)'"
        if (-not @($grants.value).Count) {
            Invoke-Graph POST '/oauth2PermissionGrants' @{ clientId = $spaSp.id; consentType = 'AllPrincipals'; resourceId = $apiSp.id; scope = 'access_as_user' } | Out-Null
        }
        Done "$($spa.name): redirect $($spa.uris -join ', '); admin consent for access_as_user"
    } else { Plan "$($spa.name): SPA redirect $($spa.uris -join ', '); delegated access_as_user with admin consent" }
    $spas[$spa.name] = $app
}

# ---------------------------------------------------------------- 3. service identity
Step '3. chaski-services (service-to-service, no secret)'
$svc = Ensure-App 'chaski-services'
if ($svc -and $apiSp -and $Apply) {
    $svcSp = Ensure-Sp $svc
    $assigned = Invoke-Graph GET "/servicePrincipals/$($svcSp.id)/appRoleAssignments"
    if (-not @($assigned.value | Where-Object { $_.appRoleId -eq $Roles.Operaciones.id }).Count) {
        Invoke-Graph POST "/servicePrincipals/$($apiSp.id)/appRoleAssignedTo" @{ principalId = $svcSp.id; resourceId = $apiSp.id; appRoleId = $Roles.Operaciones.id } | Out-Null
    }
    Done 'application role Operaciones granted; federated credential pending (infra phase)'
} else { Plan 'application role Operaciones for chaski-services; no secret (federated credential added in infra phase)' }

# ---------------------------------------------------------------- 4. users
Step '4. Demo users and role assignments'
$newCreds = @()
foreach ($u in $Users) {
    $upn = "$($u.nick)@$Domain"
    $found = Invoke-Graph GET "/users?`$filter=userPrincipalName eq '$upn'&`$select=id,userPrincipalName"
    $existing = @($found.value) | Select-Object -First 1
    if (-not $Apply) {
        Plan "$(if ($existing) { 'keep' } else { 'create' }) $upn ($($u.name)) -> role $($u.role)"
        continue
    }
    if (-not $existing) {
        $pwd = New-TempPassword
        $existing = Invoke-Graph POST '/users' @{
            accountEnabled = $true; displayName = "$($u.name) · Chaski Bank"; mailNickname = $u.nick
            userPrincipalName = $upn; usageLocation = 'PE'
            passwordProfile = @{ password = $pwd; forceChangePasswordNextSignIn = $true }
        }
        $newCreds += "$upn`t$pwd"
        Done "user $upn"
    }
    $has = Invoke-Graph GET "/users/$($existing.id)/appRoleAssignments"
    if (-not @($has.value | Where-Object { $_.appRoleId -eq $Roles[$u.role].id -and $_.resourceId -eq $apiSp.id }).Count) {
        Invoke-Graph POST "/servicePrincipals/$($apiSp.id)/appRoleAssignedTo" @{ principalId = $existing.id; resourceId = $apiSp.id; appRoleId = $Roles[$u.role].id } | Out-Null
    }
    Done "$upn -> $($u.role)"
    if ($u.ContainsKey('customer') -and $extName -and $CustomerIds.Count -gt $u.customer) {
        Invoke-Graph PATCH "/users/$($existing.id)" @{ $extName = $CustomerIds[$u.customer] } | Out-Null
        Done "$upn customer_id set"
    }
}
if ($Apply -and $CustomerIds.Count -eq 0) {
    Write-Host '  NOTE: cliente1..3 have no customer_id yet; re-run with -CustomerIds once the DB is seeded.' -ForegroundColor Yellow
}
if ($newCreds.Count) {
    Add-Content -Path $CredentialsFile -Value $newCreds -Encoding utf8
    Done "temporary passwords written to $CredentialsFile (outside the repo; change at first sign-in)"
}

# ---------------------------------------------------------------- 5. security defaults (MFA)
Step '5. Security defaults (MFA)'
# The Azure CLI token lacks Policy.Read.All, so this is checked in the portal instead.
try {
    $sd = Invoke-Graph GET '/policies/identitySecurityDefaultsEnforcementPolicy'
    if ($sd.isEnabled) { Done 'security defaults enabled (MFA for all users)' }
    else { Write-Host '  WARN: security defaults are OFF. Enable them in Entra ID > Overview > Properties.' -ForegroundColor Yellow }
} catch {
    Write-Host '  CHECK: Entra ID > Overview > Properties > Manage security defaults must be Enabled (MFA).' -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 6. output
Step '6. Configuration values (not secrets)'
if ($Apply -and $api) {
    $out = [ordered]@{
        tenantId          = $TenantId
        apiAppId          = $api.appId
        audience          = $api.appId          # v2 access tokens carry aud = appId (GUID)
        apiScope          = "api://$($api.appId)/access_as_user"
        clienteClientId   = $spas['chaski-cliente'].appId
        consolaClientId   = $spas['chaski-consola'].appId
        servicesClientId  = $svc.appId
        customerIdClaim   = $extName
    }
    New-Item -ItemType Directory -Force (Split-Path $OutputFile) | Out-Null
    $out | ConvertTo-Json | Set-Content -Path $OutputFile -Encoding utf8
    $out | Format-List | Out-String | Write-Host
    Write-Host @"
APIs:     AUTH_MODE=entra  ENTRA_TENANT_ID=$TenantId  ENTRA_AUDIENCE=$($api.appId)
Cliente:  CHASKI_ENTRA_TENANT_ID=$TenantId  CHASKI_ENTRA_CLIENT_ID=$($out.clienteClientId)  CHASKI_ENTRA_API_SCOPE=$($out.apiScope)
Consola:  CHASKI_ENTRA_TENANT_ID=$TenantId  CHASKI_ENTRA_CLIENT_ID=$($out.consolaClientId)  CHASKI_ENTRA_API_SCOPE=$($out.apiScope)
"@
} else { Plan "write $OutputFile with tenant/app ids and print the env vars for APIs and webs" }
