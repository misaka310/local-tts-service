[CmdletBinding()]
param(
    [switch]$NoOpenBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$workerScript = Join-Path $PSScriptRoot 'start-local-tts-companion.ps1'
$sharedRunnerRoot = if ($env:WINDOWS_GUI_CI_RUNNER_ROOT) {
    [IO.Path]::GetFullPath($env:WINDOWS_GUI_CI_RUNNER_ROOT)
} else {
    [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $repoRoot) '74_windows-gui-ci-runner'))
}
$noWindowLauncher = Join-Path $sharedRunnerRoot 'scripts\host\Start-NoWindowDetached.ps1'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$logRoot = Join-Path $repoRoot 'runtime\logs'
$statePath = Join-Path $logRoot 'companion-button-launch-state.json'
$stdoutPath = Join-Path $logRoot 'companion-button-launch.stdout.log'
$stderrPath = Join-Path $logRoot 'companion-button-launch.stderr.log'

function Quote-NativeArgument {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    return '"' + $Value.Replace('"', '\"') + '"'
}

foreach ($requiredPath in @($workerScript, $noWindowLauncher, $powershell)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required launcher component was not found: $requiredPath"
    }
}
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

$arguments = @(
    '-NoLogo',
    '-NoProfile',
    '-NonInteractive',
    '-ExecutionPolicy', 'Bypass',
    '-File', $workerScript
)
if ($NoOpenBrowser) {
    $arguments += '-NoOpenBrowser'
}
$argumentText = ($arguments | ForEach-Object { Quote-NativeArgument ([string]$_) }) -join ' '

& $noWindowLauncher `
    -FilePath $powershell `
    -Arguments $argumentText `
    -WorkingDirectory $repoRoot `
    -StatePath $statePath `
    -StdoutPath $stdoutPath `
    -StderrPath $stderrPath
