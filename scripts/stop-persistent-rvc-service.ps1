[CmdletBinding()]
param([string]$ConfigPath = '')

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ConfigPath)) { $ConfigPath = Join-Path $repo 'config\rvc-persistent.local.json' }
$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
function Assert-LoopbackHost {
    param([Parameter(Mandatory = $true)][string]$EndpointHost)
    if ($EndpointHost.Trim().ToLowerInvariant() -eq 'localhost') { return }
    $address = $null
    if (-not [Net.IPAddress]::TryParse($EndpointHost, [ref]$address) -or -not [Net.IPAddress]::IsLoopback($address)) {
        throw "Persistent RVC endpoints must use loopback addresses: $EndpointHost"
    }
}
Assert-LoopbackHost -EndpointHost ([string]$config.host)
$baseUrl = "http://$([string]$config.host):$([int]$config.port)"
$statePath = Join-Path $repo 'runtime\persistent-rvc\state.json'
$requested = $false
try {
    $response = Invoke-RestMethod -Method Post -Uri "$baseUrl/shutdown" -ContentType 'application/json' -Body '{}' -TimeoutSec 5
    $requested = [bool]$response.ok
} catch { }

$deadline = [DateTime]::UtcNow.AddSeconds(30)
$stopped = $false
do {
    try { Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 2 | Out-Null } catch { $stopped = $true }
    if ($stopped) { break }
    Start-Sleep -Milliseconds 250
} while ([DateTime]::UtcNow -lt $deadline)

if (-not $stopped -and (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $pidValue = [int]$state.pid
        $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        if ($null -ne $process) { Stop-Process -Id $pidValue -Force -ErrorAction Stop }
    } catch { }
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        try { Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 2 | Out-Null } catch { $stopped = $true }
        if ($stopped) { break }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
}
if (-not $stopped) { throw "Persistent RVC service remained reachable at $baseUrl" }
[pscustomobject]@{ status='stopped'; shutdownRequested=$requested; baseUrl=$baseUrl } | ConvertTo-Json -Compress
