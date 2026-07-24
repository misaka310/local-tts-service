param(
    [string]$ConfigPath = "",
    [switch]$Background,
    [switch]$WaitForHealth,
    [int]$StartupTimeoutSec = 120,
    [double]$PollIntervalSec = 1.0,
    [switch]$VisibleWindow
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot 'managed-processes.ps1')
. (Join-Path $PSScriptRoot 'no-window-process.ps1')

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
    try {
        $null = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 2 -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python -PathType Leaf)) {
    throw ".venv was not found. Run 'python -m venv .venv' first."
}

$configCandidates = @()
if ($ConfigPath -and $ConfigPath.Trim() -ne "") {
    if ([System.IO.Path]::IsPathRooted($ConfigPath)) { $configCandidates += $ConfigPath }
    else { $configCandidates += (Join-Path $repoRoot $ConfigPath) }
}
$configCandidates += (Join-Path $repoRoot "config/config.local.json")
$configCandidates += (Join-Path $repoRoot "config.local.json")
$configCandidates += (Join-Path $repoRoot "config/config.qwen3.example.json")
$configCandidates += (Join-Path $repoRoot "config/config.irodori.example.json")
$configCandidates += (Join-Path $repoRoot "config/config.example.json")

$config = $null
$resolvedConfig = ""
foreach ($candidate in $configCandidates | Select-Object -Unique) {
    $loaded = Read-JsonFile -Path $candidate
    if ($null -ne $loaded) {
        $config = $loaded
        $resolvedConfig = $candidate
        break
    }
}
if ($null -eq $config) {
    throw "config file not found. expected config/config.local.json or config/config.example.json"
}

$bindHost = [string](Get-PropertyValue -Object $config -Name "host" -Default "127.0.0.1")
$port = [int](Get-PropertyValue -Object $config -Name "port" -Default 8730)
$healthUrl = "http://$bindHost`:$port/health"

if (Test-Health -Url $healthUrl) {
    if (-not [string]::IsNullOrWhiteSpace($env:LOCAL_TTS_MANAGED_SESSION_ID)) {
        $recordPath = Get-ManagedProcessRecordPath -RepoRoot $repoRoot -Service 'local-tts-service'
        $record = if (Test-Path -LiteralPath $recordPath -PathType Leaf) { Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }
        if ($null -eq $record -or [string]$record.sessionId -ne [string]$env:LOCAL_TTS_MANAGED_SESSION_ID -or -not (Test-ManagedProcessRecord -Record $record -RepoRoot $repoRoot).valid) {
            throw "backend address is already in use by a process not started by this launch: $healthUrl"
        }
    }
    Write-Host "[INFO] local-tts-service already running ($healthUrl)"
    exit 0
}

$srcPath = Join-Path $repoRoot "src"
$envCheckScript = @'
import importlib
for module_name in ("uvicorn", "fastapi", "local_tts_service"):
    importlib.import_module(module_name)
print("ok")
'@

$env:PYTHONPATH = $srcPath
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$checkScriptPath = Join-Path ([System.IO.Path]::GetTempPath()) ("local-tts-env-check-" + [guid]::NewGuid().ToString('N') + '.py')
$checkOutPath = [System.IO.Path]::GetTempFileName()
$checkErrPath = [System.IO.Path]::GetTempFileName()
$checkProcess = $null
try {
    [System.IO.File]::WriteAllText($checkScriptPath, $envCheckScript, [System.Text.UTF8Encoding]::new($false))
    $checkProcess = Start-LocalTtsNoWindowProcess -FilePath $python -ArgumentList @($checkScriptPath) -WorkingDirectory $repoRoot -StandardOutputPath $checkOutPath -StandardErrorPath $checkErrPath -RepoRoot $repoRoot
    $checkProcess.WaitForExit()
    $checkOutput = @(
        if (Test-Path -LiteralPath $checkOutPath) { Get-Content -LiteralPath $checkOutPath -Raw -Encoding UTF8 }
        if (Test-Path -LiteralPath $checkErrPath) { Get-Content -LiteralPath $checkErrPath -Raw -Encoding UTF8 }
    )
    if ($checkProcess.ExitCode -ne 0) {
        $details = ($checkOutput | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($details)) { $details = "python exit code $($checkProcess.ExitCode)" }
        throw "Dependencies are missing. Activate '.venv' and run 'pip install -r config/requirements.txt'. Details: $details"
    }
}
finally {
    if ($null -ne $checkProcess) { $checkProcess.Dispose() }
    Remove-Item -LiteralPath $checkScriptPath, $checkOutPath, $checkErrPath -Force -ErrorAction SilentlyContinue
}

$logDir = Join-Path $repoRoot "runtime/logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "local-tts-service.log"
$errLog = Join-Path $logDir "local-tts-service.err.log"

if ($WaitForHealth) {
    $Background = $true
}

if ($Background) {
    $previousPythonPath = $env:PYTHONPATH
    $previousConfigPath = $env:LOCAL_TTS_CONFIG_PATH
    $previousManagedRepo = $env:LOCAL_TTS_MANAGED_REPO
    $previousManagedService = $env:LOCAL_TTS_MANAGED_SERVICE
    try {
        $env:PYTHONPATH = $srcPath
        $env:LOCAL_TTS_CONFIG_PATH = $resolvedConfig
        $env:LOCAL_TTS_MANAGED_REPO = [string]$repoRoot
        $env:LOCAL_TTS_MANAGED_SERVICE = 'local-tts-service'
        if ($VisibleWindow) {
            $proc = Start-Process -FilePath $python -ArgumentList @('-m', 'local_tts_service.server') -WorkingDirectory $repoRoot -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Normal -PassThru
        }
        else {
            $proc = Start-LocalTtsNoWindowProcess -FilePath $python -ArgumentList @('-m', 'local_tts_service.server') -WorkingDirectory $repoRoot -StandardOutputPath $outLog -StandardErrorPath $errLog -RepoRoot $repoRoot
        }
    }
    finally {
        $env:PYTHONPATH = $previousPythonPath
        $env:LOCAL_TTS_CONFIG_PATH = $previousConfigPath
        $env:LOCAL_TTS_MANAGED_REPO = $previousManagedRepo
        $env:LOCAL_TTS_MANAGED_SERVICE = $previousManagedService
    }
    $null = Register-ManagedProcess -RepoRoot $repoRoot -Service 'local-tts-service' -Process $proc -ExpectedCommandFragments @('local_tts_service.server', [string]$repoRoot) -HealthUrl $healthUrl -Port $port
    Write-Host "[INFO] local-tts-service started pid=$($proc.Id)"
    Write-Host "[INFO] health=$healthUrl"
    Write-Host "[INFO] config=$resolvedConfig"
    Write-Host "[INFO] logs=$outLog / $errLog"

    if ($WaitForHealth) {
        $deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
        while ((Get-Date) -lt $deadline) {
            if (Test-Health -Url $healthUrl) {
                Write-Host "[DONE] local-tts-service healthy"
                exit 0
            }
            Start-Sleep -Milliseconds ([Math]::Max(200, [int]($PollIntervalSec * 1000)))
        }
        throw "local-tts-service health check timed out: $healthUrl"
    }

    exit 0
}

$env:LOCAL_TTS_CONFIG_PATH = $resolvedConfig
Write-Host "[INFO] foreground start: local-tts-service"
Write-Host "[INFO] health=$healthUrl"
Write-Host "[INFO] config=$resolvedConfig"
Write-Host "[INFO] stdout/stderr are tee'd to $outLog"
& $python -m local_tts_service.server 2>&1 | Tee-Object -FilePath $outLog -Append
