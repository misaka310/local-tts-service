[CmdletBinding()]
param(
    [string]$ConfigPath = "config/config.local.json",
    [switch]$SkipStopManagedProcesses,
    [switch]$SkipKillPorts,
    [switch]$RunSmoke,
    [switch]$OpenFrontend,
    [switch]$StartFrontend,
    [switch]$NoComfyUIStart,
    [switch]$NoGptSovitsStart
)

$ErrorActionPreference = "Stop"

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

function Test-Health {
    param([string]$Url)
    try {
        $null = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 2 -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

function Format-ElapsedSeconds {
    param([System.Diagnostics.Stopwatch]$Stopwatch)
    return ('{0:0.0}s' -f $Stopwatch.Elapsed.TotalSeconds)
}

function Test-ModelRuntimeConfigured {
    param(
        [object]$Models,
        [string[]]$RuntimeNames
    )
    if ($null -eq $Models) { return $false }
    foreach ($property in $Models.PSObject.Properties) {
        $runtimeName = [string](Get-PropertyValue -Object $property.Value -Name "runtime" -Default "")
        if ($RuntimeNames -contains $runtimeName) { return $true }
    }
    return $false
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$configLocalPath = if ([System.IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath } else { Join-Path $repoRoot $ConfigPath }
$configExamplePath = Join-Path $repoRoot "config/config.example.json"
$configIrodoriPath = Join-Path $repoRoot "config/config.irodori.example.json"
$configQwen3Path = Join-Path $repoRoot "config/config.qwen3.example.json"

if (-not (Test-Path $configLocalPath -PathType Leaf)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $configLocalPath) | Out-Null
    if (Test-Path $configExamplePath -PathType Leaf) {
        Copy-Item -Path $configExamplePath -Destination $configLocalPath -Force
        Write-Host "[INFO] $ConfigPath was created from config/config.example.json"
    }
    elseif (Test-Path $configIrodoriPath -PathType Leaf) {
        Copy-Item -Path $configIrodoriPath -Destination $configLocalPath -Force
        Write-Host "[INFO] $ConfigPath was created from config/config.irodori.example.json"
    }
    elseif (Test-Path $configQwen3Path -PathType Leaf) {
        Copy-Item -Path $configQwen3Path -Destination $configLocalPath -Force
        Write-Host "[INFO] $ConfigPath was created from config/config.qwen3.example.json"
    }
    else {
        throw "$ConfigPath is missing and fallback config templates were not found."
    }
}

$config = Read-JsonFile -Path $configLocalPath
if ($null -eq $config) {
    throw "failed to read $configLocalPath"
}

$stack = Get-PropertyValue -Object $config -Name "stack"
$stopManagedProcessesBeforeStart = [bool](Get-PropertyValue -Object $stack -Name "stopManagedProcessesBeforeStart" -Default $true)
$startupTimeoutSec = [int](Get-PropertyValue -Object $stack -Name "startupTimeoutSec" -Default 180)
$pollIntervalSec = [double](Get-PropertyValue -Object $stack -Name "pollIntervalSec" -Default 1.0)

$modelsConfig = Get-PropertyValue -Object $config -Name "models"
$runtimes = Get-PropertyValue -Object $config -Name "runtimes"
$comfyRuntime = Get-PropertyValue -Object $runtimes -Name "comfyui"
$comfyBaseUrl = [string](Get-PropertyValue -Object $comfyRuntime -Name "baseUrl" -Default "http://127.0.0.1:8288")
$externalServices = Get-PropertyValue -Object $config -Name "externalServices"
$comfyService = Get-PropertyValue -Object $externalServices -Name "comfyui"
$comfyEnabled = [bool](Get-PropertyValue -Object $comfyService -Name "enabled" -Default $false)
$comfyRequired = Test-ModelRuntimeConfigured -Models $modelsConfig -RuntimeNames @("comfyui", "comfyui_voxcpm2")
$comfyShouldStart = $comfyEnabled -and $comfyRequired
$comfyHealthUrl = [string](Get-PropertyValue -Object $comfyService -Name "healthUrl" -Default "$comfyBaseUrl/system_stats")
$gptSovitsService = Get-PropertyValue -Object $externalServices -Name "gptSovits"
$gptSovitsRootRaw = [string](Get-PropertyValue -Object $gptSovitsService -Name "rootDir" -Default "./runtime/vendor/GPT-SoVITS")
$gptSovitsRoot = if ([System.IO.Path]::IsPathRooted($gptSovitsRootRaw)) {
    [System.IO.Path]::GetFullPath($gptSovitsRootRaw)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $gptSovitsRootRaw))
}
$gptSovitsEnabled = [bool](Get-PropertyValue -Object $gptSovitsService -Name "enabled" -Default $false)

$bindHost = [string](Get-PropertyValue -Object $config -Name "host" -Default "127.0.0.1")
$port = [int](Get-PropertyValue -Object $config -Name "port" -Default 8730)
$localTtsBaseUrl = "http://$bindHost`:$port"
$defaultModel = [string](Get-PropertyValue -Object $config -Name "defaultModel" -Default "")
$frontendConfig = Get-PropertyValue -Object $config -Name "frontend"
$frontendHost = [string](Get-PropertyValue -Object $frontendConfig -Name "host" -Default "127.0.0.1")
$frontendPort = [int](Get-PropertyValue -Object $frontendConfig -Name "port" -Default 5177)
$frontendUrl = "http://$frontendHost`:$frontendPort"
$gptSovitsApiUrl = if ($env:LOCAL_TTS_GPT_SOVITS_API_URL) {
    $env:LOCAL_TTS_GPT_SOVITS_API_URL
} else {
    [string](Get-PropertyValue -Object $gptSovitsService -Name "apiUrl" -Default 'http://127.0.0.1:9880/tts')
}

$overallTimer = [System.Diagnostics.Stopwatch]::StartNew()
$backendHealthElapsed = 'not run'
$modelCheckElapsed = 'not run'
$frontendElapsed = 'not run'

Write-Host 'Stopping previously managed app processes...'
if (-not $SkipStopManagedProcesses -and -not $SkipKillPorts -and $stopManagedProcessesBeforeStart) {
    & (Join-Path $PSScriptRoot "stop-managed-processes.ps1") -RepoRoot $repoRoot
}
else {
    Write-Host "[SKIP] managed process stop (SkipStopManagedProcesses=$SkipStopManagedProcesses, deprecated SkipKillPorts=$SkipKillPorts, stack.stopManagedProcessesBeforeStart=$stopManagedProcessesBeforeStart)"
}

if ($comfyShouldStart) {
    if (-not $NoComfyUIStart) {
        Write-Host 'Starting required ComfyUI runtime...'
        & (Join-Path $PSScriptRoot "start-comfyui-runtime.ps1") -ConfigPath $configLocalPath
        if (-not (Test-Health -Url $comfyHealthUrl)) {
            throw "ComfyUI health check failed: $comfyHealthUrl"
        }
        Write-Host '[DONE] required ComfyUI runtime is ready'
    }
    elseif (-not (Test-Health -Url $comfyHealthUrl)) {
        throw "A configured model requires ComfyUI, but NoComfyUIStart=true and ComfyUI is not running: $comfyHealthUrl"
    }
}

if ($gptSovitsEnabled -and -not $NoGptSovitsStart) {
    if (-not (Test-Path -LiteralPath $gptSovitsRoot -PathType Container)) {
        Write-Warning "GPT-SoVITS is explicitly enabled but not installed: $gptSovitsRoot"
        Write-Warning "Run setup-gpt-sovits.bat, or set externalServices.gptSovits.enabled=false."
    }
    else {
        Write-Host 'Starting enabled GPT-SoVITS API...'
        try {
            & (Join-Path $PSScriptRoot "start-gpt-sovits-api.ps1") -GptSovitsRoot $gptSovitsRoot -NoSetup
        }
        catch {
            Write-Warning ("GPT-SoVITS API could not be started: " + $_.Exception.Message)
            Write-Warning ("GPT-SoVITS models will stay unavailable until " + $gptSovitsApiUrl + " is reachable.")
        }
    }
}

Write-Host 'Starting backend...'
$backendTimer = [System.Diagnostics.Stopwatch]::StartNew()
& (Join-Path $PSScriptRoot "start-local-tts.ps1") -ConfigPath $configLocalPath -Background -WaitForHealth -StartupTimeoutSec $startupTimeoutSec -PollIntervalSec $pollIntervalSec
$backendTimer.Stop()
$backendHealthElapsed = Format-ElapsedSeconds -Stopwatch $backendTimer
Write-Host "[DONE] backend health is ready ($backendHealthElapsed)"

Write-Host 'Checking available models (startup check; external WSL probes are skipped)...'
$modelTimer = [System.Diagnostics.Stopwatch]::StartNew()
$models = Invoke-RestMethod -Method Get -Uri "$localTtsBaseUrl/v1/models?probe=false"
$modelTimer.Stop()
$modelCheckElapsed = Format-ElapsedSeconds -Stopwatch $modelTimer
if (-not $models.ok) { throw "/v1/models?probe=false returned ok=false" }
$registeredModels = @($models.models)
if ($registeredModels.Count -lt 1) {
    throw "no models were registered in /v1/models?probe=false"
}
$availableModels = @($registeredModels | Where-Object { [bool]$_.available })
if ($availableModels.Count -lt 1) {
    throw "no available models were found by the lightweight startup check. Run check-local-tts.bat for details."
}
$defaultModelInfo = $registeredModels | Where-Object { $_.model -eq $defaultModel -or $_.id -eq $defaultModel } | Select-Object -First 1
if ($null -ne $defaultModelInfo -and -not [bool]$defaultModelInfo.available) {
    Write-Warning "Default model '$defaultModel' is not currently available: $($defaultModelInfo.unavailableReason)"
}
Write-Host "[DONE] available models confirmed: $($availableModels.Count) ($modelCheckElapsed; external probes skipped)"

if ($RunSmoke) {
    $modelNames = @($registeredModels | ForEach-Object { $_.model })
    if ($modelNames -contains "irodori_v2") {
        Write-Host 'Running smoke test for irodori_v2...'
        & (Join-Path $PSScriptRoot "smoke-irodori-v2.ps1") -BaseUrl $localTtsBaseUrl -ConfigPath $configLocalPath
    } else {
        Write-Host '[SKIP] irodori_v2 model is not registered'
    }
}

if ($OpenFrontend -or $StartFrontend) {
    Write-Host 'Starting frontend...'
    $frontendTimer = [System.Diagnostics.Stopwatch]::StartNew()
    & (Join-Path $PSScriptRoot "start-tts-frontend.ps1") -ConfigPath $configLocalPath -OpenBrowser:$OpenFrontend
    $frontendTimer.Stop()
    $frontendElapsed = Format-ElapsedSeconds -Stopwatch $frontendTimer
    Write-Host "[DONE] frontend is ready ($frontendElapsed)"
}

$overallTimer.Stop()
$logsDir = Join-Path $repoRoot "runtime/logs"

Write-Host ""
Write-Host "========== Stack Ready =========="
Write-Host "backend: $localTtsBaseUrl"
if ($OpenFrontend -or $StartFrontend) { Write-Host "started: $frontendUrl" }
else { Write-Host "frontend: not started by this command" }
Write-Host "backend health: $backendHealthElapsed"
Write-Host "model check: $modelCheckElapsed"
Write-Host "frontend startup: $frontendElapsed"
Write-Host "total startup: $(Format-ElapsedSeconds -Stopwatch $overallTimer)"
Write-Host "logs: $logsDir"
Write-Host "Detailed model diagnostics: GET $localTtsBaseUrl/v1/models or run check-local-tts.bat"
Write-Host "================================="
