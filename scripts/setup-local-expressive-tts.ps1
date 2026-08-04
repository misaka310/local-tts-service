param(
  [ValidateSet('all', 'chatterbox', 'cosyvoice')]
  [string[]]$Model = @('all'),
  [string]$PythonExecutable = '',
  [switch]$Background
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'no-window-process.ps1')
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$SetupScript = Join-Path $PSScriptRoot 'setup_local_expressive_tts.py'
if (-not (Test-Path -LiteralPath $SetupScript -PathType Leaf)) {
  throw "setup script not found: $SetupScript"
}

$PythonPath = [string]$PythonExecutable
if (-not $PythonPath -and $env:LOCALAPPDATA) {
  $PythonPath = Join-Path $env:LOCALAPPDATA 'Programs/Python/Python311/python.exe'
}
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
  $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
  $PythonPath = if ($PythonCommand) { [string]$PythonCommand.Source } else { '' }
}
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
  throw 'Python 3.11 is required. Pass -PythonExecutable with the full python.exe path.'
}

$Targets = if ($Model -contains 'all') { @('chatterbox', 'cosyvoice') } else { @($Model) }
$LogDir = Join-Path $RepoRoot 'runtime/logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPath = Join-Path $LogDir 'setup-local-expressive-tts.log'
$ErrorLogPath = Join-Path $LogDir 'setup-local-expressive-tts.err.log'
$Arguments = @('-X', 'utf8', $SetupScript) + $Targets

if ($Background) {
  $Process = Start-LocalTtsNoWindowProcess -FilePath $PythonPath -ArgumentList $Arguments -WorkingDirectory $RepoRoot -StandardOutputPath $LogPath -StandardErrorPath $ErrorLogPath -RepoRoot $RepoRoot
  Write-Host "[INFO] local expressive TTS setup started. pid=$($Process.Id)"
  Write-Host "[INFO] log=$LogPath"
  Write-Host "[INFO] errorLog=$ErrorLogPath"
  exit 0
}

$Process = Start-LocalTtsNoWindowProcess -FilePath $PythonPath -ArgumentList $Arguments -WorkingDirectory $RepoRoot -StandardOutputPath $LogPath -StandardErrorPath $ErrorLogPath -RepoRoot $RepoRoot
$Process.WaitForExit()
$Stdout = if (Test-Path -LiteralPath $LogPath) { Get-Content -LiteralPath $LogPath -Raw -Encoding UTF8 } else { '' }
$Stderr = if (Test-Path -LiteralPath $ErrorLogPath) { Get-Content -LiteralPath $ErrorLogPath -Raw -Encoding UTF8 } else { '' }
if ($Stdout) { Write-Output $Stdout.TrimEnd() }
if ($Process.ExitCode -ne 0) {
  $Details = if ($Stderr.Trim()) { $Stderr.Trim() } elseif ($Stdout.Trim()) { $Stdout.Trim() } else { "exit code $($Process.ExitCode)" }
  throw "local expressive TTS setup failed: $Details"
}
Write-Host '[DONE] local expressive TTS model setup completed.'
