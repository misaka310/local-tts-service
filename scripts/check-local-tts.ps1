param(
    [string]$ConfigPath = "config/config.local.json",
    [switch]$Deep,
    [switch]$CheckOptionalServices
)

$ErrorActionPreference = "Continue"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$configPath = if ([System.IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath } else { Join-Path $repoRoot $ConfigPath }
$hasFailure = $false

function Get-PropertyValue {
    param(
        [object]$Object,
        [string]$Name,
        [object]$Default = $null
    )
    if ($null -eq $Object) { return $Default }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value) { return $Default }
    return $property.Value
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

function Test-Url {
    param(
        [string]$Url,
        [string]$Label,
        [int]$TimeoutSec = 3,
        [ValidateSet("FAIL", "WARN")][string]$FailureLevel = "FAIL"
    )
    try {
        $response = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec $TimeoutSec -ErrorAction Stop
        Write-Host "[OK] $Label is reachable ($Url)" -ForegroundColor Green
        return $response
    }
    catch {
        $color = if ($FailureLevel -eq "WARN") { "Yellow" } else { "Red" }
        Write-Host "[$FailureLevel] $Label is unreachable ($Url) | $($_.Exception.Message)" -ForegroundColor $color
        return $null
    }
}

Write-Host "========== local-tts-service Diagnostics ==========" -ForegroundColor Cyan

$config = $null
if (Test-Path $configPath -PathType Leaf) {
    Write-Host "[OK] config/config.local.json exists: $configPath" -ForegroundColor Green
    $config = Get-Content -Path $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
}
else {
    Write-Host "[WARN] config/config.local.json not found. Service will fallback to config/config.example.json" -ForegroundColor Yellow
    $examplePath = Join-Path $repoRoot "config/config.example.json"
    if (Test-Path $examplePath -PathType Leaf) {
        $config = Get-Content -Path $examplePath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
}

$hostUrl = "127.0.0.1"
$backendPort = 8730
$frontendHost = "127.0.0.1"
$frontendPort = 5177
$defaultModel = ""
$defaultVoice = ""
$comfyEnabled = $false
$comfyRequired = $false
$comfyUrl = "http://127.0.0.1:8288"

if ($null -ne $config) {
    $hostUrl = [string](Get-PropertyValue -Object $config -Name "host" -Default "127.0.0.1")
    $backendPort = [int](Get-PropertyValue -Object $config -Name "port" -Default 8730)
    $defaultModel = [string](Get-PropertyValue -Object $config -Name "defaultModel" -Default "")
    $defaultVoice = [string](Get-PropertyValue -Object $config -Name "defaultReferenceVoice" -Default "")

    $frontend = Get-PropertyValue -Object $config -Name "frontend"
    $frontendHost = [string](Get-PropertyValue -Object $frontend -Name "host" -Default "127.0.0.1")
    $frontendPort = [int](Get-PropertyValue -Object $frontend -Name "port" -Default 5177)

    $models = Get-PropertyValue -Object $config -Name "models"
    $comfyRequired = Test-ModelRuntimeConfigured -Models $models -RuntimeNames @("comfyui", "comfyui_voxcpm2")
    $externalServices = Get-PropertyValue -Object $config -Name "externalServices"
    $comfyService = Get-PropertyValue -Object $externalServices -Name "comfyui"
    $comfyEnabled = [bool](Get-PropertyValue -Object $comfyService -Name "enabled" -Default $false)
    $runtimes = Get-PropertyValue -Object $config -Name "runtimes"
    $comfyRuntime = Get-PropertyValue -Object $runtimes -Name "comfyui"
    $comfyUrl = [string](Get-PropertyValue -Object $comfyRuntime -Name "baseUrl" -Default "http://127.0.0.1:8288")
}

$backendHealth = "http://$hostUrl`:$backendPort/health"
$backendDeepHealth = "http://$hostUrl`:$backendPort/health/deep"
$frontendHealth = "http://$frontendHost`:$frontendPort/api/health"

Write-Host "`n--- Checking Backend ---" -ForegroundColor Blue
$backRes = Test-Url -Url $backendHealth -Label "Backend Health"
if ($null -eq $backRes) { $hasFailure = $true }
elseif ($backRes.status -eq "healthy") {
    Write-Host "[OK] Backend status: healthy (defaultModel=$($backRes.defaultModel))" -ForegroundColor Green
}
else {
    Write-Host "[WARN] Backend status: $($backRes.status)" -ForegroundColor Yellow
}

Write-Host "`n--- Checking Backend Deep Health ---" -ForegroundColor Blue
if (-not $Deep) {
    Write-Host "[SKIP] Deep diagnostics skipped. Run scripts/check-local-tts.ps1 -Deep for model and external-runtime checks." -ForegroundColor Yellow
}
else {
    $deepRes = Test-Url -Url $backendDeepHealth -Label "Backend Deep Health" -TimeoutSec 300 -FailureLevel "WARN"
    if ($null -ne $deepRes) {
        $modelChecks = @($deepRes.modelChecks.PSObject.Properties | ForEach-Object { $_.Value })
        $availableCount = @($modelChecks | Where-Object { [bool]$_.available }).Count
        $unavailableCount = $modelChecks.Count - $availableCount
        Write-Host "[INFO] models: available=$availableCount unavailable=$unavailableCount"
        if (-not $deepRes.ok) {
            Write-Host "[WARN] One or more required runtime checks failed." -ForegroundColor Yellow
        }
    }
}

if ($CheckOptionalServices -and $comfyRequired) {
    Write-Host "`n--- Checking required optional runtime ---" -ForegroundColor Blue
    if (-not $comfyEnabled) {
        Write-Host "[FAIL] A configured model requires ComfyUI, but externalServices.comfyui.enabled=false" -ForegroundColor Red
        $hasFailure = $true
    }
    else {
        $comfyRes = Test-Url -Url "$comfyUrl/system_stats" -Label "Required ComfyUI runtime"
        if ($null -eq $comfyRes) { $hasFailure = $true }
    }
}

Write-Host "`n--- Checking Frontend ---" -ForegroundColor Blue
$frontRes = Test-Url -Url $frontendHealth -Label "Frontend Health"
if ($null -eq $frontRes) { $hasFailure = $true }
elseif ($frontRes.ok) {
    Write-Host "[OK] Frontend is healthy" -ForegroundColor Green
}
else {
    Write-Host "[WARN] Frontend returned ok=false" -ForegroundColor Yellow
}

Write-Host "`n==================================================" -ForegroundColor Cyan
if (-not [string]::IsNullOrWhiteSpace($defaultModel)) {
    Write-Host "[INFO] config defaultModel=$defaultModel"
}
if (-not [string]::IsNullOrWhiteSpace($defaultVoice)) {
    Write-Host "[INFO] config defaultReferenceVoice=$defaultVoice"
}
if ($hasFailure) {
    Write-Host "[FAIL] One or more required services are unavailable." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Required services are available." -ForegroundColor Green
exit 0
