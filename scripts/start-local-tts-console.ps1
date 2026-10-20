$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$conhost = Join-Path $env:SystemRoot 'System32\conhost.exe'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$launchScript = Join-Path $PSScriptRoot 'launch-local-tts.ps1'
$windowTitle = [string]$env:LOCAL_TTS_WINDOW_TITLE
if ([string]::IsNullOrWhiteSpace($windowTitle)) { $windowTitle = 'local-tts-service' }

if (-not (Test-Path -LiteralPath $conhost -PathType Leaf)) { throw "console host not found: $conhost" }
if (-not (Test-Path -LiteralPath $powershell -PathType Leaf)) { throw "Windows PowerShell not found: $powershell" }
if (-not (Test-Path -LiteralPath $launchScript -PathType Leaf)) { throw "launcher not found: $launchScript" }

$arguments = @(
    $powershell,
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $launchScript,
    '-PauseOnFailure',
    '-WindowTitle', $windowTitle
) + @($args)

Start-Process -FilePath $conhost -ArgumentList $arguments -WorkingDirectory $repoRoot | Out-Null
