$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$runtimeScript = Join-Path $PSScriptRoot 'git-runtime.ps1'
if (-not (Test-Path -LiteralPath $runtimeScript -PathType Leaf)) {
    throw "git runtime resolver is missing: $runtimeScript"
}

. $runtimeScript

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function New-FakeGitRuntime {
    param([Parameter(Mandatory = $true)][string]$Directory)
    New-Item -ItemType Directory -Path (Join-Path $Directory 'cmd') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $Directory 'mingw64\bin') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $Directory 'cmd\git.exe') -Value 'fake git' -Encoding ASCII
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("local-tts-git-runtime-test-" + [guid]::NewGuid().ToString('N'))
$originalPath = $env:PATH
$originalGitDir = $env:LOCAL_TTS_GIT_DIR

try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    $fakeRepo = Join-Path $tempRoot 'repo'
    New-Item -ItemType Directory -Path $fakeRepo -Force | Out-Null

    $explicitRoot = Join-Path $tempRoot 'explicit-git'
    New-FakeGitRuntime -Directory $explicitRoot
    $env:LOCAL_TTS_GIT_DIR = $explicitRoot
    $env:PATH = ''
    $resolved = Resolve-LocalTtsGitRuntime -RepoRoot $fakeRepo
    Assert-True ($resolved.Source -eq 'environment') 'LOCAL_TTS_GIT_DIR must take precedence'
    Assert-True ($resolved.GitPath -eq (Join-Path $explicitRoot 'cmd\git.exe')) 'explicit git.exe path was not resolved'

    $env:LOCAL_TTS_GIT_DIR = ''
    $managedRoot = Join-Path $fakeRepo 'runtime\tools\mingit'
    New-FakeGitRuntime -Directory $managedRoot
    $resolved = Resolve-LocalTtsGitRuntime -RepoRoot $fakeRepo
    Assert-True ($resolved.Source -eq 'managed') 'repo-managed MinGit must be used when present'
    Assert-True ($resolved.GitPath -eq (Join-Path $managedRoot 'cmd\git.exe')) 'managed git.exe path was not resolved'

    Remove-Item -LiteralPath $managedRoot -Recurse -Force
    $systemRoot = Join-Path $tempRoot 'system-git'
    New-FakeGitRuntime -Directory $systemRoot
    $env:PATH = Join-Path $systemRoot 'cmd'
    $resolved = Resolve-LocalTtsGitRuntime -RepoRoot $fakeRepo
    Assert-True ($resolved.Source -eq 'system') 'PATH Git must be used as the final fallback'
    Assert-True ($resolved.GitRoot -eq $systemRoot) 'system Git root must resolve above the cmd directory'

    $env:PATH = ''
    $failedClearly = $false
    try {
        $null = Resolve-LocalTtsGitRuntime -RepoRoot $fakeRepo
    }
    catch {
        $failedClearly = $_.Exception.Message -match 'local-tts\.bat -ForceSetup'
    }
    Assert-True $failedClearly 'missing Git must explain that local-tts.bat -ForceSetup fixes it'

    $plan = Install-LocalTtsManagedGitRuntime -RepoRoot $fakeRepo -DryRun
    Assert-True ($plan.Source -eq 'managed') 'managed MinGit dry-run must return the managed source'
    Assert-True ($plan.GitPath -eq (Join-Path $managedRoot 'cmd\git.exe')) 'managed MinGit dry-run target is incorrect'

    $env:PATH = 'existing-path'
    Add-LocalTtsGitRuntimeToPath -GitRuntime $plan
    Assert-True ($env:PATH -match [regex]::Escape((Join-Path $managedRoot 'cmd'))) 'managed MinGit cmd directory must be added to PATH'
    Assert-True ($env:PATH -match 'existing-path') 'existing PATH entries must be preserved'
}
finally {
    $env:PATH = $originalPath
    $env:LOCAL_TTS_GIT_DIR = $originalGitDir
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host '[OK] git runtime tests passed'
