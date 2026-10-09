$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$runtimeScript = Join-Path $PSScriptRoot 'node-runtime.ps1'
if (-not (Test-Path -LiteralPath $runtimeScript -PathType Leaf)) {
    throw "node runtime resolver is missing: $runtimeScript"
}

. $runtimeScript

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function New-FakeNodePair {
    param([Parameter(Mandatory = $true)][string]$Directory)
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $Directory 'node.exe') -Value 'fake node' -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $Directory 'npm.cmd') -Value '@echo fake npm' -Encoding ASCII
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("local-tts-node-runtime-test-" + [guid]::NewGuid().ToString('N'))
$originalPath = $env:PATH
$originalNodeDir = $env:LOCAL_TTS_NODE_DIR

try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    $fakeRepo = Join-Path $tempRoot 'repo'
    New-Item -ItemType Directory -Path $fakeRepo -Force | Out-Null

    $explicitDir = Join-Path $tempRoot 'explicit-node'
    New-FakeNodePair -Directory $explicitDir
    $env:LOCAL_TTS_NODE_DIR = $explicitDir
    $env:PATH = ''
    $resolved = Resolve-LocalTtsNodeRuntime -RepoRoot $fakeRepo
    Assert-True ($resolved.Source -eq 'environment') 'LOCAL_TTS_NODE_DIR must take precedence'
    Assert-True ($resolved.NodePath -eq (Join-Path $explicitDir 'node.exe')) 'explicit node.exe path was not resolved'
    Assert-True ($resolved.NpmPath -eq (Join-Path $explicitDir 'npm.cmd')) 'explicit npm.cmd path was not resolved'

    $env:LOCAL_TTS_NODE_DIR = ''
    $managedDir = Join-Path $fakeRepo 'runtime/tools/node'
    New-FakeNodePair -Directory $managedDir
    $resolved = Resolve-LocalTtsNodeRuntime -RepoRoot $fakeRepo
    Assert-True ($resolved.Source -eq 'managed') 'repo-managed Node.js must be used when present'
    Assert-True ($resolved.NodePath -eq (Join-Path $managedDir 'node.exe')) 'managed node.exe path was not resolved'

    Remove-Item -LiteralPath $managedDir -Recurse -Force
    $systemDir = Join-Path $tempRoot 'system-node'
    New-FakeNodePair -Directory $systemDir
    $env:PATH = $systemDir
    $resolved = Resolve-LocalTtsNodeRuntime -RepoRoot $fakeRepo
    Assert-True ($resolved.Source -eq 'system') 'PATH Node.js must be used as the final fallback'
    Assert-True ($resolved.NpmPath -eq (Join-Path $systemDir 'npm.cmd')) 'PATH npm.cmd path was not resolved'

    $env:PATH = ''
    $failedClearly = $false
    try {
        $null = Resolve-LocalTtsNodeRuntime -RepoRoot $fakeRepo
    }
    catch {
        $failedClearly = $_.Exception.Message -match 'local-tts\.bat -ForceSetup'
    }
    Assert-True $failedClearly 'missing Node.js/npm must explain that local-tts.bat -ForceSetup fixes it'

    $plan = Install-LocalTtsManagedNodeRuntime -RepoRoot $fakeRepo -DryRun
    Assert-True ($plan.Source -eq 'managed') 'managed Node.js dry-run must return the managed source'
    Assert-True ($plan.NodePath -eq (Join-Path $managedDir 'node.exe')) 'managed Node.js dry-run target is incorrect'
}
finally {
    $env:PATH = $originalPath
    $env:LOCAL_TTS_NODE_DIR = $originalNodeDir
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host '[OK] node runtime tests passed'
