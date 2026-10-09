param(
  [ValidateSet('sarashina2_2_tts', 'fireredtts2', 't5gemma_tts_2b_2b', 'fish_s1_mini', 'fish_s2_pro', 'indextts_2_5', 'orpheus_3b_asmr', 'ming_omni_tts_0_5b', 'qwen3_tts_clone_0_6b', 'qwen3_tts_clone_1_7b')]
  [string[]]$Model = @(),
  [string]$VoiceId = '',
  [string]$CudaVisibleDevices = '',
  [string]$Text = '',
  [ValidateSet('cpu', 'cuda')][string]$FishS2SemanticDevice = '',
  [switch]$Background
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$VerifyScript = Join-Path $PSScriptRoot 'verify_wsl_tts_models.py'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Windows service environment not found: $Python" }
if (-not (Test-Path -LiteralPath $VerifyScript -PathType Leaf)) { throw "verification script not found: $VerifyScript" }

$LogDir = Join-Path $RepoRoot 'runtime/logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPath = Join-Path $LogDir 'model-smoke.log'
$ErrorLogPath = Join-Path $LogDir 'model-smoke.err.log'
$Arguments = @($VerifyScript)
if ($Model.Count -gt 0) { $Arguments += @('--models') + @($Model) }
if ($VoiceId.Trim()) { $Arguments += @('--voice-id', $VoiceId.Trim()) }
if ($Text.Trim()) { $Arguments += @('--text', $Text.Trim()) }

$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
if ($CudaVisibleDevices) { $env:LOCAL_TTS_WSL_CUDA_VISIBLE_DEVICES = $CudaVisibleDevices }
if ($FishS2SemanticDevice) { $env:LOCAL_TTS_FISH_S2_SEMANTIC_DEVICE = $FishS2SemanticDevice }

$StartInfo = @{
  FilePath = $Python
  ArgumentList = $Arguments
  WorkingDirectory = $RepoRoot
  RedirectStandardOutput = $LogPath
  RedirectStandardError = $ErrorLogPath
  WindowStyle = 'Hidden'
  PassThru = $true
}

if ($Background) {
  $Process = Start-Process @StartInfo
  Write-Host "[INFO] model smoke verification started in background. pid=$($Process.Id)"
  Write-Host "[INFO] log=$LogPath"
  Write-Host "[INFO] errorLog=$ErrorLogPath"
  exit 0
}

$Process = Start-Process @StartInfo -Wait
[string]$Stdout = if (Test-Path -LiteralPath $LogPath) { Get-Content -LiteralPath $LogPath -Raw -Encoding UTF8 } else { '' }
[string]$Stderr = if (Test-Path -LiteralPath $ErrorLogPath) { Get-Content -LiteralPath $ErrorLogPath -Raw -Encoding UTF8 } else { '' }
if ($Stdout.Trim()) { Write-Output $Stdout.TrimEnd() }
if ($Process.ExitCode -ne 0) {
  $Details = if ($Stderr.Trim()) { $Stderr.Trim() } elseif ($Stdout.Trim()) { $Stdout.Trim() } else { "exit code $($Process.ExitCode)" }
  throw "model smoke verification failed: $Details"
}
Write-Host '[DONE] model smoke verification completed.'
