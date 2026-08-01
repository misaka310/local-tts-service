$script:LocalTtsPythonVersion = '3.11.9'
$script:LocalTtsPythonInstallerName = 'python-3.11.9-amd64.exe'
$script:LocalTtsPythonInstallerSha256 = '5EE42C4EEE1E6B4464BB23722F90B45303F79442DF63083F05322F1785F5FDDE'
$script:LocalTtsPythonDownloadUrl = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'
$script:LocalTtsPythonEmbedUrl = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip'
$script:LocalTtsPythonEmbedSha256 = '009D6BF7E3B2DDCA3D784FA09F90FE54336D5B60F0E0F305C37F400BF83CFD3B'
$script:LocalTtsPipVersion = '26.1.2'
$script:LocalTtsPipWheelName = 'pip-26.1.2-py3-none-any.whl'
$script:LocalTtsPipWheelUrl = 'https://files.pythonhosted.org/packages/5d/95/6b5cb3461ea5673ba0995989746db58eb18b91b54dbf331e72f569540946/pip-26.1.2-py3-none-any.whl'
$script:LocalTtsPipWheelSha256 = '382FF9F685EE3BC25864F820AA50505825F10F5458FFFF07E30A6D96E5715CAB'

function New-LocalTtsPythonRuntimeResult {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$PythonPath
    )

    $resolvedPath = [System.IO.Path]::GetFullPath($PythonPath)
    return [pscustomobject]@{
        Source = $Source
        PythonPath = $resolvedPath
        PythonRoot = Split-Path -Parent $resolvedPath
    }
}

function Get-LocalTtsManagedPythonDir {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot 'runtime/tools/python311'))
}

function Test-LocalTtsPython311 {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    if ([string]::IsNullOrWhiteSpace($PythonPath)) { return $false }
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { return $false }
    if ($PythonPath -match '(?i)\\Microsoft\\WindowsApps\\python(?:3(?:\.exe)?|\.exe)?$') { return $false }

    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()
    try {
        $process = Start-Process -FilePath $PythonPath -ArgumentList @('--version') -Wait -PassThru -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        if ($process.ExitCode -ne 0) { return $false }
        $stdout = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue } else { '' }
        $stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue } else { '' }
        $version = (($stdout, $stderr) -join "`n").Trim()
        return ($version -match '^Python 3\.11\.\d+$')
    }
    catch {
        return $false
    }
    finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Resolve-LocalTtsPythonCommandPath {
    param([Parameter(Mandatory = $true)][string]$CommandOrPath)

    if ([string]::IsNullOrWhiteSpace($CommandOrPath)) { return $null }
    if ([System.IO.Path]::IsPathRooted($CommandOrPath)) {
        return [System.IO.Path]::GetFullPath($CommandOrPath)
    }
    $command = Get-Command $CommandOrPath -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    return $null
}

function Resolve-LocalTtsPythonRuntime {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [string]$RequestedPython = ''
    )

    if (-not [string]::IsNullOrWhiteSpace($env:LOCAL_TTS_PYTHON)) {
        $explicitPath = Resolve-LocalTtsPythonCommandPath -CommandOrPath $env:LOCAL_TTS_PYTHON
        if (-not $explicitPath -or -not (Test-LocalTtsPython311 -PythonPath $explicitPath)) {
            throw "LOCAL_TTS_PYTHON is not a usable Python 3.11 executable: $($env:LOCAL_TTS_PYTHON)"
        }
        return New-LocalTtsPythonRuntimeResult -Source 'environment' -PythonPath $explicitPath
    }

    if (-not [string]::IsNullOrWhiteSpace($RequestedPython)) {
        $requestedPath = Resolve-LocalTtsPythonCommandPath -CommandOrPath $RequestedPython
        if ($requestedPath -and (Test-LocalTtsPython311 -PythonPath $requestedPath)) {
            return New-LocalTtsPythonRuntimeResult -Source 'requested' -PythonPath $requestedPath
        }
    }

    $managedPath = Join-Path (Get-LocalTtsManagedPythonDir -RepoRoot $RepoRoot) 'python.exe'
    if (Test-LocalTtsPython311 -PythonPath $managedPath) {
        return New-LocalTtsPythonRuntimeResult -Source 'managed' -PythonPath $managedPath
    }

    $launcher = Get-Command 'py.exe' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($launcher) {
        $launcherStdout = [System.IO.Path]::GetTempFileName()
        $launcherStderr = [System.IO.Path]::GetTempFileName()
        try {
            $launcherProcess = Start-Process -FilePath $launcher.Source -ArgumentList @('-3.11', '-c', 'import sys; print(sys.executable)') -Wait -PassThru -NoNewWindow -RedirectStandardOutput $launcherStdout -RedirectStandardError $launcherStderr
            if ($launcherProcess.ExitCode -eq 0) {
                $launcherPath = (Get-Content -LiteralPath $launcherStdout -Raw -ErrorAction SilentlyContinue).Trim()
                if (Test-LocalTtsPython311 -PythonPath $launcherPath) {
                    return New-LocalTtsPythonRuntimeResult -Source 'launcher' -PythonPath $launcherPath
                }
            }
        }
        catch {}
        finally {
            Remove-Item -LiteralPath $launcherStdout, $launcherStderr -Force -ErrorAction SilentlyContinue
        }
    }

    foreach ($commandName in @('python.exe', 'python')) {
        $commandPath = Resolve-LocalTtsPythonCommandPath -CommandOrPath $commandName
        if ($commandPath -and (Test-LocalTtsPython311 -PythonPath $commandPath)) {
            return New-LocalTtsPythonRuntimeResult -Source 'system' -PythonPath $commandPath
        }
    }

    throw 'Python 3.11 was not found.'
}

function Install-LocalTtsManagedPythonRuntime {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [string]$RequestedPython = '',
        [switch]$DryRun
    )

    # Normal first-run setup must be self-contained.  Only an explicit
    # LOCAL_TTS_PYTHON override may opt out of the repo-managed runtime; a
    # system `python` command is not a portable installation guarantee.
    if (-not [string]::IsNullOrWhiteSpace($env:LOCAL_TTS_PYTHON)) {
        return Resolve-LocalTtsPythonRuntime -RepoRoot $RepoRoot -RequestedPython $RequestedPython
    }

    $managedDir = Get-LocalTtsManagedPythonDir -RepoRoot $RepoRoot
    $managedPath = Join-Path $managedDir 'python.exe'
    if (Test-LocalTtsPython311 -PythonPath $managedPath) {
        return New-LocalTtsPythonRuntimeResult -Source 'managed' -PythonPath $managedPath
    }
    if ($DryRun) {
        Write-Host "[DRY-RUN] download pinned Python $script:LocalTtsPythonVersion from $script:LocalTtsPythonDownloadUrl"
        Write-Host "[DRY-RUN] verify SHA-256: $script:LocalTtsPythonInstallerSha256"
        Write-Host "[DRY-RUN] install Python into $managedDir"
        return New-LocalTtsPythonRuntimeResult -Source 'managed' -PythonPath $managedPath
    }

    $toolsDir = Split-Path -Parent $managedDir
    New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
    $installerPath = Join-Path $toolsDir ('.' + $script:LocalTtsPythonInstallerName + '.download.exe')
    $installerLogPath = Join-Path $toolsDir 'python311-installer.log'

    try {
        Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $managedDir -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $installerLogPath -Force -ErrorAction SilentlyContinue

        Write-Host "[INFO] Downloading Python $script:LocalTtsPythonVersion..."
        $previousProgressPreference = $ProgressPreference
        try {
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -UseBasicParsing -Uri $script:LocalTtsPythonDownloadUrl -OutFile $installerPath
        }
        finally {
            $ProgressPreference = $previousProgressPreference
        }

        Write-Host '[INFO] Verifying Python installer SHA-256...'
        $actualHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($actualHash -ne $script:LocalTtsPythonInstallerSha256) {
            throw "Python installer SHA-256 mismatch. expected=$script:LocalTtsPythonInstallerSha256 actual=$actualHash"
        }

        $installerArguments = @(
            '/quiet',
            'InstallAllUsers=0',
            "TargetDir=`"$managedDir`"",
            'PrependPath=0',
            'AppendPath=0',
            'Include_launcher=0',
            'InstallLauncherAllUsers=0',
            'Include_pip=1',
            'Include_test=0',
            'Include_doc=0',
            'Include_tcltk=0',
            'Include_tools=1',
            'Shortcuts=0',
            'AssociateFiles=0',
            'CompileAll=0',
            "/log `"$installerLogPath`""
        )
        $process = Start-Process -FilePath $installerPath -ArgumentList $installerArguments -Wait -PassThru -NoNewWindow
        if ($process.ExitCode -notin @(0, 3010)) {
            throw "Python installer failed with exit code $($process.ExitCode)"
        }
    }
    finally {
        Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-LocalTtsPython311 -PythonPath $managedPath)) {
        # The Windows installer enters maintenance mode when this Python version
        # is already installed elsewhere. Fall back to the official embeddable
        # distribution so each repository still receives an independent runtime.
        $embedPath = Join-Path $toolsDir '.python-3.11.9-embed-amd64.zip'
        $pipWheelPath = Join-Path $toolsDir ('.' + $script:LocalTtsPipWheelName)
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $script:LocalTtsPythonEmbedUrl -OutFile $embedPath
            if ((Get-FileHash -LiteralPath $embedPath -Algorithm SHA256).Hash.ToUpperInvariant() -ne $script:LocalTtsPythonEmbedSha256) { throw 'embedded Python SHA-256 mismatch' }
            Expand-Archive -LiteralPath $embedPath -DestinationPath $managedDir -Force
            $sitePackagesPath = Join-Path $managedDir 'Lib\site-packages'
            New-Item -ItemType Directory -Force -Path $sitePackagesPath | Out-Null
            $pthPath = Join-Path $managedDir 'python311._pth'
            $pthText = Get-Content -LiteralPath $pthPath -Raw -Encoding ASCII
            $pthText = $pthText -replace '#import site', "Lib\site-packages`r`nimport site"
            $pthText | Set-Content -LiteralPath $pthPath -Encoding ASCII

            Invoke-WebRequest -UseBasicParsing -Uri $script:LocalTtsPipWheelUrl -OutFile $pipWheelPath
            $actualPipWheelHash = (Get-FileHash -LiteralPath $pipWheelPath -Algorithm SHA256).Hash.ToUpperInvariant()
            if ($actualPipWheelHash -ne $script:LocalTtsPipWheelSha256) {
                throw "pip wheel SHA-256 mismatch. expected=$script:LocalTtsPipWheelSha256 actual=$actualPipWheelHash"
            }
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            [System.IO.Compression.ZipFile]::ExtractToDirectory($pipWheelPath, $sitePackagesPath)
            $pipVersionProcess = Start-Process -FilePath $managedPath -ArgumentList @('-m', 'pip', '--version') -Wait -PassThru -NoNewWindow
            if ($pipVersionProcess.ExitCode -ne 0) { throw "pinned pip $script:LocalTtsPipVersion bootstrap failed with exit code $($pipVersionProcess.ExitCode)" }
            $virtualenvProcess = Start-Process -FilePath $managedPath -ArgumentList @('-m', 'pip', 'install', 'virtualenv', '--disable-pip-version-check', '--no-warn-script-location') -Wait -PassThru -NoNewWindow
            if ($virtualenvProcess.ExitCode -ne 0) { throw "virtualenv install failed with exit code $($virtualenvProcess.ExitCode)" }
        }
        finally {
            Remove-Item -LiteralPath $embedPath, $pipWheelPath -Force -ErrorAction SilentlyContinue
        }
        if (-not (Test-LocalTtsPython311 -PythonPath $managedPath)) {
            $detail = if (Test-Path -LiteralPath $installerLogPath) { (Get-Content -LiteralPath $installerLogPath -Tail 20 -ErrorAction SilentlyContinue) -join "`n" } else { 'installer log was not created' }
            throw "Repo-managed Python 3.11 installation did not complete: $managedPath`n$detail"
        }
    }

    Write-Host "[DONE] Python $script:LocalTtsPythonVersion is ready: $managedDir"
    return New-LocalTtsPythonRuntimeResult -Source 'managed' -PythonPath $managedPath
}
