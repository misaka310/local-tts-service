[CmdletBinding()]
param(
    [string]$ConfigPath = 'config/config.local.json',
    [int]$StartupTimeoutSec = 180
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'deployment-role.ps1')

function Read-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    return ($raw | ConvertFrom-Json)
}

function Get-PropertyValue {
    param([object]$Object, [string]$Name, [object]$Default = $null)
    if ($null -eq $Object) { return $Default }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value) { return $Default }
    return $property.Value
}

function Get-LoopbackHealthHost {
    param([string]$HostName)
    if ([string]::IsNullOrWhiteSpace($HostName) -or $HostName -in @('0.0.0.0', '::', '[::]')) { return '127.0.0.1' }
    return $HostName
}

function Test-Health {
    param([Parameter(Mandatory = $true)][string]$Url)
    try {
        $null = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 2 -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$configLocalPath = if ([IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath } else { Join-Path $repoRoot $ConfigPath }
$config = Read-JsonFile -Path $configLocalPath
if ($null -eq $config) { throw "config file not found: $configLocalPath" }

$deployment = Get-LocalTtsDeploymentSettings -Config $config
$frontend = Get-PropertyValue -Object $config -Name 'frontend'
$frontHost = [string](Get-PropertyValue -Object $frontend -Name 'host' -Default '127.0.0.1')
$frontPort = [int](Get-PropertyValue -Object $frontend -Name 'port' -Default 5177)
$frontHealthHost = Get-LoopbackHealthHost -HostName $frontHost
$frontendLocalHealthUrl = "http://$frontHealthHost`:$frontPort/api/frontend-health"
$gatewayHealthUrl = "http://$frontHealthHost`:$frontPort/api/health"

$configuredBackendHost = [string](Get-PropertyValue -Object $config -Name 'host' -Default '127.0.0.1')
$backendHost = if (-not [string]::IsNullOrWhiteSpace($deployment.BackendHost)) { [string]$deployment.BackendHost } else { $configuredBackendHost }
$backendHealthHost = Get-LoopbackHealthHost -HostName $backendHost
$backendPort = [int](Get-PropertyValue -Object $config -Name 'port' -Default 8730)
$backendHealthUrl = "http://$backendHealthHost`:$backendPort/health"

function Test-RoleHealthy {
    switch ($deployment.Role) {
        'frontend' { return (Test-Health -Url $frontendLocalHealthUrl) }
        'worker' { return (Test-Health -Url $gatewayHealthUrl) }
        default { return (Test-Health -Url $backendHealthUrl) -and (Test-Health -Url $frontendLocalHealthUrl) }
    }
}

if (Test-RoleHealthy) {
    Write-Host "[OK] local-tts-service role '$($deployment.Role)' is healthy"
    exit 0
}

Write-Warning "local-tts-service role '$($deployment.Role)' is incomplete or stopped; repairing the managed stack."
& (Join-Path $PSScriptRoot 'start-local-tts-stack.ps1') `
    -ConfigPath $configLocalPath `
    -SkipStopManagedProcesses `
    -StartFrontend `
    -StartupTimeoutSec $StartupTimeoutSec

if (-not (Test-RoleHealthy)) {
    throw "local-tts-service role '$($deployment.Role)' did not become healthy after repair (timeout hint: ${StartupTimeoutSec}s)"
}

Write-Host "[DONE] local-tts-service role '$($deployment.Role)' recovered"
