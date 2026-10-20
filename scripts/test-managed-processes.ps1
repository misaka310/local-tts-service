$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$helperPath = Join-Path $PSScriptRoot 'managed-processes.ps1'
if (-not (Test-Path -LiteralPath $helperPath -PathType Leaf)) {
    throw "managed process helper is missing: $helperPath"
}

. $helperPath

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Wait-ProcessExit {
    param([int]$ProcessId, [int]$TimeoutMs = 5000)
    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMs)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return $true }
        Start-Sleep -Milliseconds 100
    }
    return $false
}

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("local-tts-managed-process-test-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$managed = $null
$unrelated = $null

try {
    $managedCommand = "`$env:LOCAL_TTS_MANAGED_SERVICE='managed-test'; `$env:LOCAL_TTS_MANAGED_REPO='$testRoot'; Start-Sleep -Seconds 60"
    $managed = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-Command', $managedCommand) -PassThru -WindowStyle Hidden
    Register-ManagedProcess -RepoRoot $testRoot -Service 'managed-test' -Process $managed -ExpectedCommandFragments @('LOCAL_TTS_MANAGED_SERVICE', 'managed-test', $testRoot)

    $recordPath = Get-ManagedProcessRecordPath -RepoRoot $testRoot -Service 'managed-test'
    Assert-True (Test-Path -LiteralPath $recordPath -PathType Leaf) 'managed process record was not created'

    $result = Stop-ManagedProcesses -RepoRoot $testRoot -Service 'managed-test'
    Assert-True ($result.Stopped -eq 1) "expected one managed process to stop, got $($result.Stopped)"
    Assert-True (Wait-ProcessExit -ProcessId $managed.Id) 'managed process was not stopped'
    Assert-True (-not (Test-Path -LiteralPath $recordPath)) 'managed process record was not removed'

    $unrelated = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-Command', 'Start-Sleep -Seconds 60') -PassThru -WindowStyle Hidden
    $unrelated.Refresh()
    $recordDir = Get-ManagedProcessDirectory -RepoRoot $testRoot
    New-Item -ItemType Directory -Path $recordDir -Force | Out-Null
    $fakeRecordPath = Get-ManagedProcessRecordPath -RepoRoot $testRoot -Service 'unrelated-test'
    [PSCustomObject]@{
        schemaVersion = 1
        service = 'unrelated-test'
        pid = $unrelated.Id
        processStartTimeUtc = $unrelated.StartTime.ToUniversalTime().ToString('o')
        repoRoot = $testRoot
        expectedCommandFragments = @('LOCAL_TTS_MANAGED_SERVICE', 'unrelated-test', $testRoot)
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $fakeRecordPath -Encoding UTF8

    $unrelatedResult = Stop-ManagedProcesses -RepoRoot $testRoot -Service 'unrelated-test'
    Assert-True ($unrelatedResult.Stopped -eq 0) 'unrelated process must not be stopped'
    Assert-True ($unrelatedResult.Skipped -eq 1) 'unrelated process must be reported as skipped'
    Assert-True ($null -ne (Get-Process -Id $unrelated.Id -ErrorAction SilentlyContinue)) 'unrelated process was terminated'

    Write-Host '[OK] managed process tests passed'
}
finally {
    if ($managed -and (Get-Process -Id $managed.Id -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $managed.Id -Force -ErrorAction SilentlyContinue
    }
    if ($unrelated -and (Get-Process -Id $unrelated.Id -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $unrelated.Id -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
