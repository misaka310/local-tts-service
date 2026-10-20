$script:LocalTtsGitVersion = '2.55.0.2'
$script:LocalTtsGitArchiveName = 'MinGit-2.55.0.2-64-bit.zip'
$script:LocalTtsGitArchiveSha256 = 'E3EA2944CEA4B3FABCD69C7C1669EF69B1B66C05AC7806D81224D0ABAD2DEC31'
$script:LocalTtsGitDownloadUrl = 'https://github.com/git-for-windows/git/releases/download/v2.55.0.windows.2/MinGit-2.55.0.2-64-bit.zip'

function New-LocalTtsGitRuntimeResult {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$GitRoot,
        [Parameter(Mandatory = $true)][string]$GitPath
    )

    $resolvedRoot = [System.IO.Path]::GetFullPath($GitRoot)
    $resolvedGitPath = [System.IO.Path]::GetFullPath($GitPath)
    return [pscustomobject]@{
        Source = $Source
        GitRoot = $resolvedRoot
        GitPath = $resolvedGitPath
        PathEntries = @(
            (Join-Path $resolvedRoot 'cmd'),
            (Join-Path $resolvedRoot 'mingw64\bin')
        )
    }
}

function Test-LocalTtsGitRuntime {
    param([Parameter(Mandatory = $true)][string]$GitRoot)

    if ([string]::IsNullOrWhiteSpace($GitRoot)) { return $false }
    return (Test-Path -LiteralPath (Join-Path $GitRoot 'cmd\git.exe') -PathType Leaf)
}

function Get-LocalTtsManagedGitRoot {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot 'runtime\tools\mingit'))
}

function Resolve-LocalTtsGitRuntime {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    if (-not [string]::IsNullOrWhiteSpace($env:LOCAL_TTS_GIT_DIR)) {
        $explicitRoot = [System.IO.Path]::GetFullPath($env:LOCAL_TTS_GIT_DIR)
        if (-not (Test-LocalTtsGitRuntime -GitRoot $explicitRoot)) {
            throw "LOCAL_TTS_GIT_DIR does not contain cmd\git.exe: $explicitRoot"
        }
        return New-LocalTtsGitRuntimeResult -Source 'environment' -GitRoot $explicitRoot -GitPath (Join-Path $explicitRoot 'cmd\git.exe')
    }

    $managedRoot = Get-LocalTtsManagedGitRoot -RepoRoot $RepoRoot
    if (Test-LocalTtsGitRuntime -GitRoot $managedRoot) {
        return New-LocalTtsGitRuntimeResult -Source 'managed' -GitRoot $managedRoot -GitPath (Join-Path $managedRoot 'cmd\git.exe')
    }

    $systemGit = Get-Command 'git.exe' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $systemGit) {
        $systemDir = Split-Path -Parent $systemGit.Source
        $systemRoot = $systemDir
        if ((Split-Path -Leaf $systemDir) -eq 'cmd') {
            $systemRoot = Split-Path -Parent $systemDir
        } elseif ((Split-Path -Leaf $systemDir) -eq 'bin' -and (Split-Path -Leaf (Split-Path -Parent $systemDir)) -eq 'mingw64') {
            $systemRoot = Split-Path -Parent (Split-Path -Parent $systemDir)
        }
        return New-LocalTtsGitRuntimeResult -Source 'system' -GitRoot $systemRoot -GitPath $systemGit.Source
    }

    throw 'Git was not found. Run local-tts.bat -ForceSetup to install or repair the repo-managed runtime.'
}

function Install-LocalTtsManagedGitRuntime {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [switch]$DryRun
    )

    $managedRoot = Get-LocalTtsManagedGitRoot -RepoRoot $RepoRoot
    if (Test-LocalTtsGitRuntime -GitRoot $managedRoot) {
        return New-LocalTtsGitRuntimeResult -Source 'managed' -GitRoot $managedRoot -GitPath (Join-Path $managedRoot 'cmd\git.exe')
    }

    if ($DryRun) {
        Write-Host "[DRY-RUN] download pinned MinGit $script:LocalTtsGitVersion from $script:LocalTtsGitDownloadUrl"
        Write-Host "[DRY-RUN] verify SHA-256: $script:LocalTtsGitArchiveSha256"
        Write-Host "[DRY-RUN] install MinGit into $managedRoot"
        return New-LocalTtsGitRuntimeResult -Source 'managed' -GitRoot $managedRoot -GitPath (Join-Path $managedRoot 'cmd\git.exe')
    }

    $toolsDir = Split-Path -Parent $managedRoot
    New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
    $archivePath = Join-Path $toolsDir '.mingit.download.zip'
    $stagingDir = Join-Path $toolsDir ('.mingit-extract-' + [guid]::NewGuid().ToString('N'))

    try {
        Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Path $stagingDir -Force | Out-Null

        Write-Host "[INFO] Downloading portable MinGit $script:LocalTtsGitVersion..."
        $previousProgressPreference = $ProgressPreference
        try {
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -UseBasicParsing -Uri $script:LocalTtsGitDownloadUrl -OutFile $archivePath
        }
        finally {
            $ProgressPreference = $previousProgressPreference
        }

        Write-Host '[INFO] Verifying portable MinGit SHA-256...'
        $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($actualHash -ne $script:LocalTtsGitArchiveSha256) {
            throw "MinGit archive SHA-256 mismatch. expected=$script:LocalTtsGitArchiveSha256 actual=$actualHash"
        }

        Expand-Archive -LiteralPath $archivePath -DestinationPath $stagingDir -Force
        if (-not (Test-LocalTtsGitRuntime -GitRoot $stagingDir)) {
            throw 'Downloaded MinGit archive did not contain cmd\git.exe.'
        }

        Remove-Item -LiteralPath $managedRoot -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $stagingDir -Destination $managedRoot
    }
    finally {
        Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-LocalTtsGitRuntime -GitRoot $managedRoot)) {
        throw "Portable MinGit installation did not complete: $managedRoot"
    }

    Write-Host "[DONE] Portable MinGit is ready: $managedRoot"
    return New-LocalTtsGitRuntimeResult -Source 'managed' -GitRoot $managedRoot -GitPath (Join-Path $managedRoot 'cmd\git.exe')
}

function Add-LocalTtsGitRuntimeToPath {
    param([Parameter(Mandatory = $true)][object]$GitRuntime)

    $entries = @($GitRuntime.PathEntries | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
    if ($entries.Count -eq 0) { return }
    $env:PATH = (($entries + @($env:PATH)) -join [System.IO.Path]::PathSeparator)
}
