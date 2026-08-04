if (-not (Get-Command ConvertTo-LocalTtsWindowsArgument -ErrorAction SilentlyContinue)) {
    . (Join-Path $PSScriptRoot 'no-window-process.ps1')
}

function Get-LocalTtsConsoleCtrlSender {
    param([string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')))

    $resolvedRoot = [System.IO.Path]::GetFullPath([string]$RepoRoot)
    $sourcePath = Join-Path $resolvedRoot 'src/LocalTtsConsoleCtrlSender.cs'
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "console Ctrl+C sender source is missing: $sourcePath"
    }

    $sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant().Substring(0, 16)
    $outputDirectory = Join-Path $resolvedRoot 'runtime/tools'
    $senderPath = Join-Path $outputDirectory "local-tts-console-ctrl-sender-$sourceHash.exe"
    if (Test-Path -LiteralPath $senderPath -PathType Leaf) { return $senderPath }

    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    $temporaryPath = Join-Path $outputDirectory ("local-tts-console-ctrl-sender-" + [guid]::NewGuid().ToString('N') + '.exe')
    $source = Get-Content -LiteralPath $sourcePath -Raw -Encoding UTF8
    try {
        Add-Type -TypeDefinition $source -Language CSharp -OutputAssembly $temporaryPath -OutputType WindowsApplication -ErrorAction Stop
        try {
            Move-Item -LiteralPath $temporaryPath -Destination $senderPath -Force -ErrorAction Stop
        }
        catch {
            if (-not (Test-Path -LiteralPath $senderPath -PathType Leaf)) { throw }
        }
    }
    finally {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path -LiteralPath $senderPath -PathType Leaf)) {
        throw "console Ctrl+C sender build did not produce an executable: $senderPath"
    }
    return $senderPath
}

function Send-LocalTtsConsoleCtrlC {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][ValidateRange(1, [int]::MaxValue)][int]$TargetProcessId,
        [ValidateRange(1000, 60000)][int]$TimeoutMs = 10000,
        [string]$ErrorLogPath = '',
        [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..'))
    )

    if (-not (Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue)) {
        throw "Ctrl+C target process is not running: $TargetProcessId"
    }

    $resolvedRoot = [System.IO.Path]::GetFullPath([string]$RepoRoot)
    if ([string]::IsNullOrWhiteSpace($ErrorLogPath)) {
        $ErrorLogPath = Join-Path $resolvedRoot "runtime/logs/console-ctrl-sender-$TargetProcessId.err.log"
    }
    $resolvedErrorPath = [System.IO.Path]::GetFullPath($ErrorLogPath)
    Remove-Item -LiteralPath $resolvedErrorPath -Force -ErrorAction SilentlyContinue

    $senderPath = Get-LocalTtsConsoleCtrlSender -RepoRoot $resolvedRoot
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $senderPath
    $startInfo.Arguments = @(
        (ConvertTo-LocalTtsWindowsArgument -Value ([string]$TargetProcessId)),
        (ConvertTo-LocalTtsWindowsArgument -Value $resolvedErrorPath)
    ) -join ' '
    $startInfo.WorkingDirectory = $resolvedRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

    $sender = New-Object System.Diagnostics.Process
    $sender.StartInfo = $startInfo
    try {
        if (-not $sender.Start()) { throw "console Ctrl+C sender did not start: $senderPath" }
        $sender.Refresh()
        if ($sender.MainWindowHandle -ne [IntPtr]::Zero) {
            throw 'console Ctrl+C sender unexpectedly created a visible window'
        }
        if (-not $sender.WaitForExit($TimeoutMs)) {
            try { $sender.Kill() } catch { }
            throw "console Ctrl+C sender timed out after $TimeoutMs ms"
        }
        if ($sender.ExitCode -ne 0) {
            $detail = if (Test-Path -LiteralPath $resolvedErrorPath) {
                (Get-Content -LiteralPath $resolvedErrorPath -Raw -Encoding UTF8).Trim()
            }
            else { 'no diagnostic file was written' }
            throw "console Ctrl+C sender failed with exit code $($sender.ExitCode): $detail"
        }
    }
    finally {
        $sender.Dispose()
    }
}
