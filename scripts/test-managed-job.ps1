$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
. (Join-Path $PSScriptRoot 'managed-job.ps1')

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("local-tts-job-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$managedHostScript = Join-Path $testRoot 'host.ps1'
$childPidPath = Join-Path $testRoot 'child.pid'
$readyName = "LocalTtsJobTest-$PID-$([guid]::NewGuid().ToString('N'))"
$ready = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset, $readyName)
$job = [IntPtr]::Zero
$managedHost = $null

try {
    @'
param([string]$ConfigPath, [string]$ReadyEventName, [switch]$NoGptSovitsStart)
$ready = [Threading.EventWaitHandle]::OpenExisting($ReadyEventName)
$child = Start-Process powershell.exe -ArgumentList '-NoProfile','-Command','Start-Sleep -Seconds 60' -WindowStyle Hidden -PassThru
Set-Content -LiteralPath $ConfigPath -Value $child.Id -Encoding ASCII
$null = $ready.Set()
$wait = New-Object Threading.ManualResetEvent($false)
$null = $wait.WaitOne()
'@ | Set-Content -LiteralPath $managedHostScript -Encoding UTF8

    Write-Host '[TEST] creating job'
    $job = New-LocalTtsManagedJob
    Write-Host '[TEST] starting suspended host'
    $managedHost = Start-LocalTtsManagedStackHost -JobHandle $job -ScriptPath $managedHostScript -ConfigPath $childPidPath -ReadyEventName $readyName -WorkingDirectory $testRoot
    Write-Host '[TEST] waiting for host readiness'
    Assert-True ($ready.WaitOne(10000)) 'managed host did not become ready'
    $childPid = [int](Get-Content -LiteralPath $childPidPath -Raw)
    Assert-True ($null -ne (Get-Process -Id $managedHost.ProcessId -ErrorAction SilentlyContinue)) 'managed host exited early'
    Assert-True ($null -ne (Get-Process -Id $childPid -ErrorAction SilentlyContinue)) 'managed child exited early'

    Write-Host '[TEST] closing job'
    Close-LocalTtsManagedJob -JobHandle $job
    $job = [IntPtr]::Zero
    Assert-True ([LocalTtsJobNative]::WaitForSingleObject($managedHost.ProcessHandle, 5000) -eq [LocalTtsJobNative]::WAIT_OBJECT_0) 'managed host survived job close'
    $deadline = [DateTime]::UtcNow.AddSeconds(5)
    while ([DateTime]::UtcNow -lt $deadline -and (Get-Process -Id $childPid -ErrorAction SilentlyContinue)) { Start-Sleep -Milliseconds 100 }
    Assert-True ($null -eq (Get-Process -Id $childPid -ErrorAction SilentlyContinue)) 'managed child survived job close'
    Write-Host '[OK] managed Job Object tests passed'
}
finally {
    if ($job -ne [IntPtr]::Zero) { Close-LocalTtsManagedJob -JobHandle $job }
    if ($managedHost -and $managedHost.ProcessHandle -ne [IntPtr]::Zero) { $null = [LocalTtsJobNative]::CloseHandle($managedHost.ProcessHandle) }
    $ready.Dispose()
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
