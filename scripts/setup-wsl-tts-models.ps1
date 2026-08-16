param(
  [ValidateSet('all', 'asmr', 'sarashina', 'fireredtts2', 't5gemma', 'fish_s1_mini', 'orpheus_asmr', 'ming_omni_tts')]
  [string[]]$Model = @('all'),
  [switch]$Background
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$ScriptPath = Join-Path $PSScriptRoot 'setup_wsl_tts_models.sh'
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { throw 'WSL is not installed.' }
if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) { throw "setup script not found: $ScriptPath" }

function Convert-ToWslPath {
  param([Parameter(Mandatory = $true)][string]$WindowsPath)
  $full = [System.IO.Path]::GetFullPath($WindowsPath)
  $root = [System.IO.Path]::GetPathRoot($full)
  if (-not $root -or $root.Length -lt 2 -or $root[1] -ne ':') { throw "unsupported Windows path for WSL: $full" }
  $drive = $root[0].ToString().ToLowerInvariant()
  $relative = $full.Substring($root.Length).Replace('\', '/')
  return "/mnt/$drive/$relative"
}

$ScriptWsl = Convert-ToWslPath $ScriptPath
$LogDir = Join-Path $RepoRoot 'runtime/logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPath = Join-Path $LogDir 'setup-wsl-tts-models.log'
$ErrorLogPath = Join-Path $LogDir 'setup-wsl-tts-models.err.log'
$Arguments = @('--exec', 'bash', $ScriptWsl) + @($Model)

if ($Background) {
  $Process = Start-Process -FilePath 'wsl.exe' -ArgumentList $Arguments -RedirectStandardOutput $LogPath -RedirectStandardError $ErrorLogPath -WindowStyle Hidden -PassThru
  Write-Host "[INFO] WSL setup started in background. pid=$($Process.Id)"
  Write-Host "[INFO] log=$LogPath"
  Write-Host "[INFO] errorLog=$ErrorLogPath"
  exit 0
}

$Process = Start-Process -FilePath 'wsl.exe' -ArgumentList $Arguments -RedirectStandardOutput $LogPath -RedirectStandardError $ErrorLogPath -WindowStyle Hidden -PassThru -Wait
$Stdout = if (Test-Path -LiteralPath $LogPath) { Get-Content -LiteralPath $LogPath -Raw -Encoding UTF8 } else { '' }
$Stderr = if (Test-Path -LiteralPath $ErrorLogPath) { Get-Content -LiteralPath $ErrorLogPath -Raw -Encoding UTF8 } else { '' }
if ($Stdout) { Write-Output $Stdout.TrimEnd() }
if ($Process.ExitCode -ne 0) {
  $Details = if ($Stderr.Trim()) { $Stderr.Trim() } elseif ($Stdout.Trim()) { $Stdout.Trim() } else { "exit code $($Process.ExitCode)" }
  throw "WSL TTS setup failed: $Details"
}
Write-Host '[DONE] WSL TTS model setup completed.'
