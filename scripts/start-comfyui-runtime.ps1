param(
    [string]$ConfigPath = "",
    [switch]$RunPortKill,
    [switch]$NoWait,
    [switch]$VisibleWindow
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot 'managed-processes.ps1')

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path $Path -PathType Leaf)) { return $null }
    $raw = Get-Content -Path $Path -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    return ($raw | ConvertFrom-Json)
}

function Get-PropertyValue {
    param(
        [object]$Object,
        [string]$Name,
        [object]$Default = $null
    )
    if ($null -eq $Object) { return $Default }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    if ($null -eq $prop.Value) { return $Default }
    return $prop.Value
}

function Resolve-RepoPath {
    param([string]$RepoRoot, [string]$RawPath)
    if ([string]::IsNullOrWhiteSpace($RawPath)) { return "" }
    if ([System.IO.Path]::IsPathRooted($RawPath)) { return $RawPath }
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $RawPath))
}

function Test-Health {
    param([string]$Url)
    if ([string]::IsNullOrWhiteSpace($Url)) { return $false }
    try {
        $null = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 2 -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$configCandidates = @()
if ($ConfigPath -and $ConfigPath.Trim() -ne "") {
    if ([System.IO.Path]::IsPathRooted($ConfigPath)) { $configCandidates += $ConfigPath }
    else { $configCandidates += (Join-Path $repoRoot $ConfigPath) }
}
$configCandidates += (Join-Path $repoRoot "config/config.local.json")
$configCandidates += (Join-Path $repoRoot "config.local.json")
$configCandidates += (Join-Path $repoRoot "config/config.irodori.example.json")
$configCandidates += (Join-Path $repoRoot "config/config.example.json")

$loadedConfigs = @()
foreach ($candidate in $configCandidates | Select-Object -Unique) {
    $loaded = Read-JsonFile -Path $candidate
    if ($null -ne $loaded) {
        $loadedConfigs += [PSCustomObject]@{
            Path = $candidate
            Config = $loaded
        }
    }
}
if ($loadedConfigs.Count -eq 0) {
    throw "Config file was not found. Expected config/config.local.json or an example config."
}
$config = $loadedConfigs[0].Config
$configSource = [string]$loadedConfigs[0].Path

$stack = Get-PropertyValue -Object $config -Name "stack"
if ($null -eq $stack) {
    foreach ($entry in $loadedConfigs) {
        $candidateStack = Get-PropertyValue -Object $entry.Config -Name "stack"
        if ($null -ne $candidateStack) {
            $stack = $candidateStack
            break
        }
    }
}
$startupTimeoutSec = [int](Get-PropertyValue -Object $stack -Name "startupTimeoutSec" -Default 180)
$pollIntervalSec = [double](Get-PropertyValue -Object $stack -Name "pollIntervalSec" -Default 1.0)

$comfy = $null
foreach ($entry in $loadedConfigs) {
    $external = Get-PropertyValue -Object $entry.Config -Name "externalServices"
    $candidateComfy = Get-PropertyValue -Object $external -Name "comfyui"
    if ($null -ne $candidateComfy) {
        $comfy = $candidateComfy
        if ($entry.Path -ne $configSource) {
            Write-Host "[INFO] externalServices.comfyui loaded from fallback: $($entry.Path)"
        }
        break
    }
}
if ($null -eq $comfy) {
    throw "externalServices.comfyui is missing in $configSource"
}

$enabled = [bool](Get-PropertyValue -Object $comfy -Name "enabled" -Default $true)
if (-not $enabled) {
    Write-Host "[SKIP] externalServices.comfyui.enabled=false"
    exit 0
}

$serviceName = [string](Get-PropertyValue -Object $comfy -Name "name" -Default "ComfyUI")
$rootDirRaw = [string](Get-PropertyValue -Object $comfy -Name "rootDir" -Default "")
$startCommand = [string](Get-PropertyValue -Object $comfy -Name "startCommand" -Default "")
$baseUrl = [string](Get-PropertyValue -Object $comfy -Name "baseUrl" -Default "http://127.0.0.1:8288")
$healthUrl = [string](Get-PropertyValue -Object $comfy -Name "healthUrl" -Default "$baseUrl/system_stats")
$rootDir = Resolve-RepoPath -RepoRoot $repoRoot -RawPath $rootDirRaw

if (Test-Health -Url $healthUrl) {
    Write-Host "[INFO] $serviceName already running ($healthUrl)"
    exit 0
}

if ([string]::IsNullOrWhiteSpace($startCommand)) {
    throw "externalServices.comfyui.startCommand is empty. Please set config/config.local.json"
}
if ([string]::IsNullOrWhiteSpace($rootDir) -or -not (Test-Path $rootDir -PathType Container)) {
    throw "externalServices.comfyui.rootDir not found: $rootDir"
}

if ($RunPortKill) {
    Write-Host '[INFO] RunPortKill is deprecated; ComfyUI startup never force-kills arbitrary port owners.'
}

$logDir = Join-Path $repoRoot "runtime/logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "comfyui-runtime.out.log"
$errLog = Join-Path $logDir "comfyui-runtime.err.log"

$windowStyle = if ($VisibleWindow) { "Normal" } else { "Hidden" }
$managedStartCommand = Add-ManagedProcessMarker -Command $startCommand -RepoRoot $repoRoot -Service 'comfyui'
$startArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command", $managedStartCommand
)

$proc = Start-Process -FilePath "powershell.exe" -ArgumentList $startArgs -WorkingDirectory $rootDir -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle $windowStyle -PassThru
$null = Register-ManagedProcess -RepoRoot $repoRoot -Service 'comfyui' -Process $proc -ExpectedCommandFragments @('LOCAL_TTS_MANAGED_SERVICE', 'comfyui', [string]$repoRoot) -HealthUrl $healthUrl
Write-Host "[INFO] started $serviceName pid=$($proc.Id)"
Write-Host "[INFO] config=$configSource"
Write-Host "[INFO] rootDir=$rootDir"
Write-Host "[INFO] healthUrl=$healthUrl"
Write-Host "[INFO] logs=$outLog / $errLog"

if ($NoWait) {
    exit 0
}

$deadline = (Get-Date).AddSeconds($startupTimeoutSec)
while ((Get-Date) -lt $deadline) {
    if (Test-Health -Url $healthUrl) {
        Write-Host "[DONE] $serviceName is healthy"
        exit 0
    }
    Start-Sleep -Milliseconds ([Math]::Max(200, [int]($pollIntervalSec * 1000)))
}

Write-Error "[FAIL] timeout waiting for $serviceName"
Write-Host "startCommand: $startCommand"
Write-Host "healthUrl: $healthUrl"
Write-Host "rootDir: $rootDir"
Write-Host "baseUrl: $baseUrl"
Write-Host "log(out): $outLog"
Write-Host "log(err): $errLog"
throw "$serviceName startup timed out"
