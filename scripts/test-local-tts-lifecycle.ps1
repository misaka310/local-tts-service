[CmdletBinding()]
param(
    [ValidateSet('CtrlC', 'CloseWindow')][string]$Mode = 'CtrlC',
    [int]$StartupTimeoutSec = 240,
    [int]$PidTimeoutSec = 30,
    [int]$PortTimeoutSec = 30,
    [string]$RunId = '',
    [int]$SendCtrlCToLauncherPid = 0
)

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
if ([string]::IsNullOrWhiteSpace($RunId)) { $RunId = [guid]::NewGuid().ToString('N') }
$windowTitle = "LocalTtsLifecycle-$RunId"
$backendPort = 8730
$frontendPort = 5177
$configPath = Join-Path $repoRoot 'config/config.local.json'
if (Test-Path -LiteralPath $configPath -PathType Leaf) {
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -ne $config.PSObject.Properties['port']) { $backendPort = [int]$config.port }
    if ($null -ne $config.frontend -and $null -ne $config.frontend.PSObject.Properties['port']) { $frontendPort = [int]$config.frontend.port }
}
$backendHealth = "http://127.0.0.1:$backendPort/health"
$frontendHealth = "http://127.0.0.1:$frontendPort/api/health"
$logDir = Join-Path $repoRoot 'runtime/logs'
$processDir = Join-Path $repoRoot 'runtime/processes'
$stageLog = Join-Path $logDir "lifecycle-test-$RunId.stage.log"
$startedAtUtc = [DateTime]::UtcNow
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not ('LocalTtsLifecycleUiNative' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

public static class LocalTtsLifecycleUiNative
{
    public delegate bool EnumWindowsProc(IntPtr window, IntPtr lParam);
    private const uint WM_SYSCOMMAND = 0x0112;
    private const uint SC_CLOSE = 0xF060;
    private const uint SMTO_ABORTIFHUNG = 0x2;

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr window, StringBuilder text, int maxCount);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr window, StringBuilder text, int maxCount);
    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SendMessageTimeout(IntPtr window, uint message, IntPtr wParam, IntPtr lParam, uint flags, uint timeoutMs, out IntPtr result);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AttachConsole(uint processId);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool FreeConsole();
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GenerateConsoleCtrlEvent(uint ctrlEvent, uint processGroupId);

    public static IntPtr FindVisibleWindowByExactTitle(string expectedTitle)
    {
        IntPtr found = IntPtr.Zero;
        EnumWindows(delegate(IntPtr window, IntPtr lParam) {
            if (!IsWindowVisible(window)) return true;
            StringBuilder title = new StringBuilder(2048);
            GetWindowText(window, title, title.Capacity);
            if (!String.Equals(title.ToString(), expectedTitle, StringComparison.Ordinal)) return true;
            StringBuilder className = new StringBuilder(256);
            GetClassName(window, className, className.Capacity);
            if (String.Equals(className.ToString(), "ConsoleWindowClass", StringComparison.Ordinal)) {
                found = window;
                return false;
            }
            return true;
        }, IntPtr.Zero);
        return found;
    }

    public static void SendConsoleCtrlC(int launcherProcessId)
    {
        FreeConsole();
        if (!AttachConsole((uint)launcherProcessId)) throw new Win32Exception(Marshal.GetLastWin32Error());
        try
        {
            SetConsoleCtrlHandler(IntPtr.Zero, true);
            if (!GenerateConsoleCtrlEvent(0, 0)) throw new Win32Exception(Marshal.GetLastWin32Error());
            Thread.Sleep(300);
        }
        finally
        {
            FreeConsole();
        }
    }

    public static void CloseWindow(string title)
    {
        IntPtr window = FindVisibleWindowByExactTitle(title);
        if (window == IntPtr.Zero) throw new InvalidOperationException("terminal window not found: " + title);
        IntPtr result;
        IntPtr status = SendMessageTimeout(window, WM_SYSCOMMAND, new IntPtr(SC_CLOSE), IntPtr.Zero, SMTO_ABORTIFHUNG, 5000, out result);
        if (status == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
    }
}
'@
}

if ($SendCtrlCToLauncherPid -gt 0) {
    [LocalTtsLifecycleUiNative]::SendConsoleCtrlC($SendCtrlCToLauncherPid)
    exit 0
}

function Write-TestStage {
    param([Parameter(Mandatory = $true)][string]$Message)
    $line = "{0} pid={1} mode={2} {3}" -f [DateTime]::UtcNow.ToString('o'), $PID, $Mode, $Message
    Add-Content -LiteralPath $stageLog -Value $line -Encoding UTF8
    Write-Host $line
}

function Test-PortOpen {
    param([Parameter(Mandatory = $true)][int]$Port)
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Test-Url {
    param([Parameter(Mandatory = $true)][string]$Url)
    Add-Type -AssemblyName System.Net.Http
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(2)
    try {
        $response = $client.GetAsync($Url).GetAwaiter().GetResult()
        try { return $response.IsSuccessStatusCode }
        finally { $response.Dispose() }
    }
    catch { return $false }
    finally {
        $client.Dispose()
        $handler.Dispose()
    }
}

function Wait-Condition {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Condition,
        [Parameter(Mandatory = $true)][int]$TimeoutSec,
        [Parameter(Mandatory = $true)][string]$Failure
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSec)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (& $Condition) { return }
        Start-Sleep -Milliseconds 250
    }
    throw $Failure
}

function Get-CurrentLifecycleState {
    $files = @(Get-ChildItem -LiteralPath $logDir -Filter 'launcher-*.json' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTimeUtc -ge $startedAtUtc.AddSeconds(-2) } |
        Sort-Object LastWriteTimeUtc -Descending)
    foreach ($file in $files) {
        try {
            $state = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([int]$state.launcherPid -gt 0) {
                return [PSCustomObject]@{ Path = $file.FullName; State = $state }
            }
        }
        catch { }
    }
    return $null
}

function Get-SessionRecords {
    param([Parameter(Mandatory = $true)][string]$SessionId)
    if (-not (Test-Path -LiteralPath $processDir -PathType Container)) { return @() }
    return @(Get-ChildItem -LiteralPath $processDir -Filter '*.json' -File -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $record = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([string]$record.sessionId -eq $SessionId) { $record }
        }
        catch { }
    })
}

function Write-FailureDiagnostics {
    param(
        [string]$Stage,
        [int]$LauncherPid,
        [int[]]$ManagedPids,
        [int[]]$ListenerPids,
        [string]$LifecycleStatePath,
        [string]$EventSent
    )
    Write-Host "FAIL stage=$Stage eventSent=$EventSent forcedCleanup=False"
    if ($LifecycleStatePath -and (Test-Path -LiteralPath $LifecycleStatePath)) {
        Write-Host '--- launcher lifecycle state ---'
        Get-Content -LiteralPath $LifecycleStatePath
    }
    Write-Host '--- owned process state ---'
    $ids = @($LauncherPid) + @($ManagedPids) + @($ListenerPids) | Where-Object { $_ -gt 0 } | Select-Object -Unique
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessId -in $ids } |
        Select-Object ProcessId, ParentProcessId, Name, CreationDate, CommandLine |
        Format-List
    Write-Host '--- LISTEN owners ---'
    Get-NetTCPConnection -State Listen -LocalPort @($backendPort, $frontendPort) -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess |
        Format-Table
    Write-Host '--- recent logs ---'
    foreach ($name in @('local-tts-service.log', 'local-tts-service.err.log', 'tts-frontend.out.log', 'tts-frontend.err.log')) {
        $path = Join-Path $logDir $name
        if (Test-Path -LiteralPath $path) {
            Write-Host "--- $name (updated=$((Get-Item -LiteralPath $path).LastWriteTime.ToString('o'))) ---"
            Get-Content -LiteralPath $path -Tail 20
        }
    }
}

if ((Test-PortOpen $backendPort) -or (Test-PortOpen $frontendPort)) {
    throw "lifecycle test requires free ports: $backendPort, $frontendPort"
}
if ([LocalTtsLifecycleUiNative]::FindVisibleWindowByExactTitle($windowTitle) -ne [IntPtr]::Zero) {
    throw "lifecycle test window already exists: $windowTitle"
}

$stage = 'bootstrap'
$launcherPid = 0
$managedPids = @()
$listenerPids = @()
$sessionId = ''
$lifecycleStatePath = ''
$eventSent = 'none'
$testPassed = $false
$forcedCleanup = $false
$failure = $null

try {
    $bat = Join-Path $repoRoot 'local-tts.bat'
    $cmd = Join-Path $env:SystemRoot 'System32/cmd.exe'
    $previousTitle = $env:LOCAL_TTS_WINDOW_TITLE
    $bootstrapTimer = [Diagnostics.Stopwatch]::StartNew()
    try {
        $env:LOCAL_TTS_WINDOW_TITLE = $windowTitle
        $global:LASTEXITCODE = 0
        & $cmd /d /c "call `"$bat`""
        if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "local-tts.bat bootstrap failed with exit code $LASTEXITCODE" }
    }
    finally {
        if ($null -eq $previousTitle) { Remove-Item Env:LOCAL_TTS_WINDOW_TITLE -ErrorAction SilentlyContinue }
        else { $env:LOCAL_TTS_WINDOW_TITLE = $previousTitle }
        $bootstrapTimer.Stop()
    }
    if ($bootstrapTimer.Elapsed.TotalSeconds -gt 15) {
        throw "local-tts.bat bootstrap did not return promptly ($([Math]::Round($bootstrapTimer.Elapsed.TotalSeconds, 1))s)"
    }
    Write-TestStage "bootstrap-returned durationSec=$([Math]::Round($bootstrapTimer.Elapsed.TotalSeconds, 1)) windowTitle=$windowTitle"

    $stage = 'terminal-window'
    Wait-Condition -TimeoutSec 30 -Failure 'dedicated terminal window did not appear' -Condition {
        [LocalTtsLifecycleUiNative]::FindVisibleWindowByExactTitle($windowTitle) -ne [IntPtr]::Zero
    }
    Write-TestStage 'terminal-window-open'

    $stage = 'startup-listen'
    Wait-Condition -TimeoutSec $StartupTimeoutSec -Failure 'startup/listen timeout' -Condition {
        (Test-PortOpen $backendPort) -and (Test-PortOpen $frontendPort)
    }
    Write-TestStage 'listeners-open'

    $stage = 'health'
    Wait-Condition -TimeoutSec 30 -Failure 'health timeout' -Condition {
        (Test-Url $backendHealth) -and (Test-Url $frontendHealth)
    }
    Write-TestStage 'health-ok'

    $stage = 'lifecycle-records'
    $current = $null
    Wait-Condition -TimeoutSec 20 -Failure 'launcher lifecycle state was not created' -Condition {
        $script:current = Get-CurrentLifecycleState
        $null -ne $script:current
    }
    $lifecycleStatePath = $current.Path
    $sessionId = [string]$current.State.sessionId
    $launcherPid = [int]$current.State.launcherPid
    if ([string]::IsNullOrWhiteSpace($sessionId)) { throw 'launcher lifecycle state has no session ID' }
    if (-not (Get-Process -Id $launcherPid -ErrorAction SilentlyContinue)) { throw 'launcher process is not alive after startup' }

    $records = @()
    Wait-Condition -TimeoutSec 20 -Failure 'backend/frontend session records were not created' -Condition {
        $script:records = @(Get-SessionRecords -SessionId $sessionId)
        @($script:records).Count -ge 2
    }
    $managedPids = @($records | ForEach-Object { [int]$_.pid } | Where-Object { $_ -gt 0 } | Select-Object -Unique)
    if ($managedPids.Count -lt 2) { throw 'backend/frontend session records did not contain two managed PIDs' }
    $listenerPids = @(Get-NetTCPConnection -State Listen -LocalPort @($backendPort, $frontendPort) -ErrorAction Stop |
        Select-Object -ExpandProperty OwningProcess -Unique)
    Write-Host "PASS $Mode startup, health, dedicated terminal persistence, and session ownership"
    Write-TestStage "records-ok session=$sessionId launcherPid=$launcherPid managedPids=$($managedPids -join ',') listenerPids=$($listenerPids -join ',')"

    $stage = 'send-exit-event'
    if ($Mode -eq 'CtrlC') {
        $senderArgs = @(
            '-NoProfile',
            '-ExecutionPolicy', 'Bypass',
            '-File', $PSCommandPath,
            '-SendCtrlCToLauncherPid', [string]$launcherPid
        )
        $sender = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe') -ArgumentList $senderArgs -WindowStyle Hidden -PassThru
        if (-not $sender.WaitForExit(10000)) {
            $sender.Kill()
            throw 'Ctrl+C sender timeout'
        }
        if ($sender.ExitCode -ne 0) { throw "Ctrl+C sender failed with exit code $($sender.ExitCode)" }
    }
    else {
        [LocalTtsLifecycleUiNative]::CloseWindow($windowTitle)
    }
    $eventSent = $Mode
    Write-TestStage "terminal-event-sent event=$eventSent"

    $stage = 'managed-pid-exit'
    Wait-Condition -TimeoutSec $PidTimeoutSec -Failure 'managed PID exit timeout' -Condition {
        @($managedPids | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue }).Count -eq 0
    }
    Wait-Condition -TimeoutSec $PidTimeoutSec -Failure 'listener owner PID exit timeout' -Condition {
        @($listenerPids | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue }).Count -eq 0
    }
    Write-TestStage 'managed-and-listener-pids-gone'

    $stage = 'launcher-exit'
    Wait-Condition -TimeoutSec $PidTimeoutSec -Failure 'launcher exit timeout' -Condition {
        -not (Get-Process -Id $launcherPid -ErrorAction SilentlyContinue)
    }
    Write-TestStage 'launcher-gone'

    $stage = 'terminal-window-exit'
    Wait-Condition -TimeoutSec $PidTimeoutSec -Failure 'terminal window exit timeout' -Condition {
        [LocalTtsLifecycleUiNative]::FindVisibleWindowByExactTitle($windowTitle) -eq [IntPtr]::Zero
    }
    Write-TestStage 'terminal-window-gone'

    $stage = 'port-release'
    Wait-Condition -TimeoutSec $PortTimeoutSec -Failure 'port release timeout' -Condition {
        -not (Test-PortOpen $backendPort) -and -not (Test-PortOpen $frontendPort)
    }
    Write-TestStage 'ports-free'

    $stage = 'lifecycle-state'
    $finalState = Get-Content -LiteralPath $lifecycleStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Mode -eq 'CtrlC') {
        if (-not [bool]$finalState.jobClosed -or -not [bool]$finalState.cleanupExecuted -or [string]$finalState.lastEvent -ne 'CtrlC' -or [string]$finalState.stage -ne 'stopped') {
            throw "Ctrl+C lifecycle state mismatch (event=$($finalState.lastEvent), stage=$($finalState.stage), jobClosed=$($finalState.jobClosed), cleanup=$($finalState.cleanupExecuted))"
        }
        $shutdownEvidence = 'graceful Ctrl+C cleanup; jobClosed=true'
    }
    else {
        $gracefulClose = [bool]$finalState.jobClosed -and [bool]$finalState.cleanupExecuted -and [string]$finalState.lastEvent -eq 'ConsoleClose'
        $ownerExitClose = [bool]$finalState.jobCreated -and -not (Get-Process -Id $launcherPid -ErrorAction SilentlyContinue)
        if (-not $gracefulClose -and -not $ownerExitClose) {
            throw "window-close lifecycle evidence mismatch (event=$($finalState.lastEvent), stage=$($finalState.stage), jobCreated=$($finalState.jobCreated), jobClosed=$($finalState.jobClosed), cleanup=$($finalState.cleanupExecuted))"
        }
        $shutdownEvidence = if ($gracefulClose) { 'graceful ConsoleClose cleanup' } else { 'terminal owner exited; kill-on-job-close fallback completed' }
    }

    $testPassed = $true
    $stage = 'passed'
    Write-Host "PASS $Mode launcher/backend/frontend exited; ports $backendPort/$frontendPort released; $shutdownEvidence"
}
catch {
    $failure = $_
}
finally {
    if (-not $testPassed) {
        Write-FailureDiagnostics -Stage $stage -LauncherPid $launcherPid -ManagedPids $managedPids -ListenerPids $listenerPids -LifecycleStatePath $lifecycleStatePath -EventSent $eventSent

        if ($launcherPid -gt 0 -and (Get-Process -Id $launcherPid -ErrorAction SilentlyContinue)) {
            Stop-Process -Id $launcherPid -Force -ErrorAction SilentlyContinue
            $forcedCleanup = $true
        }
        if ($sessionId) {
            try {
                . (Join-Path $PSScriptRoot 'managed-processes.ps1')
                $result = Stop-ManagedProcesses -RepoRoot $repoRoot -SessionId $sessionId
                if (($result.Stopped + $result.Stale) -gt 0) { $forcedCleanup = $true }
            }
            catch { }
        }
        foreach ($processId in @($managedPids + $listenerPids | Where-Object { $_ -gt 0 } | Select-Object -Unique)) {
            if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
                Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                $forcedCleanup = $true
            }
        }
        if ([LocalTtsLifecycleUiNative]::FindVisibleWindowByExactTitle($windowTitle) -ne [IntPtr]::Zero) {
            try { [LocalTtsLifecycleUiNative]::CloseWindow($windowTitle) } catch { }
        }
        if ($forcedCleanup) { Write-TestStage 'forced-cleanup-executed result=FAIL' }
    }
}

if (-not $testPassed) {
    Write-Host "FAIL $Mode stage=$stage error=$($failure.Exception.Message) eventSent=$eventSent forcedCleanup=$forcedCleanup"
    exit 1
}
Write-Host "PASS $Mode forcedCleanup=false"
exit 0
