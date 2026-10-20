[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$Service = '',
    [string]$SessionId = ''
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = [string](Resolve-Path (Join-Path $PSScriptRoot '..'))
}
else {
    $RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
}

. (Join-Path $PSScriptRoot 'managed-processes.ps1')

$result = Stop-ManagedProcesses -RepoRoot $RepoRoot -Service $Service -SessionId $SessionId
Write-Host "[INFO] managed process stop summary: stopped=$($result.Stopped) stale=$($result.Stale) skipped=$($result.Skipped) failed=$($result.Failed)"

if ($result.Failed -gt 0) {
    throw "failed to stop one or more managed processes"
}
