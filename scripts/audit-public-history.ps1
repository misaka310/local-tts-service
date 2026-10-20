[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$OutputPath = '',
    [switch]$FailOnFindings,
    [switch]$FailOnWorkingTreeFindings
)

$ErrorActionPreference = 'Stop'

function Resolve-PythonExecutable {
    param([string]$Root)

    $venvPython = Join-Path $Root '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) { return $venvPython }

    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $candidates = @()
    if ($env:LOCALAPPDATA) {
        $candidates += Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'Programs\Python') -Filter python.exe -File -Recurse -ErrorAction SilentlyContinue
    }
    if ($env:ProgramFiles) {
        $candidates += Get-ChildItem -LiteralPath $env:ProgramFiles -Filter python.exe -File -Depth 2 -ErrorAction SilentlyContinue
    }
    $resolved = $candidates | Select-Object -First 1
    if ($resolved) { return $resolved.FullName }
    throw 'Python 3 executable was not found. Run local-tts.bat -ForceSetup first.'
}

function Quote-NativeArgument {
    param([string]$Value)
    return '"' + ($Value -replace '"', '\"') + '"'
}

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = [string](Resolve-Path (Join-Path $PSScriptRoot '..'))
}
else {
    $RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $RepoRoot 'runtime/audits/public-history-audit.json'
}
elseif (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path $RepoRoot $OutputPath
}

$python = Resolve-PythonExecutable -Root $RepoRoot
$arguments = @(
    (Quote-NativeArgument (Join-Path $PSScriptRoot 'audit_public_history.py')),
    '--repo-root', (Quote-NativeArgument $RepoRoot),
    '--output', (Quote-NativeArgument $OutputPath)
)
if ($FailOnFindings) { $arguments += '--fail-on-findings' }
if ($FailOnWorkingTreeFindings) { $arguments += '--fail-on-working-tree-findings' }

$runId = [Guid]::NewGuid().ToString('N')
$stdoutPath = Join-Path ([System.IO.Path]::GetTempPath()) "local-tts-audit-$runId.out.txt"
$stderrPath = Join-Path ([System.IO.Path]::GetTempPath()) "local-tts-audit-$runId.err.txt"
try {
    $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $RepoRoot -Wait -PassThru -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    if (Test-Path -LiteralPath $stdoutPath) {
        Get-Content -LiteralPath $stdoutPath -Encoding UTF8 | Write-Host
    }
    if (Test-Path -LiteralPath $stderrPath) {
        Get-Content -LiteralPath $stderrPath -Encoding UTF8 | Write-Host
    }
    if ($process.ExitCode -ne 0) { exit $process.ExitCode }
}
finally {
    Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
}
