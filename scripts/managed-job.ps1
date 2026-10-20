if (-not ('LocalTtsJobNative' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

public static class LocalTtsJobNative
{
    public const uint CREATE_SUSPENDED = 0x4;
    public const uint CREATE_NEW_PROCESS_GROUP = 0x200;
    public const uint WAIT_OBJECT_0 = 0;
    private const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000;

    [StructLayout(LayoutKind.Sequential)]
    public struct IO_COUNTERS {
        public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
        public ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct BASIC_LIMITS {
        public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct EXTENDED_LIMITS {
        public BASIC_LIMITS BasicLimitInformation;
        public IO_COUNTERS IoInfo;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
    }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct STARTUPINFO {
        public uint cb;
        public string lpReserved, lpDesktop, lpTitle;
        public uint dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
        public ushort wShowWindow, cbReserved2;
        public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }
    [StructLayout(LayoutKind.Sequential)]
    public struct PROCESS_INFORMATION {
        public IntPtr hProcess, hThread;
        public uint dwProcessId, dwThreadId;
    }

    public delegate bool ConsoleCtrlHandler(uint ctrlType);
    private static ConsoleCtrlHandler handler;
    private static readonly ManualResetEvent ctrlEvent = new ManualResetEvent(false);
    private static int lastCtrlType = -1;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint length);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool result);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool TerminateProcess(IntPtr process, uint exitCode);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool GetExitCodeProcess(IntPtr process, out uint exitCode);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CreateProcess(string applicationName, StringBuilder commandLine, IntPtr processAttributes, IntPtr threadAttributes, bool inheritHandles, uint creationFlags, IntPtr environment, string currentDirectory, ref STARTUPINFO startupInfo, out PROCESS_INFORMATION processInformation);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetConsoleCtrlHandler(ConsoleCtrlHandler callback, bool add);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool GenerateConsoleCtrlEvent(uint ctrlEvent, uint processGroupId);

    public static IntPtr CreateKillOnCloseJob()
    {
        IntPtr job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        EXTENDED_LIMITS limits = new EXTENDED_LIMITS();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        int size = Marshal.SizeOf(typeof(EXTENDED_LIMITS));
        IntPtr buffer = Marshal.AllocHGlobal(size);
        try {
            Marshal.StructureToPtr(limits, buffer, false);
            if (!SetInformationJobObject(job, 9, buffer, (uint)size))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            return job;
        }
        catch { CloseHandle(job); throw; }
        finally { Marshal.FreeHGlobal(buffer); }
    }

    public static bool InstallCtrlHandler()
    {
        ctrlEvent.Reset();
        lastCtrlType = -1;
        SetConsoleCtrlHandler(null, false);
        handler = delegate(uint type) {
            if (type == 0 || type == 1 || type == 2) { lastCtrlType = (int)type; ctrlEvent.Set(); return true; }
            return false;
        };
        return SetConsoleCtrlHandler(handler, true);
    }
    public static void RemoveCtrlHandler()
    {
        if (handler != null) { SetConsoleCtrlHandler(handler, false); handler = null; }
    }
    public static bool WaitForCtrl(int milliseconds) { return ctrlEvent.WaitOne(milliseconds); }
    public static int GetLastCtrlType() { return lastCtrlType; }
}
'@
}

function ConvertTo-WindowsCommandLineArgument {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function New-LocalTtsManagedJob {
    $handle = [LocalTtsJobNative]::CreateKillOnCloseJob()
    $global:LocalTtsManagedJobHandle = $handle
    return $handle
}

function Add-ProcessToLocalTtsManagedJob {
    param([Parameter(Mandatory = $true)][IntPtr]$JobHandle, [Parameter(Mandatory = $true)][IntPtr]$ProcessHandle, [Parameter(Mandatory = $true)][int]$ProcessId)
    $inJob = $false
    if (-not [LocalTtsJobNative]::IsProcessInJob($ProcessHandle, $JobHandle, [ref]$inJob)) {
        throw [ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error())
    }
    if ($inJob) { return }
    if (-not [LocalTtsJobNative]::AssignProcessToJobObject($JobHandle, $ProcessHandle)) {
        throw "failed to assign pid $ProcessId to the local TTS job: $([ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error()).Message)"
    }
}

function Start-LocalTtsManagedStackHost {
    param([Parameter(Mandatory = $true)][IntPtr]$JobHandle, [Parameter(Mandatory = $true)][string]$ScriptPath, [Parameter(Mandatory = $true)][string]$ConfigPath, [Parameter(Mandatory = $true)][string]$ReadyEventName, [Parameter(Mandatory = $true)][string]$WorkingDirectory, [switch]$NoGptSovitsStart)
    $powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
    $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ScriptPath, '-ConfigPath', $ConfigPath, '-ReadyEventName', $ReadyEventName)
    if ($NoGptSovitsStart) { $arguments += '-NoGptSovitsStart' }
    $commandLine = (@($powershell) + $arguments | ForEach-Object { ConvertTo-WindowsCommandLineArgument -Value ([string]$_) }) -join ' '
    $startup = New-Object LocalTtsJobNative+STARTUPINFO
    $startup.cb = [Runtime.InteropServices.Marshal]::SizeOf([type]'LocalTtsJobNative+STARTUPINFO')
    $processInfo = New-Object LocalTtsJobNative+PROCESS_INFORMATION
    $flags = [LocalTtsJobNative]::CREATE_SUSPENDED -bor [LocalTtsJobNative]::CREATE_NEW_PROCESS_GROUP
    $created = [LocalTtsJobNative]::CreateProcess($powershell, [Text.StringBuilder]::new($commandLine), [IntPtr]::Zero, [IntPtr]::Zero, $true, $flags, [IntPtr]::Zero, $WorkingDirectory, [ref]$startup, [ref]$processInfo)
    if (-not $created) {
        throw "failed to create managed stack host: $([ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error()).Message) (cwd=$WorkingDirectory; command=$commandLine)"
    }
    try {
        Add-ProcessToLocalTtsManagedJob -JobHandle $JobHandle -ProcessHandle $processInfo.hProcess -ProcessId ([int]$processInfo.dwProcessId)
        if ([LocalTtsJobNative]::ResumeThread($processInfo.hThread) -eq 0xffffffff) {
            throw "failed to resume managed stack host: $([ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error()).Message)"
        }
        return [PSCustomObject]@{ ProcessId = [int]$processInfo.dwProcessId; ProcessHandle = $processInfo.hProcess }
    }
    catch {
        $null = [LocalTtsJobNative]::TerminateProcess($processInfo.hProcess, 1)
        $null = [LocalTtsJobNative]::CloseHandle($processInfo.hProcess)
        throw
    }
    finally { $null = [LocalTtsJobNative]::CloseHandle($processInfo.hThread) }
}

function Get-LocalTtsManagedProcessExitCode {
    param([Parameter(Mandatory = $true)][IntPtr]$ProcessHandle)
    $exitCode = [uint32]0
    if (-not [LocalTtsJobNative]::GetExitCodeProcess($ProcessHandle, [ref]$exitCode)) {
        throw [ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error())
    }
    return [int]$exitCode
}

function Close-LocalTtsManagedJob {
    param([IntPtr]$JobHandle = [IntPtr]::Zero)
    if ($JobHandle -eq [IntPtr]::Zero) { $JobHandle = $global:LocalTtsManagedJobHandle }
    if ($JobHandle -and $JobHandle -ne [IntPtr]::Zero) { $null = [LocalTtsJobNative]::CloseHandle($JobHandle) }
    $global:LocalTtsManagedJobHandle = [IntPtr]::Zero
}
