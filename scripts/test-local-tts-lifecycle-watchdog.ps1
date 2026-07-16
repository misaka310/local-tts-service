[CmdletBinding()]
param(
    [ValidateSet('CtrlC', 'CloseWindow')][string]$Mode = 'CtrlC',
    [int]$OverallTimeoutSec = 360,
    [int]$StartupTimeoutSec = 240
)

$ErrorActionPreference = 'Stop'
if (-not ('LocalTtsWatchdogNative' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class LocalTtsWatchdogNative {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool GetExitCodeProcess(IntPtr process, out uint exitCode);
}
'@
}
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$runId = [guid]::NewGuid().ToString('N')
$logDir = Join-Path $repoRoot 'runtime/logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "lifecycle-test-$runId.out.log"
$errLog = Join-Path $logDir "lifecycle-test-$runId.err.log"
$stageLog = Join-Path $logDir "lifecycle-test-$runId.stage.log"
$workerScript = Join-Path $PSScriptRoot 'test-local-tts-lifecycle.ps1'
$workerArgs = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $workerScript,
    '-Mode', $Mode,
    '-StartupTimeoutSec', [string]$StartupTimeoutSec,
    '-RunId', $runId
)

$startedAt = [DateTime]::UtcNow
$worker = Start-Process -FilePath 'powershell.exe' -ArgumentList $workerArgs -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
$workerHandle = $worker.Handle
$completed = $worker.WaitForExit($OverallTimeoutSec * 1000)

if (-not $completed) {
    Write-Host "FAIL $Mode overall-timeout after $($OverallTimeoutSec)s"
    Write-Host "stageLog=$stageLog workerPid=$($worker.Id)"
    if (Test-Path -LiteralPath $stageLog) {
        Write-Host '--- stage log ---'
        Get-Content -LiteralPath $stageLog -Tail 40
    }
    Write-Host '--- current process tree ---'
    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $owned = @($worker.Id)
    for ($i = 0; $i -lt 8; $i++) {
        $children = @($all | Where-Object { $_.ParentProcessId -in $owned } | Select-Object -ExpandProperty ProcessId)
        $owned += $children
    }
    $all | Where-Object { $_.ProcessId -in $owned } | Select-Object ProcessId, ParentProcessId, Name, CreationDate, CommandLine | Format-List
    Write-Host '--- LISTEN owners ---'
    Get-NetTCPConnection -State Listen -LocalPort @(8730, 5177) -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess |
        Format-Table
    Write-Host '--- recent logs ---'
    Get-ChildItem -LiteralPath $logDir -File | Sort-Object LastWriteTime -Descending | Select-Object -First 8 Name, Length, LastWriteTime | Format-Table
    foreach ($name in @('local-tts-service.log', 'local-tts-service.err.log', 'tts-frontend.out.log', 'tts-frontend.err.log')) {
        $path = Join-Path $logDir $name
        if (Test-Path -LiteralPath $path) {
            Write-Host "--- $name ---"
            Get-Content -LiteralPath $path -Tail 30
        }
    }
    Write-Host 'forcedCleanup=true result=FAIL'
    if (Get-Process -Id $worker.Id -ErrorAction SilentlyContinue) {
        $null = Start-Process -FilePath 'taskkill.exe' -ArgumentList @('/PID', [string]$worker.Id, '/T', '/F') -WindowStyle Hidden -PassThru -Wait
    }
    exit 1
}

$worker.WaitForExit()
$nativeExitCode = [uint32]0
if (-not [LocalTtsWatchdogNative]::GetExitCodeProcess($workerHandle, [ref]$nativeExitCode)) {
    throw 'could not read lifecycle worker exit code'
}
$workerExitCode = [int]$nativeExitCode
$duration = [Math]::Round(([DateTime]::UtcNow - $startedAt).TotalSeconds, 1)
if (Test-Path -LiteralPath $outLog) { Get-Content -LiteralPath $outLog }
if (Test-Path -LiteralPath $errLog) {
    $errors = Get-Content -LiteralPath $errLog
    if ($errors) { $errors | Write-Host }
}
if ($workerExitCode -ne 0) {
    Write-Host "FAIL $Mode workerExit=$workerExitCode durationSec=$duration"
    exit $workerExitCode
}

Write-Host "PASS $Mode overall durationSec=$duration forcedCleanup=false"
exit 0
