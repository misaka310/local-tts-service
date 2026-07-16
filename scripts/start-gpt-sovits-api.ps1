param(
  [string]$GptSovitsRoot = '',
  [string]$PythonExecutable = '',
  [string]$ApiHost = '127.0.0.1',
  [int]$ApiPort = 9880,
  [switch]$NoSetup,
  [switch]$VisibleWindow,
  [int]$StartupTimeoutSec = 60
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'managed-processes.ps1')

function Test-PortOpen {
  param([string]$HostName, [int]$Port)
  try {
    $client = New-Object System.Net.Sockets.TcpClient
    $iar = $client.BeginConnect($HostName, $Port, $null, $null)
    if (-not $iar.AsyncWaitHandle.WaitOne(1500, $false)) {
      $client.Close()
      return $false
    }
    $client.EndConnect($iar)
    $client.Close()
    return $true
  } catch {
    return $false
  }
}

function Resolve-PythonExecutable {
  param([string]$Root, [string]$ExplicitPath)
  $candidates = @()
  if ($ExplicitPath) { $candidates += $ExplicitPath }
  if ($env:LOCAL_TTS_GPT_SOVITS_PYTHON) { $candidates += $env:LOCAL_TTS_GPT_SOVITS_PYTHON }
  $candidates += @(
    (Join-Path $Root '.venv\Scripts\python.exe'),
    (Join-Path $Root 'runtime\python\python.exe'),
    (Join-Path $Root 'python\python.exe'),
    'python'
  )
  foreach ($candidate in $candidates) {
    if ($candidate -eq 'python') { return $candidate }
    if (Test-Path -LiteralPath $candidate) { return $candidate }
  }
  return 'python'
}

function Ensure-GptSovitsEnvironment {
  param([string]$Root, [string]$PythonPath)
  $requirementsPath = Join-Path $Root 'requirements.txt'
  if (-not (Test-Path -LiteralPath $requirementsPath)) {
    return $PythonPath
  }

  $venvPython = Join-Path $Root '.venv\Scripts\python.exe'
  if ($PythonPath -eq 'python' -and -not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "[INFO] creating GPT-SoVITS venv..."
    python -m venv (Join-Path $Root '.venv')
  }
  if (Test-Path -LiteralPath $venvPython) {
    $PythonPath = $venvPython
  }

  $oldPreference = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  & $PythonPath -c "import ffmpeg" *> $null
  $probeExitCode = $LASTEXITCODE
  $ErrorActionPreference = $oldPreference
  if ($probeExitCode -eq 0) {
    return $PythonPath
  }

  Write-Host "[INFO] installing GPT-SoVITS Python dependencies..."
  & $PythonPath -m pip install --upgrade pip
  & $PythonPath -m pip install -r $requirementsPath
  return $PythonPath
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
if (-not $GptSovitsRoot) {
  $GptSovitsRoot = if ($env:LOCAL_TTS_GPT_SOVITS_ROOT) { $env:LOCAL_TTS_GPT_SOVITS_ROOT } else { Join-Path $RepoRoot 'runtime/vendor/GPT-SoVITS' }
}
if (-not (Test-Path -LiteralPath $GptSovitsRoot)) {
  if ($NoSetup) {
    throw "GPT-SoVITS repo not found: $GptSovitsRoot"
  }
  & (Join-Path $PSScriptRoot 'setup-gpt-sovits.ps1')
}
if (-not (Test-Path -LiteralPath $GptSovitsRoot)) {
  throw "GPT-SoVITS repo not found after setup: $GptSovitsRoot"
}

if (Test-PortOpen -HostName $ApiHost -Port $ApiPort) {
  Write-Host "[INFO] GPT-SoVITS API already running: http://$ApiHost`:$ApiPort"
  exit 0
}

$ApiScript = Get-ChildItem -LiteralPath $GptSovitsRoot -Recurse -Filter 'api_v2.py' -File | Select-Object -First 1
if (-not $ApiScript) {
  throw "api_v2.py not found under $GptSovitsRoot"
}

$PythonExecutable = Resolve-PythonExecutable -Root $GptSovitsRoot -ExplicitPath $PythonExecutable
$PythonExecutable = Ensure-GptSovitsEnvironment -Root $GptSovitsRoot -PythonPath $PythonExecutable
$LogDir = Join-Path $RepoRoot 'runtime/logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$OutLog = Join-Path $LogDir 'gpt-sovits-api.out.log'
$ErrLog = Join-Path $LogDir 'gpt-sovits-api.err.log'

$FfmpegVendorRoot = Join-Path $RepoRoot 'runtime/vendor/ffmpeg'
$FfmpegBin = ''
if (Test-Path -LiteralPath $FfmpegVendorRoot) {
  $FfmpegBin = Get-ChildItem -LiteralPath $FfmpegVendorRoot -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName 'bin' } |
    Where-Object { Test-Path -LiteralPath (Join-Path $_ 'ffmpeg.exe') } |
    Select-Object -First 1
}
if ($FfmpegBin) {
  $env:LOCAL_TTS_FFMPEG_BIN = $FfmpegBin
  $env:PATH = "$FfmpegBin;$env:PATH"
  Write-Host "[INFO] using local FFmpeg: $FfmpegBin"
}

$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$env:PYTHONLEGACYWINDOWSSTDIO = '0'

$windowStyle = if ($VisibleWindow) { 'Normal' } else { 'Hidden' }
$pythonLiteral = ConvertTo-PowerShellSingleQuotedLiteral -Value ([string]$PythonExecutable)
$apiScriptLiteral = ConvertTo-PowerShellSingleQuotedLiteral -Value ([string]$ApiScript.FullName)
$command = "& $pythonLiteral -X utf8 $apiScriptLiteral"
$command = Add-ManagedProcessMarker -Command $command -RepoRoot $RepoRoot -Service 'gpt-sovits'
$proc = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $command) -WorkingDirectory $ApiScript.DirectoryName -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -WindowStyle $windowStyle -PassThru
$null = Register-ManagedProcess -RepoRoot $RepoRoot -Service 'gpt-sovits' -Process $proc -ExpectedCommandFragments @('LOCAL_TTS_MANAGED_SERVICE', 'gpt-sovits', [string]$RepoRoot) -HealthUrl "http://$ApiHost`:$ApiPort" -Port $ApiPort

$deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
while ((Get-Date) -lt $deadline) {
  if (Test-PortOpen -HostName $ApiHost -Port $ApiPort) {
    Write-Host "[DONE] GPT-SoVITS API started: http://$ApiHost`:$ApiPort (pid=$($proc.Id))"
    Write-Host "[INFO] logs: $OutLog / $ErrLog"
    exit 0
  }
  if ($proc.HasExited) {
    $stderrTail = ''
    if (Test-Path -LiteralPath $ErrLog) {
      $stderrTail = (Get-Content -LiteralPath $ErrLog -Tail 40) -join [Environment]::NewLine
    }
    throw "GPT-SoVITS API exited before becoming ready. Logs: $ErrLog`n$stderrTail"
  }
  Start-Sleep -Milliseconds 500
}

throw "GPT-SoVITS API startup timed out: http://$ApiHost`:$ApiPort (logs: $OutLog / $ErrLog)"
