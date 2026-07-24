$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
. (Join-Path $PSScriptRoot 'no-window-process.ps1')

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('local-tts-no-window-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$stdoutPath = Join-Path $tempRoot 'stdout.log'
$stderrPath = Join-Path $tempRoot 'stderr.log'
$powershell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$terminalBefore = @(Get-Process -Name WindowsTerminal -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$process = $null

Assert-True ((ConvertTo-LocalTtsWindowsArgument -Value 'plain') -eq 'plain') 'plain arguments must not be quoted'
Assert-True ((ConvertTo-LocalTtsWindowsArgument -Value 'hello world') -eq '"hello world"') 'arguments with spaces must use Windows command-line quotes'
Assert-True ((ConvertTo-LocalTtsWindowsArgument -Value 'quote"value') -eq '"quote\"value"') 'embedded quotes must be escaped'
Assert-True ((ConvertTo-LocalTtsWindowsArgument -Value 'trail\') -eq 'trail\') 'unquoted trailing backslashes must be preserved'

try {
    $process = Start-LocalTtsNoWindowProcess `
        -FilePath $powershell `
        -ArgumentList @(
            '-NoLogo',
            '-NoProfile',
            '-NonInteractive',
            '-Command',
            "Write-Output 'probe-out'; [Console]::Error.WriteLine('probe-err'); Start-Sleep -Seconds 2; exit 7"
        ) `
        -WorkingDirectory $tempRoot `
        -StandardOutputPath $stdoutPath `
        -StandardErrorPath $stderrPath `
        -RepoRoot $repoRoot

    $process.Refresh()
    Assert-True ($process.MainWindowHandle -eq [IntPtr]::Zero) 'launcher must not own a visible window'

    $child = $null
    $deadline = [DateTime]::UtcNow.AddSeconds(5)
    while ([DateTime]::UtcNow -lt $deadline -and $null -eq $child) {
        $child = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($process.Id)" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $child) { Start-Sleep -Milliseconds 100 }
    }
    Assert-True ($null -ne $child) 'launcher child process was not observed'
    $childProcess = Get-Process -Id ([int]$child.ProcessId) -ErrorAction Stop
    Assert-True ($childProcess.MainWindowHandle -eq [IntPtr]::Zero) 'child process must not own a visible window'

    Assert-True ($process.WaitForExit(15000)) 'launcher did not exit after the child completed'
    Assert-True ($process.ExitCode -eq 7) "launcher must return the child exit code; actual=$($process.ExitCode)"

    $stdout = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw -Encoding UTF8 } else { '' }
    $stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw -Encoding UTF8 } else { '' }
    Assert-True ($stdout -match 'probe-out') 'launcher must preserve child stdout'
    Assert-True ($stderr -match 'probe-err') 'launcher must preserve child stderr'

    $terminalAfter = @(Get-Process -Name WindowsTerminal -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    $newTerminal = @($terminalAfter | Where-Object { $_ -notin $terminalBefore })
    Assert-True ($newTerminal.Count -eq 0) "no new Windows Terminal process may be created: $($newTerminal -join ', ')"

    Write-Host '[OK] no-window process launcher tests passed'
}
finally {
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $process) { $process.Dispose() }
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
