$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
. (Join-Path $PSScriptRoot 'console-control.ps1')

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('local-tts-console-control-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$readyPath = Join-Path $tempRoot 'ready.txt'
$receivedPath = Join-Path $tempRoot 'received.txt'
$errorPath = Join-Path $tempRoot 'sender.err.log'
$targetPath = Join-Path $tempRoot 'hidden-console-target.exe'
$target = $null
$terminalBefore = @(Get-Process -Name WindowsTerminal -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)

$targetSource = @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

internal static class HiddenConsoleTarget
{
    private delegate bool ConsoleCtrlHandler(uint ctrlType);
    private static readonly ManualResetEvent Received = new ManualResetEvent(false);
    private static readonly ConsoleCtrlHandler Handler = OnConsoleControl;

    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool AllocConsole();
    [DllImport("kernel32.dll")] private static extern IntPtr GetConsoleWindow();
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool SetConsoleCtrlHandler(ConsoleCtrlHandler handler, bool add);
    [DllImport("user32.dll")] private static extern bool ShowWindow(IntPtr window, int command);

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length != 2) return 2;
        if (!AllocConsole()) return 3;
        var consoleWindow = GetConsoleWindow();
        if (consoleWindow != IntPtr.Zero) ShowWindow(consoleWindow, 0);
        if (!SetConsoleCtrlHandler(Handler, true)) return 4;
        File.WriteAllText(args[0], "ready", new UTF8Encoding(false));
        if (!Received.WaitOne(TimeSpan.FromSeconds(20))) return 5;
        File.WriteAllText(args[1], "received", new UTF8Encoding(false));
        return 0;
    }

    private static bool OnConsoleControl(uint ctrlType)
    {
        if (ctrlType != 0) return false;
        Received.Set();
        return true;
    }
}
'@

try {
    Add-Type -TypeDefinition $targetSource -Language CSharp -OutputAssembly $targetPath -OutputType WindowsApplication -ErrorAction Stop
    $targetArguments = @(
        (ConvertTo-LocalTtsWindowsArgument -Value $readyPath),
        (ConvertTo-LocalTtsWindowsArgument -Value $receivedPath)
    ) -join ' '
    $target = Start-Process -FilePath $targetPath -ArgumentList $targetArguments -WindowStyle Hidden -PassThru

    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while ([DateTime]::UtcNow -lt $deadline -and -not (Test-Path -LiteralPath $readyPath)) {
        if ($target.HasExited) { throw "hidden console target exited before becoming ready: $($target.ExitCode)" }
        Start-Sleep -Milliseconds 100
    }
    Assert-True (Test-Path -LiteralPath $readyPath) 'hidden console target did not become ready'
    $target.Refresh()
    Assert-True ($target.MainWindowHandle -eq [IntPtr]::Zero) 'hidden console target must not expose a visible window'

    Send-LocalTtsConsoleCtrlC -TargetProcessId $target.Id -TimeoutMs 5000 -ErrorLogPath $errorPath -RepoRoot $repoRoot
    Assert-True ($target.WaitForExit(10000)) 'hidden console target did not exit after Ctrl+C'
    Assert-True ($target.ExitCode -eq 0) "hidden console target returned an unexpected exit code: $($target.ExitCode)"
    Assert-True (Test-Path -LiteralPath $receivedPath) 'hidden console target did not record Ctrl+C receipt'

    $terminalAfter = @(Get-Process -Name WindowsTerminal -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    $newTerminal = @($terminalAfter | Where-Object { $_ -notin $terminalBefore })
    Assert-True ($newTerminal.Count -eq 0) "console-control test must not create Windows Terminal: $($newTerminal -join ', ')"
    Write-Host '[OK] no-window console Ctrl+C sender tests passed'
}
finally {
    if ($null -ne $target -and -not $target.HasExited) {
        Stop-Process -Id $target.Id -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $target) { $target.Dispose() }
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
