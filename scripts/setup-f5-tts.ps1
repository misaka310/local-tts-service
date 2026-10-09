param(
  [string]$BasePython = '',
  [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'no-window-process.ps1')
. (Join-Path $PSScriptRoot 'python-runtime.ps1')
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$RuntimeRoot = Get-LocalTtsRuntimeRoot -RepoRoot $RepoRoot
$env:LOCAL_TTS_RUNTIME_ROOT = $RuntimeRoot
$env:HF_HOME = Join-Path $RuntimeRoot 'hf-cache'
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME 'hub'
$env:TORCH_HOME = Join-Path $RuntimeRoot 'cache\torch'
$env:PIP_CACHE_DIR = Join-Path $RuntimeRoot 'cache\pip'
$env:TMP = Join-Path $RuntimeRoot 'temp'
$env:TEMP = $env:TMP
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HUB_DISABLE_TELEMETRY = '1'

$VenvRoot = Join-Path $RuntimeRoot 'venvs\f5-tts'
$Python = Join-Path $VenvRoot 'Scripts\python.exe'
$ModelRoot = Join-Path $RuntimeRoot 'models\f5-tts'
$LogRoot = Join-Path $RuntimeRoot 'logs'
$StdoutLog = Join-Path $LogRoot 'setup-f5-tts.out.log'
$StderrLog = Join-Path $LogRoot 'setup-f5-tts.err.log'
$Downloader = Join-Path $PSScriptRoot 'download_f5_tts_assets.py'
New-Item -ItemType Directory -Force -Path $LogRoot, $ModelRoot, $env:TMP, $env:PIP_CACHE_DIR | Out-Null

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  $BasePythonRuntime = Install-LocalTtsManagedPythonRuntime -RepoRoot $RepoRoot -RequestedPython $BasePython
  & $BasePythonRuntime.PythonPath -m venv $VenvRoot
  if ($LASTEXITCODE -ne 0) { throw "Could not create F5-TTS environment (exit=$LASTEXITCODE)." }
}

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class LocalTtsSetupScheduling {
    [DllImport("kernel32.dll")] public static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool SetPriorityClass(IntPtr process, uint priorityClass);
}
'@
$currentProcess = [LocalTtsSetupScheduling]::GetCurrentProcess()
if (-not [LocalTtsSetupScheduling]::SetPriorityClass($currentProcess, 0x00100000)) {
  throw 'Could not set background CPU and I/O scheduling for F5 setup.'
}

function Invoke-LowPriorityCommand {
  param([string]$Name, [string]$FilePath, [string[]]$Arguments)
  $Process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $RepoRoot -WindowStyle Hidden -RedirectStandardOutput $StdoutLog -RedirectStandardError $StderrLog -PassThru
  try {
    $null = [LocalTtsSetupScheduling]::SetPriorityClass($Process.Handle, 0x00100000)
    $Process.WaitForExit()
    if ($Process.ExitCode -ne 0) {
      $stderr = if (Test-Path -LiteralPath $StderrLog) { (Get-Content -LiteralPath $StderrLog -Tail 40 -Encoding UTF8) -join [Environment]::NewLine } else { '' }
      throw "$Name failed (exit=$($Process.ExitCode)). $stderr"
    }
    Write-Output "[DONE] $Name"
  } finally {
    $Process.Dispose()
  }
}

try {
  if (-not $SkipInstall) {
    Invoke-LowPriorityCommand -Name 'install CUDA 12.8 PyTorch 2.10.0' -FilePath $Python -Arguments @('-m','pip','install','--index-url','https://download.pytorch.org/whl/cu128','torch==2.10.0','torchaudio==2.10.0')
    Invoke-LowPriorityCommand -Name 'install TorchCodec 0.10.0 for PyTorch 2.10' -FilePath $Python -Arguments @('-m','pip','install','torchcodec==0.10.0')
    Invoke-LowPriorityCommand -Name 'install F5-TTS 1.1.20' -FilePath $Python -Arguments @('-m','pip','install','f5-tts==1.1.20')
  }
  Invoke-LowPriorityCommand -Name 'download Japanese F5-TTS model and license/readme' -FilePath $Python -Arguments @($Downloader,'--model-root',$ModelRoot)
  & (Join-Path $PSScriptRoot 'run-f5-tts.ps1') -Check
} finally {
  if (-not [LocalTtsSetupScheduling]::SetPriorityClass($currentProcess, 0x00200000)) {
    throw 'Could not restore normal scheduling after F5 setup.'
  }
}
