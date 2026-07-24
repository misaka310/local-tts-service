param(
    [string]$ConfigPath = "",
    [switch]$OpenBrowser,
    [switch]$SkipKillPort,
    [switch]$NoInstall
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot 'managed-processes.ps1')
. (Join-Path $PSScriptRoot 'no-window-process.ps1')
. (Join-Path $PSScriptRoot 'node-runtime.ps1')

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

function Resolve-OptionalConfigPath {
    param(
        [object]$Value,
        [string]$BasePath
    )
    $raw = [string]$Value
    if ([string]::IsNullOrWhiteSpace($raw)) { return "" }
    if ([System.IO.Path]::IsPathRooted($raw)) {
        return [System.IO.Path]::GetFullPath($raw)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $BasePath $raw))
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

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$frontendDir = Join-Path $repoRoot "frontend"
if (-not (Test-Path $frontendDir -PathType Container)) {
    throw "frontend directory not found: $frontendDir"
}

$configCandidates = @()
if ($ConfigPath -and $ConfigPath.Trim() -ne "") {
    if ([System.IO.Path]::IsPathRooted($ConfigPath)) { $configCandidates += $ConfigPath }
    else { $configCandidates += (Join-Path $repoRoot $ConfigPath) }
}
$configCandidates += (Join-Path $repoRoot "config/config.local.json")
$configCandidates += (Join-Path $repoRoot "config.local.json")
$configCandidates += (Join-Path $repoRoot "config/config.irodori.example.json")
$configCandidates += (Join-Path $repoRoot "config/config.example.json")

$config = $null
foreach ($candidate in $configCandidates | Select-Object -Unique) {
    $loaded = Read-JsonFile -Path $candidate
    if ($null -ne $loaded) {
        $config = $loaded
        break
    }
}
if ($null -eq $config) {
    throw "config not found"
}

$bindHost = [string](Get-PropertyValue -Object $config -Name "host" -Default "127.0.0.1")
$port = [int](Get-PropertyValue -Object $config -Name "port" -Default 8730)
$ttsBaseUrl = "http://$bindHost`:$port"
$ttsHealthUrl = "$ttsBaseUrl/health"

if (-not (Test-Health -Url $ttsHealthUrl)) {
    throw "local-tts-service is not running: $ttsHealthUrl`n先に .\\local-tts.bat を実行してください。"
}

$frontendCfg = Get-PropertyValue -Object $config -Name "frontend"
$frontHost = [string](Get-PropertyValue -Object $frontendCfg -Name "host" -Default "127.0.0.1")
$frontPort = [int](Get-PropertyValue -Object $frontendCfg -Name "port" -Default 5177)
$frontUrl = "http://$frontHost`:$frontPort"

$rvcCfg = Get-PropertyValue -Object $config -Name "rvc"
$rvcRoot = Resolve-OptionalConfigPath -Value (Get-PropertyValue -Object $rvcCfg -Name "rootDir" -Default "") -BasePath $repoRoot
$rvcPython = Resolve-OptionalConfigPath -Value (Get-PropertyValue -Object $rvcCfg -Name "pythonPath" -Default "") -BasePath $repoRoot
$rvcCwd = Resolve-OptionalConfigPath -Value (Get-PropertyValue -Object $rvcCfg -Name "cwd" -Default "") -BasePath $repoRoot
$rvcModelPath = Resolve-OptionalConfigPath -Value (Get-PropertyValue -Object $rvcCfg -Name "modelPath" -Default "") -BasePath $repoRoot
$rvcIndexPath = Resolve-OptionalConfigPath -Value (Get-PropertyValue -Object $rvcCfg -Name "indexPath" -Default "") -BasePath $repoRoot
$rvcExternalAudioPath = Resolve-OptionalConfigPath -Value (Get-PropertyValue -Object $rvcCfg -Name "externalAudioPath" -Default "") -BasePath $repoRoot

if ($rvcRoot) {
    if (-not $rvcPython) { $rvcPython = Join-Path $rvcRoot ".venv/Scripts/python.exe" }
    if (-not $rvcCwd) { $rvcCwd = Join-Path $rvcRoot "vendor/rvc" }
}

if ($rvcRoot -and -not (Test-Path -LiteralPath $rvcRoot -PathType Container)) {
    throw "RVC root directory not found: $rvcRoot"
}
if ($rvcPython -and -not (Test-Path -LiteralPath $rvcPython -PathType Leaf)) {
    throw "RVC python not found: $rvcPython"
}
if ($rvcCwd -and -not (Test-Path -LiteralPath $rvcCwd -PathType Container)) {
    throw "RVC cwd not found: $rvcCwd"
}
if ($rvcModelPath -and -not (Test-Path -LiteralPath $rvcModelPath -PathType Leaf)) {
    throw "RVC model not found: $rvcModelPath"
}
if ($rvcIndexPath -and -not (Test-Path -LiteralPath $rvcIndexPath -PathType Leaf)) {
    throw "RVC index not found: $rvcIndexPath"
}
if ($rvcExternalAudioPath -and -not (Test-Path -LiteralPath $rvcExternalAudioPath -PathType Leaf)) {
    throw "RVC external audio not found: $rvcExternalAudioPath"
}

if ($SkipKillPort) {
    Write-Host '[INFO] SkipKillPort is deprecated; frontend startup never force-kills a port owner.'
}

$nodeRuntime = Resolve-LocalTtsNodeRuntime -RepoRoot $repoRoot
Write-Host "[INFO] Node.js runtime: $($nodeRuntime.Source) ($($nodeRuntime.NodeDir))"
$npmSource = $nodeRuntime.NpmPath
$nodeSource = $nodeRuntime.NodePath

$nodeModulesDir = Join-Path $frontendDir "node_modules"
if (-not $NoInstall -and -not (Test-Path $nodeModulesDir -PathType Container)) {
    Write-Host "[INFO] frontend dependencies are missing. running npm install..."
    Push-Location $frontendDir
    try {
        & $npmSource install
        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed"
        }
    }
    finally {
        Pop-Location
    }
}

if (Test-Health -Url "$frontUrl/api/health") {
    if (-not [string]::IsNullOrWhiteSpace($env:LOCAL_TTS_MANAGED_SESSION_ID)) {
        $recordPath = Get-ManagedProcessRecordPath -RepoRoot $repoRoot -Service 'frontend'
        $record = if (Test-Path -LiteralPath $recordPath -PathType Leaf) { Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }
        if ($null -eq $record -or [string]$record.sessionId -ne [string]$env:LOCAL_TTS_MANAGED_SESSION_ID -or -not (Test-ManagedProcessRecord -Record $record -RepoRoot $repoRoot).valid) {
            throw "frontend address is already in use by a process not started by this launch: $frontUrl"
        }
    }
    Write-Host "[INFO] frontend already running: $frontUrl"
    if ($OpenBrowser) { Start-Process $frontUrl }
    exit 0
}

$logDir = Join-Path $repoRoot "runtime/logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "tts-frontend.out.log"
$errLog = Join-Path $logDir "tts-frontend.err.log"

$env:TTS_FRONT_HOST = $frontHost
$env:TTS_FRONT_PORT = [string]$frontPort
$env:TTS_API_BASE_URL = $ttsBaseUrl
$env:LOCAL_TTS_RVC_ROOT = $rvcRoot
$env:LOCAL_TTS_RVC_PYTHON = $rvcPython
$env:LOCAL_TTS_RVC_CWD = $rvcCwd
$env:LOCAL_TTS_RVC_MODEL_PATH = $rvcModelPath
$env:LOCAL_TTS_RVC_INDEX_PATH = $rvcIndexPath
$env:LOCAL_TTS_RVC_EXTERNAL_AUDIO_PATH = $rvcExternalAudioPath

if ($rvcModelPath -and $rvcIndexPath) {
    Write-Host "[INFO] RVC configured: model=$rvcModelPath"
    Write-Host "[INFO] RVC index configured: $rvcIndexPath"
}

$repoMarker = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$repoRoot))
$processArgs = @('server.js', '--local-tts-managed-service', 'frontend', '--local-tts-managed-repo-b64', $repoMarker)
$proc = Start-LocalTtsNoWindowProcess -FilePath $nodeSource -ArgumentList $processArgs -WorkingDirectory $frontendDir -StandardOutputPath $outLog -StandardErrorPath $errLog -RepoRoot $repoRoot

$null = Register-ManagedProcess -RepoRoot $repoRoot -Service 'frontend' -Process $proc -ExpectedCommandFragments @('server.js', '--local-tts-managed-service', 'frontend', '--local-tts-managed-repo-b64', $repoMarker) -HealthUrl "$frontUrl/api/health" -Port $frontPort

$deadline = (Get-Date).AddSeconds(45)
while ((Get-Date) -lt $deadline) {
    if (Test-Health -Url "$frontUrl/api/health") {
        Write-Host "[DONE] frontend started: $frontUrl (pid=$($proc.Id))"
        Write-Host "[INFO] logs: $outLog / $errLog"
        if ($OpenBrowser) { Start-Process $frontUrl }
        exit 0
    }
    Start-Sleep -Milliseconds 500
}

throw "frontend startup timed out: $frontUrl (logs: $outLog / $errLog)"
