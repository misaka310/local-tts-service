using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

internal static class LocalTtsNoWindowLauncher
{
    private const uint JobObjectLimitKillOnJobClose = 0x00002000;
    private const int JobObjectExtendedLimitInformationClass = 9;

    [StructLayout(LayoutKind.Sequential)]
    private struct JobObjectBasicLimitInformation
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public IntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct IoCounters
    {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct JobObjectExtendedLimitInformation
    {
        public JobObjectBasicLimitInformation BasicLimitInformation;
        public IoCounters IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateJobObject(IntPtr jobAttributes, string name);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetInformationJobObject(
        IntPtr job,
        int informationClass,
        IntPtr information,
        uint informationLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr handle);

    private sealed class Options
    {
        public string FilePath = string.Empty;
        public string WorkingDirectory = string.Empty;
        public string StandardOutputPath = string.Empty;
        public string StandardErrorPath = string.Empty;
        public readonly List<string> Arguments = new List<string>();
    }

    [STAThread]
    private static int Main(string[] args)
    {
        Options options = null;
        try
        {
            options = ParseArguments(args);
            EnsureParentDirectory(options.StandardOutputPath);
            EnsureParentDirectory(options.StandardErrorPath);
            return RunChild(options);
        }
        catch (Exception ex)
        {
            if (options != null && !string.IsNullOrWhiteSpace(options.StandardErrorPath))
            {
                try
                {
                    File.AppendAllText(
                        options.StandardErrorPath,
                        "[no-window-launcher] " + ex + Environment.NewLine,
                        new UTF8Encoding(false));
                }
                catch
                {
                }
            }
            return 1;
        }
    }

    private static Options ParseArguments(string[] args)
    {
        var options = new Options();
        var index = 0;
        while (index < args.Length)
        {
            var current = args[index++];
            if (current == "--")
            {
                while (index < args.Length)
                {
                    options.Arguments.Add(args[index++]);
                }
                break;
            }

            if (index >= args.Length)
            {
                throw new ArgumentException("Missing value for " + current + ".");
            }

            var value = args[index++];
            switch (current)
            {
                case "--file":
                    options.FilePath = value;
                    break;
                case "--working-directory":
                    options.WorkingDirectory = value;
                    break;
                case "--stdout":
                    options.StandardOutputPath = value;
                    break;
                case "--stderr":
                    options.StandardErrorPath = value;
                    break;
                default:
                    throw new ArgumentException("Unknown argument: " + current);
            }
        }

        if (string.IsNullOrWhiteSpace(options.FilePath))
        {
            throw new ArgumentException("--file is required.");
        }
        if (string.IsNullOrWhiteSpace(options.WorkingDirectory))
        {
            throw new ArgumentException("--working-directory is required.");
        }
        if (string.IsNullOrWhiteSpace(options.StandardOutputPath))
        {
            throw new ArgumentException("--stdout is required.");
        }
        if (string.IsNullOrWhiteSpace(options.StandardErrorPath))
        {
            throw new ArgumentException("--stderr is required.");
        }
        return options;
    }

    private static IntPtr CreateKillOnCloseJob()
    {
        var job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero)
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not create the child-process job object.");
        }

        var limits = new JobObjectExtendedLimitInformation();
        limits.BasicLimitInformation.LimitFlags = JobObjectLimitKillOnJobClose;
        var size = Marshal.SizeOf(typeof(JobObjectExtendedLimitInformation));
        var buffer = Marshal.AllocHGlobal(size);
        try
        {
            Marshal.StructureToPtr(limits, buffer, false);
            if (!SetInformationJobObject(job, JobObjectExtendedLimitInformationClass, buffer, (uint)size))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not configure the child-process job object.");
            }
            return job;
        }
        catch
        {
            CloseHandle(job);
            throw;
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }

    private static int RunChild(Options options)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = options.FilePath,
            Arguments = JoinArguments(options.Arguments),
            WorkingDirectory = options.WorkingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = new UTF8Encoding(false),
            StandardErrorEncoding = new UTF8Encoding(false)
        };

        var job = CreateKillOnCloseJob();
        try
        {
            using (var stdout = CreateWriter(options.StandardOutputPath))
            using (var stderr = CreateWriter(options.StandardErrorPath))
            using (var stdoutClosed = new ManualResetEvent(false))
            using (var stderrClosed = new ManualResetEvent(false))
            using (var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true })
            {
                var stdoutLock = new object();
                var stderrLock = new object();

                process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs eventArgs)
                {
                    if (eventArgs.Data == null)
                    {
                        stdoutClosed.Set();
                        return;
                    }
                    lock (stdoutLock)
                    {
                        stdout.WriteLine(eventArgs.Data);
                    }
                };
                process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs eventArgs)
                {
                    if (eventArgs.Data == null)
                    {
                        stderrClosed.Set();
                        return;
                    }
                    lock (stderrLock)
                    {
                        stderr.WriteLine(eventArgs.Data);
                    }
                };

                if (!process.Start())
                {
                    throw new InvalidOperationException("The child process did not start.");
                }
                if (!AssignProcessToJobObject(job, process.Handle))
                {
                    var error = Marshal.GetLastWin32Error();
                    try { process.Kill(); }
                    catch { }
                    throw new Win32Exception(error, "Could not attach the child process to its kill-on-close job object.");
                }

                process.StandardInput.Close();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                process.WaitForExit();
                stdoutClosed.WaitOne(5000);
                stderrClosed.WaitOne(5000);
                return process.ExitCode;
            }
        }
        finally
        {
            CloseHandle(job);
        }
    }

    private static StreamWriter CreateWriter(string path)
    {
        var stream = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.ReadWrite);
        return new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = true };
    }

    private static void EnsureParentDirectory(string path)
    {
        var parent = Path.GetDirectoryName(Path.GetFullPath(path));
        if (!string.IsNullOrWhiteSpace(parent))
        {
            Directory.CreateDirectory(parent);
        }
    }

    private static string JoinArguments(IEnumerable<string> arguments)
    {
        var builder = new StringBuilder();
        foreach (var argument in arguments)
        {
            if (builder.Length > 0)
            {
                builder.Append(' ');
            }
            builder.Append(QuoteArgument(argument ?? string.Empty));
        }
        return builder.ToString();
    }

    private static string QuoteArgument(string value)
    {
        if (value.Length > 0 && value.IndexOfAny(new[] { ' ', '\t', '\n', '\v', '"' }) < 0)
        {
            return value;
        }

        var builder = new StringBuilder();
        builder.Append('"');
        var backslashes = 0;
        foreach (var character in value)
        {
            if (character == '\\')
            {
                backslashes++;
                continue;
            }

            if (character == '"')
            {
                builder.Append('\\', backslashes * 2 + 1);
                builder.Append('"');
                backslashes = 0;
                continue;
            }

            builder.Append('\\', backslashes);
            backslashes = 0;
            builder.Append(character);
        }
        builder.Append('\\', backslashes * 2);
        builder.Append('"');
        return builder.ToString();
    }
}
