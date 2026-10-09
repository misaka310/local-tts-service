using System;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

internal static class LocalTtsConsoleCtrlSender
{
    private const uint CtrlCEvent = 0;

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AttachConsole(uint processId);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool FreeConsole();

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GenerateConsoleCtrlEvent(uint ctrlEvent, uint processGroupId);

    [STAThread]
    private static int Main(string[] args)
    {
        var errorPath = args.Length >= 2 ? args[1] : string.Empty;
        try
        {
            uint targetProcessId;
            if (args.Length < 1 || !uint.TryParse(args[0], NumberStyles.None, CultureInfo.InvariantCulture, out targetProcessId) || targetProcessId == 0)
            {
                throw new ArgumentException("A positive target process ID is required.");
            }

            FreeConsole();
            if (!AttachConsole(targetProcessId))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not attach to the target console.");
            }

            try
            {
                if (!SetConsoleCtrlHandler(IntPtr.Zero, true))
                {
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not ignore Ctrl+C in the sender process.");
                }
                if (!GenerateConsoleCtrlEvent(CtrlCEvent, 0))
                {
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not generate Ctrl+C in the target console.");
                }
                Thread.Sleep(500);
            }
            finally
            {
                FreeConsole();
            }

            if (!string.IsNullOrWhiteSpace(errorPath) && File.Exists(errorPath)) File.Delete(errorPath);
            return 0;
        }
        catch (Exception ex)
        {
            WriteError(errorPath, ex);
            return 1;
        }
    }

    private static void WriteError(string path, Exception error)
    {
        if (string.IsNullOrWhiteSpace(path)) return;
        try
        {
            var parent = Path.GetDirectoryName(Path.GetFullPath(path));
            if (!string.IsNullOrWhiteSpace(parent)) Directory.CreateDirectory(parent);
            File.WriteAllText(path, error.ToString() + Environment.NewLine, new UTF8Encoding(false));
        }
        catch
        {
        }
    }
}
