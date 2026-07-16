param(
    [string]$ConfigPath = "config/config.local.json",
    [switch]$SkipFrontend,
    [switch]$TryIrodoriV3
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$configAbs = if ([System.IO.Path]::IsPathRooted($ConfigPath)) {
    $ConfigPath
} else {
    Join-Path $repoRoot $ConfigPath
}

if (-not (Test-Path -LiteralPath $configAbs -PathType Leaf)) {
    $template = Join-Path $repoRoot "config/config.example.json"
    if (-not (Test-Path -LiteralPath $template -PathType Leaf)) {
        throw "config file and public template are missing: $configAbs"
    }
    Copy-Item -LiteralPath $template -Destination $configAbs -Force
}

$startParams = @{ ConfigPath = $configAbs }
if (-not $SkipFrontend) { $startParams['OpenFrontend'] = $true }

$config = Get-Content -LiteralPath $configAbs -Raw -Encoding UTF8 | ConvertFrom-Json
$backendHost = if ($config.backend.host) { [string]$config.backend.host } else { "127.0.0.1" }
$backendPort = if ($config.backend.port) { [int]$config.backend.port } else { 8730 }
$backendBaseUrl = "http://$backendHost`:$backendPort"

Write-Host 'Starting the normal local TTS stack...'
& (Join-Path $PSScriptRoot "start-local-tts-stack.ps1") @startParams

Write-Host 'Generating an Irodori v2 WAV through the current direct runtime...'
& (Join-Path $PSScriptRoot "smoke-irodori-v2.ps1") -BaseUrl $backendBaseUrl -ConfigPath $configAbs

if ($TryIrodoriV3) {
    Write-Host 'Generating an Irodori v3 WAV through the current direct runtime...'
    & (Join-Path $PSScriptRoot "smoke-irodori-v3.ps1") -BaseUrl $backendBaseUrl -ConfigPath $configAbs
}

if (-not $SkipFrontend) {
    $frontendHost = if ($config.frontend.host) { [string]$config.frontend.host } else { "127.0.0.1" }
    $frontendPort = if ($config.frontend.port) { [int]$config.frontend.port } else { 5177 }
    $frontendHealth = Invoke-RestMethod -Method Get -Uri "http://$frontendHost`:$frontendPort/api/health" -TimeoutSec 10
    if (-not $frontendHealth.ok) { throw "frontend health returned ok=false" }
}

Write-Host '[OK] Irodori stack E2E passed' -ForegroundColor Green
