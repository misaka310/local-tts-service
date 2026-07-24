function ConvertTo-LocalTtsWindowsArgument {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)

    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') {
        return $Value
    }

    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $backslashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') {
            $backslashes++
            continue
        }
        if ($character -eq '"') {
            [void]$builder.Append(('\' * (($backslashes * 2) + 1)))
            [void]$builder.Append('"')
            $backslashes = 0
            continue
        }
        if ($backslashes -gt 0) {
            [void]$builder.Append(('\' * $backslashes))
            $backslashes = 0
        }
        [void]$builder.Append($character)
    }
    if ($backslashes -gt 0) {
        [void]$builder.Append(('\' * ($backslashes * 2)))
    }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Get-LocalTtsNoWindowLauncher {
    param([string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')))

    $resolvedRoot = [System.IO.Path]::GetFullPath([string]$RepoRoot)
    $sourcePath = Join-Path $resolvedRoot 'src/LocalTtsNoWindowLauncher.cs'
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "no-window launcher source is missing: $sourcePath"
    }

    $sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant().Substring(0, 16)
    $outputDirectory = Join-Path $resolvedRoot 'runtime/tools'
    $launcherPath = Join-Path $outputDirectory "local-tts-no-window-launcher-$sourceHash.exe"
    if (Test-Path -LiteralPath $launcherPath -PathType Leaf) {
        return $launcherPath
    }

    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    $temporaryPath = Join-Path $outputDirectory ("local-tts-no-window-launcher-" + [guid]::NewGuid().ToString('N') + '.exe')
    $source = Get-Content -LiteralPath $sourcePath -Raw -Encoding UTF8
    try {
        Add-Type -TypeDefinition $source -Language CSharp -OutputAssembly $temporaryPath -OutputType WindowsApplication -ErrorAction Stop
        try {
            Move-Item -LiteralPath $temporaryPath -Destination $launcherPath -Force -ErrorAction Stop
        }
        catch {
            if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
                throw
            }
        }
    }
    finally {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
        throw "no-window launcher build did not produce an executable: $launcherPath"
    }
    return $launcherPath
}

function Start-LocalTtsNoWindowProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$StandardOutputPath,
        [Parameter(Mandatory = $true)][string]$StandardErrorPath,
        [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..'))
    )

    $resolvedExecutable = [System.IO.Path]::GetFullPath($FilePath)
    if (-not (Test-Path -LiteralPath $resolvedExecutable -PathType Leaf)) {
        throw "process executable is missing: $resolvedExecutable"
    }

    $resolvedWorkingDirectory = [System.IO.Path]::GetFullPath($WorkingDirectory)
    if (-not (Test-Path -LiteralPath $resolvedWorkingDirectory -PathType Container)) {
        throw "process working directory is missing: $resolvedWorkingDirectory"
    }

    $launcherPath = Get-LocalTtsNoWindowLauncher -RepoRoot $RepoRoot
    $launcherArguments = @(
        '--file', $resolvedExecutable,
        '--working-directory', $resolvedWorkingDirectory,
        '--stdout', [System.IO.Path]::GetFullPath($StandardOutputPath),
        '--stderr', [System.IO.Path]::GetFullPath($StandardErrorPath),
        '--'
    ) + @($ArgumentList | ForEach-Object { [string]$_ })

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $launcherPath
    $startInfo.Arguments = ($launcherArguments | ForEach-Object { ConvertTo-LocalTtsWindowsArgument -Value ([string]$_) }) -join ' '
    $startInfo.WorkingDirectory = $resolvedWorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $startInfo.RedirectStandardInput = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        $process.Dispose()
        throw "no-window launcher did not start: $launcherPath"
    }
    $process.StandardInput.Close()
    return $process
}
