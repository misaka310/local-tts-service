[CmdletBinding()]
param(
    [switch]$NoOpenBrowser,
    [string]$ReferenceVoicesDir = '',
    [ValidateRange(-1, 86400)]
    [int]$IrodoriIdleTimeoutSeconds = -1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$workerScript = Join-Path $PSScriptRoot 'start-local-tts-companion.ps1'
$noWindowProcessScript = Join-Path $PSScriptRoot 'no-window-process.ps1'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$logRoot = Join-Path $repoRoot 'runtime\logs'
$stdoutPath = Join-Path $logRoot 'companion-button-launch.stdout.log'
$stderrPath = Join-Path $logRoot 'companion-button-launch.stderr.log'

foreach ($requiredPath in @($workerScript, $noWindowProcessScript, $powershell)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required launcher component was not found: $requiredPath"
    }
}

. $noWindowProcessScript
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
if (-not [string]::IsNullOrWhiteSpace($ReferenceVoicesDir)) {
    $arguments += @('-ReferenceVoicesDir', [IO.Path]::GetFullPath($ReferenceVoicesDir))
}
if ($IrodoriIdleTimeoutSeconds -ge 0) {
    $arguments += @('-IrodoriIdleTimeoutSeconds', [string]$IrodoriIdleTimeoutSeconds)
}

$process = Start-LocalTtsNoWindowProcess `
    -FilePath $powershell `
    -ArgumentList $arguments `
    -WorkingDirectory $repoRoot `
    -StandardOutputPath $stdoutPath `
    -StandardErrorPath $stderrPath `
    -RepoRoot $repoRoot
try {
    [pscustomobject]@{
        started = $true
        launcherProcessId = [int]$process.Id
        createNoWindow = $true
        launcher = 'repository'
        stdoutPath = $stdoutPath
        stderrPath = $stderrPath
    } | ConvertTo-Json -Compress
}
finally {
    $process.Dispose()
}
