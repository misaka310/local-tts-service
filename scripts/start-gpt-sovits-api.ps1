param(
  [string]$GptSovitsRoot = '',
  [string]$PythonExecutable = '',
  [string]$ConfigPath = '',
  [string]$VisibleGpuDevices,
  [string]$ApiHost = '127.0.0.1',
  [int]$ApiPort = 9880,
  [switch]$NoSetup,
  [switch]$Check,
  [switch]$VisibleWindow,
  [int]$StartupTimeoutSec = 900
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'managed-processes.ps1')
. (Join-Path $PSScriptRoot 'no-window-process.ps1')

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

$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$RuntimeRoot = Get-LocalTtsRuntimeRoot -RepoRoot $RepoRoot
if (-not $GptSovitsRoot) {
  $GptSovitsRoot = if ($env:LOCAL_TTS_GPT_SOVITS_ROOT) {
    $env:LOCAL_TTS_GPT_SOVITS_ROOT
  } else {
    Join-Path $RuntimeRoot 'vendor/GPT-SoVITS-clean'
  }
}
if (-not [System.IO.Path]::IsPathRooted($GptSovitsRoot)) {
  $GptSovitsRoot = Join-Path $RepoRoot $GptSovitsRoot
}
$GptSovitsRoot = [System.IO.Path]::GetFullPath($GptSovitsRoot)

if (-not $PythonExecutable) {
  $PythonExecutable = if ($env:LOCAL_TTS_GPT_SOVITS_PYTHON) {
    $env:LOCAL_TTS_GPT_SOVITS_PYTHON
  } else {
    Join-Path $RuntimeRoot 'venvs/gpt-sovits/Scripts/python.exe'
  }
}
if (-not [System.IO.Path]::IsPathRooted($PythonExecutable)) {
  $PythonExecutable = Join-Path $RepoRoot $PythonExecutable
}
$PythonExecutable = [System.IO.Path]::GetFullPath($PythonExecutable)

if (-not $ConfigPath) {
  $ConfigPath = if ($env:LOCAL_TTS_GPT_SOVITS_CONFIG) {
    $env:LOCAL_TTS_GPT_SOVITS_CONFIG
  } else {
    Join-Path $RuntimeRoot 'gpt-sovits/tts_infer.yaml'
  }
}
if (-not [System.IO.Path]::IsPathRooted($ConfigPath)) {
  $ConfigPath = Join-Path $RepoRoot $ConfigPath
}
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)

if (-not (Test-Path -LiteralPath $GptSovitsRoot -PathType Container)) {
  if ($NoSetup) {
    throw "GPT-SoVITS source checkout not found: $GptSovitsRoot"
  }
  & (Join-Path $PSScriptRoot 'setup-gpt-sovits.ps1') -GptSovitsRoot $GptSovitsRoot
}
if (-not (Test-Path -LiteralPath $GptSovitsRoot -PathType Container)) {
  throw "GPT-SoVITS source checkout not found after setup: $GptSovitsRoot"
}
$ApiScript = Get-ChildItem -LiteralPath $GptSovitsRoot -Recurse -Filter 'api_v2.py' -File | Select-Object -First 1
if (-not $ApiScript) {
  throw "api_v2.py not found under $GptSovitsRoot"
}
if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
  throw "Dedicated GPT-SoVITS Python environment is missing: $PythonExecutable"
}
if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
  throw "External GPT-SoVITS inference config is missing: $ConfigPath"
}

if ($Check) {
  if (-not (Test-PortOpen -HostName $ApiHost -Port $ApiPort)) {
    throw ("GPT-SoVITS API is not reachable at http://{0}:{1}" -f $ApiHost, $ApiPort)
  }
  Write-Output '[DONE] GPT-SoVITS source, external Python, config, and API are ready.'
  exit 0
}

if (Test-PortOpen -HostName $ApiHost -Port $ApiPort) {
  Write-Host ("[INFO] GPT-SoVITS API already running: http://{0}:{1}" -f $ApiHost, $ApiPort)
  exit 0
}

$LogDir = Join-Path $RuntimeRoot 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$OutLog = Join-Path $LogDir 'gpt-sovits-api.out.log'
$ErrLog = Join-Path $LogDir 'gpt-sovits-api.err.log'

$FfmpegVendorRoot = Join-Path $RuntimeRoot 'vendor/ffmpeg'
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
}

$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$env:PYTHONLEGACYWINDOWSSTDIO = '0'
if (-not [string]::IsNullOrWhiteSpace($VisibleGpuDevices)) {
  $env:CUDA_VISIBLE_DEVICES = $VisibleGpuDevices.Trim()
  Write-Host ("[INFO] GPT-SoVITS CUDA_VISIBLE_DEVICES={0}" -f $env:CUDA_VISIBLE_DEVICES)
}
$env:LOCAL_TTS_RUNTIME_ROOT = $RuntimeRoot
$env:HF_HOME = Join-Path $RuntimeRoot 'hf-cache'
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME 'hub'
$env:TORCH_HOME = Join-Path $RuntimeRoot 'cache\torch'
$env:NLTK_DATA = Join-Path $RuntimeRoot 'nltk_data'
$env:TMP = Join-Path $RuntimeRoot 'temp'
$env:TEMP = $env:TMP
$env:XDG_CACHE_HOME = Join-Path $RuntimeRoot 'cache\xdg'
$env:PYTHONDONTWRITEBYTECODE = '1'
New-Item -ItemType Directory -Force -Path $env:HF_HOME, $env:TORCH_HOME, $env:NLTK_DATA, $env:TEMP, $env:XDG_CACHE_HOME | Out-Null

$previousManagedRepo = $env:LOCAL_TTS_MANAGED_REPO
$previousManagedService = $env:LOCAL_TTS_MANAGED_SERVICE
try {
  $env:LOCAL_TTS_MANAGED_REPO = [string]$RepoRoot
  $env:LOCAL_TTS_MANAGED_SERVICE = 'gpt-sovits'
  $apiArguments = @('-X', 'utf8', (Join-Path $RepoRoot 'scripts/gpt_sovits_api_bootstrap.py'), $ApiScript.FullName, '-a', $ApiHost, '-p', [string]$ApiPort, '-c', $ConfigPath)
  if ($VisibleWindow) {
    $proc = Start-Process -FilePath $PythonExecutable -ArgumentList $apiArguments -WorkingDirectory $GptSovitsRoot -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -WindowStyle Normal -PassThru
  }
  else {
    $proc = Start-LocalTtsNoWindowProcess -FilePath $PythonExecutable -ArgumentList $apiArguments -WorkingDirectory $GptSovitsRoot -StandardOutputPath $OutLog -StandardErrorPath $ErrLog -RepoRoot $RepoRoot
  }
}
finally {
  if ($null -eq $previousManagedRepo) { Remove-Item Env:LOCAL_TTS_MANAGED_REPO -ErrorAction SilentlyContinue } else { $env:LOCAL_TTS_MANAGED_REPO = $previousManagedRepo }
  if ($null -eq $previousManagedService) { Remove-Item Env:LOCAL_TTS_MANAGED_SERVICE -ErrorAction SilentlyContinue } else { $env:LOCAL_TTS_MANAGED_SERVICE = $previousManagedService }
}
$null = Register-ManagedProcess -RepoRoot $RepoRoot -Service 'gpt-sovits' -Process $proc -ExpectedCommandFragments @('api_v2.py', [string]$GptSovitsRoot, [string]$ConfigPath) -HealthUrl ("http://{0}:{1}" -f $ApiHost, $ApiPort) -Port $ApiPort
$deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
while ((Get-Date) -lt $deadline) {
  if (Test-PortOpen -HostName $ApiHost -Port $ApiPort) {
    Write-Host ("[DONE] GPT-SoVITS API started: http://{0}:{1} (pid={2})" -f $ApiHost, $ApiPort, $proc.Id)
    Write-Host "[INFO] logs: $OutLog / $ErrLog"
    exit 0
  }
  if ($proc.HasExited) {
    $stderrTail = ''
    if (Test-Path -LiteralPath $ErrLog) {
      $stderrTail = (Get-Content -LiteralPath $ErrLog -Tail 40) -join [Environment]::NewLine
    }
    throw ("GPT-SoVITS API exited before becoming ready. Logs: {0}{1}{2}" -f $ErrLog, [Environment]::NewLine, $stderrTail)
  }
  Start-Sleep -Milliseconds 500
}

throw ("GPT-SoVITS API startup timed out: http://{0}:{1} (logs: {2} / {3})" -f $ApiHost, $ApiPort, $OutLog, $ErrLog)
