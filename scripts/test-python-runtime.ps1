$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
. (Join-Path $PSScriptRoot 'python-runtime.ps1')

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('local-tts-python-runtime-test-' + [guid]::NewGuid().ToString('N'))
$originalPath = $env:PATH
$originalExplicitPython = $env:LOCAL_TTS_PYTHON
try {
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null

    $currentPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (-not (Test-LocalTtsPython311 -PythonPath $currentPython)) {
        $pythonCommand = Get-Command 'python.exe' -ErrorAction SilentlyContinue
        if ($pythonCommand) {
            $currentPython = $pythonCommand.Source
        }
    }
    Assert-True (Test-LocalTtsPython311 -PythonPath $currentPython) 'the repository test environment must provide Python 3.11 through .venv or PATH'

    $windowsAppsDir = Join-Path $tempRoot 'Microsoft\WindowsApps'
    New-Item -ItemType Directory -Force -Path $windowsAppsDir | Out-Null
    $aliasPath = Join-Path $windowsAppsDir 'python.exe'
    Set-Content -LiteralPath $aliasPath -Value '' -Encoding ASCII
    Assert-True (-not (Test-LocalTtsPython311 -PythonPath $aliasPath)) 'WindowsApps python alias must not be accepted as a real interpreter'

    $env:LOCAL_TTS_PYTHON = $aliasPath
    $explicitAliasRejected = $false
    try {
        $null = Resolve-LocalTtsPythonRuntime -RepoRoot $tempRoot
    }
    catch {
        $explicitAliasRejected = $_.Exception.Message -match 'not a usable Python 3\.11'
    }
    Assert-True $explicitAliasRejected 'invalid LOCAL_TTS_PYTHON must fail clearly'
    Remove-Item Env:LOCAL_TTS_PYTHON -ErrorAction SilentlyContinue

    $resolved = Resolve-LocalTtsPythonRuntime -RepoRoot $RepoRoot -RequestedPython $currentPython
    Assert-True ($resolved.PythonPath -eq $currentPython) 'an explicit usable Python 3.11 path must be accepted'

    $fakeRepo = Join-Path $tempRoot 'repo'
    New-Item -ItemType Directory -Force -Path $fakeRepo | Out-Null
    $env:PATH = $windowsAppsDir
    $dryRun = Install-LocalTtsManagedPythonRuntime -RepoRoot $fakeRepo -RequestedPython 'python' -DryRun
    Assert-True ($dryRun.Source -eq 'managed') 'WindowsApps-only environment must fall back to repo-managed Python'
    Assert-True ($dryRun.PythonPath -eq (Join-Path $fakeRepo 'runtime\tools\python311\python.exe')) 'managed Python path is incorrect'

    $dryRunWithSystemPython = Install-LocalTtsManagedPythonRuntime -RepoRoot $fakeRepo -RequestedPython $currentPython -DryRun
    Assert-True ($dryRunWithSystemPython.Source -eq 'managed') 'normal setup must not reuse a requested system Python'

    Write-Host '[OK] python runtime tests passed'
}
finally {
    $env:PATH = $originalPath
    if ($null -eq $originalExplicitPython) {
        Remove-Item Env:LOCAL_TTS_PYTHON -ErrorAction SilentlyContinue
    } else {
        $env:LOCAL_TTS_PYTHON = $originalExplicitPython
    }
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
