$script:LocalTtsNodeVersion = 'v24.18.0'
$script:LocalTtsNodeArchiveName = 'node-v24.18.0-win-x64.zip'
$script:LocalTtsNodeArchiveSha256 = '0AE68406B42D7725661DA979B1403EC9926DA205C6770827F33AAC9D8F26E821'
$script:LocalTtsNodeDownloadUrl = 'https://nodejs.org/dist/v24.18.0/node-v24.18.0-win-x64.zip'

function New-LocalTtsNodeRuntimeResult {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$NodeDir
    )

    $resolvedDir = [System.IO.Path]::GetFullPath($NodeDir)
    return [pscustomobject]@{
        Source = $Source
        NodeDir = $resolvedDir
        NodePath = Join-Path $resolvedDir 'node.exe'
        NpmPath = Join-Path $resolvedDir 'npm.cmd'
    }
}

function Test-LocalTtsNodeRuntimePair {
    param([Parameter(Mandatory = $true)][string]$NodeDir)

    if ([string]::IsNullOrWhiteSpace($NodeDir)) { return $false }
    return (
        (Test-Path -LiteralPath (Join-Path $NodeDir 'node.exe') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $NodeDir 'npm.cmd') -PathType Leaf)
    )
}

function Get-LocalTtsManagedNodeDir {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot 'runtime/tools/node'))
}

function Resolve-LocalTtsNodeRuntime {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    if (-not [string]::IsNullOrWhiteSpace($env:LOCAL_TTS_NODE_DIR)) {
        $explicitDir = [System.IO.Path]::GetFullPath($env:LOCAL_TTS_NODE_DIR)
        if (-not (Test-LocalTtsNodeRuntimePair -NodeDir $explicitDir)) {
            throw "LOCAL_TTS_NODE_DIR does not contain node.exe and npm.cmd: $explicitDir"
        }
        return New-LocalTtsNodeRuntimeResult -Source 'environment' -NodeDir $explicitDir
    }

    $managedDir = Get-LocalTtsManagedNodeDir -RepoRoot $RepoRoot
    if (Test-LocalTtsNodeRuntimePair -NodeDir $managedDir) {
        return New-LocalTtsNodeRuntimeResult -Source 'managed' -NodeDir $managedDir
    }

    $systemNode = Get-Command 'node.exe' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $systemNode) {
        $systemDir = Split-Path -Parent $systemNode.Source
        if (Test-LocalTtsNodeRuntimePair -NodeDir $systemDir) {
            return New-LocalTtsNodeRuntimeResult -Source 'system' -NodeDir $systemDir
        }
    }

    throw "Node.js/npm was not found. Run local-tts.bat -ForceSetup to install or repair the repo-managed runtime."
}

function Install-LocalTtsManagedNodeRuntime {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [switch]$DryRun
    )

    $managedDir = Get-LocalTtsManagedNodeDir -RepoRoot $RepoRoot
    if (Test-LocalTtsNodeRuntimePair -NodeDir $managedDir) {
        return New-LocalTtsNodeRuntimeResult -Source 'managed' -NodeDir $managedDir
    }

    if ($DryRun) {
        Write-Host "[DRY-RUN] download pinned Node.js $script:LocalTtsNodeVersion from $script:LocalTtsNodeDownloadUrl"
        Write-Host "[DRY-RUN] verify SHA-256: $script:LocalTtsNodeArchiveSha256"
        Write-Host "[DRY-RUN] install Node.js into $managedDir"
        return New-LocalTtsNodeRuntimeResult -Source 'managed' -NodeDir $managedDir
    }

    $toolsDir = Split-Path -Parent $managedDir
    New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
    $archiveBaseName = [System.IO.Path]::GetFileNameWithoutExtension($script:LocalTtsNodeArchiveName)
    $archivePath = Join-Path $toolsDir ('.' + $archiveBaseName + '.download.zip')
    $stagingDir = Join-Path $toolsDir ('.node-extract-' + [guid]::NewGuid().ToString('N'))

    try {
        Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Path $stagingDir -Force | Out-Null

        Write-Host "[INFO] Downloading portable Node.js $script:LocalTtsNodeVersion..."
        $previousProgressPreference = $ProgressPreference
        try {
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -UseBasicParsing -Uri $script:LocalTtsNodeDownloadUrl -OutFile $archivePath
        }
        finally {
            $ProgressPreference = $previousProgressPreference
        }

        Write-Host '[INFO] Verifying portable Node.js SHA-256...'
        $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($actualHash -ne $script:LocalTtsNodeArchiveSha256) {
            throw "Node.js archive SHA-256 mismatch. expected=$script:LocalTtsNodeArchiveSha256 actual=$actualHash"
        }

        $expanded = $false
        for ($attempt = 1; $attempt -le 6; $attempt++) {
            try {
                Expand-Archive -LiteralPath $archivePath -DestinationPath $stagingDir -Force
                $expanded = $true
                break
            }
            catch {
                if ($attempt -ge 6) { throw }
                Write-Host "[WAIT] Node.js archive is temporarily busy; retrying extraction ($attempt/6)..."
                Start-Sleep -Seconds 2
            }
        }
        if (-not $expanded) { throw 'Portable Node.js archive extraction did not complete.' }
        $extractedDir = Join-Path $stagingDir 'node-v24.18.0-win-x64'
        if (-not (Test-LocalTtsNodeRuntimePair -NodeDir $extractedDir)) {
            throw "Downloaded Node.js archive did not contain the expected node.exe/npm.cmd pair."
        }

        Remove-Item -LiteralPath $managedDir -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $extractedDir -Destination $managedDir
    }
    finally {
        Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-LocalTtsNodeRuntimePair -NodeDir $managedDir)) {
        throw "Portable Node.js installation did not complete: $managedDir"
    }

    Write-Host "[DONE] Portable Node.js is ready: $managedDir"
    return New-LocalTtsNodeRuntimeResult -Source 'managed' -NodeDir $managedDir
}
