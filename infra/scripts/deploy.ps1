<#
.SYNOPSIS
  Deploys the CHASKI infrastructure (infra/main.bicep) to the UTP Azure for Students
  subscription.

.DESCRIPTION
  -Stage whatif1  Preview stage 1 (changes nothing).
  -Stage 1        Network, monitoring, identities, Key Vault, storage, ACR, AI services.
  -Stage seed     Generates the secrets that do not exist yet and stores them in Key Vault
                  (random values, never printed, never written to the repo).
  -Stage whatif2  Preview stage 2 (needs the seeded secrets).
  -Stage 2        PostgreSQL, Azure SQL, Container Apps (+ jobs) and API Management.

  Uses the default Azure CLI profile (UTP account). Refuses to run against any other
  subscription, so nothing can ever land on the personal pay-as-you-go subscription.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('whatif1', '1', 'seed', 'whatif2', '2')][string]$Stage,
    [string]$SubscriptionName = 'Azure for Students',
    [string]$Location = 'westus',
    [switch]$RealImages,
    [string]$ImageTag = 'dev',
    [ValidateSet('mock', 'azure')][string]$AiMode = 'mock'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Remove-Item Env:AZURE_CONFIG_DIR -ErrorAction SilentlyContinue   # never the personal profile
$az = 'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd'
if (-not (Test-Path $az)) { $az = 'az' }
$infra = Split-Path $PSScriptRoot -Parent

function Invoke-Az {
    $out = & $az @args --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "az $($args[0..2] -join ' ') ... failed ($LASTEXITCODE)" }
    if ($out) { return ($out | Out-String | ConvertFrom-Json) }
}

# ---------------------------------------------------------------- guard rails
$acct = Invoke-Az account show
if ($acct.name -ne $SubscriptionName) {
    throw "Active subscription is '$($acct.name)'. Expected '$SubscriptionName' (az account set -s '$SubscriptionName')."
}
# Deployer identity from the ARM token claims (Microsoft Graph may be blocked by the
# tenant's Continuous Access Evaluation location policy).
$token = (Invoke-Az account get-access-token).accessToken
$payload = $token.Split('.')[1].Replace('-', '+').Replace('_', '/')
while ($payload.Length % 4) { $payload += '=' }
$claims = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payload)) | ConvertFrom-Json
$me = @{ id = $claims.oid; userPrincipalName = $claims.upn }
$ip = (Invoke-RestMethod -Uri 'https://api.ipify.org' -TimeoutSec 15).ToString().Trim()
Write-Host "Subscription : $($acct.name) ($($acct.id))"
Write-Host "Deployer     : $($me.userPrincipalName)  IP $ip"

$common = @(
    '--location', $Location,
    '--template-file', (Join-Path $infra 'main.bicep'),
    '--parameters', (Join-Path $infra 'main.bicepparam'),
    '--parameters', "location=$Location", "deployerIp=$ip", "deployerObjectId=$($me.id)", "deployerUpn=$($me.userPrincipalName)",
    "usePlaceholderImages=$(if ($RealImages) { 'false' } else { 'true' })", "imageTag=$ImageTag", "aiMode=$AiMode"
)

function Get-Outputs {
    $d = Invoke-Az deployment sub show --name chaski-stage1
    return $d.properties.outputs
}

function New-Secret([int]$Length = 32) {
    $chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
    $bytes = [byte[]]::new($Length)
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}

switch ($Stage) {
    'whatif1' { & $az deployment sub what-if --name chaski-stage1 @common '--parameters' 'deployWorkloads=false' }
    '1'       { Invoke-Az deployment sub create --name chaski-stage1 @common '--parameters' 'deployWorkloads=false' | Out-Null; Get-Outputs | ConvertTo-Json -Depth 5 }
    'whatif2' { & $az deployment sub what-if --name chaski-stage2 @common '--parameters' 'deployWorkloads=true' }
    '2'       { $r = Invoke-Az deployment sub create --name chaski-stage2 @common '--parameters' 'deployWorkloads=true'; $r.properties.outputs | ConvertTo-Json -Depth 5 }
    'seed' {
        $o = Get-Outputs
        $kv = $o.keyVaultName.value
        $pgHost = "$($o.postgresServerName.value).postgres.database.azure.com"
        $tmp = Join-Path ([IO.Path]::GetTempPath()) ("chaski-seed-" + [guid]::NewGuid())
        New-Item -ItemType Directory $tmp | Out-Null
        $expires = (Get-Date).ToUniversalTime().AddDays(180).ToString('yyyy-MM-ddTHH:mm:ssZ')

        function Get-Existing([string]$Name) {
            for ($i = 0; $i -lt 12; $i++) {   # RBAC propagation can take a few minutes
                $v = & $az keyvault secret show --vault-name $kv --name $Name --query value -o tsv 2>&1
                if ($LASTEXITCODE -eq 0) { return $v }
                if ("$v" -match 'SecretNotFound') { return $null }
                Write-Host "  waiting for Key Vault access ($($i + 1)/12)..."; Start-Sleep -Seconds 20
            }
            throw "Cannot read Key Vault $kv"
        }
        function Set-Secret([string]$Name, [string]$Value) {
            $f = Join-Path $tmp $Name
            [IO.File]::WriteAllText($f, $Value)
            try {
                & $az keyvault secret set --vault-name $kv --name $Name --file $f --encoding utf-8 --expires $expires --only-show-errors -o none
                if ($LASTEXITCODE -ne 0) { throw "Cannot set secret $Name" }
            } finally { Remove-Item $f -Force }
            Write-Host "  [ok] $Name (expires $expires)"
        }
        function Ensure-Secret([string]$Name, [scriptblock]$Make) {
            $v = Get-Existing $Name
            if ($null -ne $v) { Write-Host "  [keep] $Name"; return $v }
            $v = & $Make
            Set-Secret $Name $v
            return $v
        }

        try {
            Write-Host "Seeding secrets into $kv"
            $admin = Ensure-Secret 'pg-admin-password' { New-Secret 32 }
            $app = Ensure-Secret 'pg-app-password' { New-Secret 32 }
            $ro = Ensure-Secret 'pg-readonly-password' { New-Secret 32 }
            Ensure-Secret 'fraud-webhook-secret' { New-Secret 48 } | Out-Null
            $base = "@${pgHost}:5432/chaski?sslmode=require"
            Ensure-Secret 'database-url' { "postgresql+psycopg://chaski_app:$app$base" } | Out-Null
            Ensure-Secret 'analytics-db-url' { "postgresql+psycopg://chaski_app:$app$base" } | Out-Null
            Ensure-Secret 'nl2sql-db-url' { "postgresql+psycopg://chaski_readonly:$ro$base" } | Out-Null
            Ensure-Secret 'migrations-database-url' { "postgresql+psycopg://chaski_admin:$admin$base" } | Out-Null
        } finally { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }
    }
}
