[CmdletBinding()]
param(
    [ValidateRange(10, 900)]
    [int]$StartupTimeoutSeconds = 240,
    [switch]$NoOpenBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$configPath = Join-Path $repoRoot 'config\config.local.json'
$launchScript = Join-Path $PSScriptRoot 'launch-local-tts.ps1'
$frontendScript = Join-Path $PSScriptRoot 'start-tts-frontend.ps1'
$sharedRunnerRoot = if ($env:WINDOWS_GUI_CI_RUNNER_ROOT) {
    [IO.Path]::GetFullPath($env:WINDOWS_GUI_CI_RUNNER_ROOT)
} else {
    [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $repoRoot) '74_windows-gui-ci-runner'))
}
$noWindowLauncher = Join-Path $sharedRunnerRoot 'scripts\host\Start-NoWindowDetached.ps1'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$logRoot = Join-Path $repoRoot 'runtime\logs'
$statePath = Join-Path $logRoot 'companion-launch-state.json'
$stdoutPath = Join-Path $logRoot 'companion-launch.stdout.log'
$stderrPath = Join-Path $logRoot 'companion-launch.stderr.log'

function Get-JsonPropertyValue {
    param(
        [AllowNull()][object]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()][object]$Default = $null
    )
    if ($null -eq $Object) { return $Default }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value) { return $Default }
    return $property.Value
}

function Test-HttpSuccess {
    param([Parameter(Mandatory = $true)][string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        return [int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 300
    }
    catch {
        return $false
    }
}

function Quote-NativeArgument {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    return '"' + $Value.Replace('"', '\"') + '"'
}

foreach ($requiredPath in @($configPath, $launchScript, $frontendScript, $noWindowLauncher, $powershell)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required launcher component was not found: $requiredPath"
    }
}

$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$apiHost = [string](Get-JsonPropertyValue -Object $config -Name 'host' -Default '127.0.0.1')
$apiPort = [int](Get-JsonPropertyValue -Object $config -Name 'port' -Default 8730)
$frontendConfig = Get-JsonPropertyValue -Object $config -Name 'frontend'
$frontHost = [string](Get-JsonPropertyValue -Object $frontendConfig -Name 'host' -Default '127.0.0.1')
$frontPort = [int](Get-JsonPropertyValue -Object $frontendConfig -Name 'port' -Default 5177)
$apiHealthUrl = "http://$apiHost`:$apiPort/health"
$frontUrl = "http://$frontHost`:$frontPort"
$frontHealthUrl = "$frontUrl/api/health"

if (Test-HttpSuccess -Url $frontHealthUrl) {
    if (-not $NoOpenBrowser) { Start-Process $frontUrl | Out-Null }
    [pscustomobject]@{ started = $false; alreadyReady = $true; url = $frontUrl } | ConvertTo-Json -Compress
    exit 0
}

if (Test-HttpSuccess -Url $apiHealthUrl) {
    & $frontendScript -ConfigPath $configPath -OpenBrowser:(-not $NoOpenBrowser) -NoInstall
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    [pscustomobject]@{ started = $false; frontendStarted = $true; url = $frontUrl } | ConvertTo-Json -Compress
    exit 0
}

$escapedLaunchScript = [Regex]::Escape($launchScript)
$existingLauncher = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -ieq 'powershell.exe' -and
    $_.CommandLine -and
    $_.CommandLine -match $escapedLaunchScript
}) | Select-Object -First 1

if ($null -ne $existingLauncher) {
    $launcherAgeSeconds = [double]::PositiveInfinity
    try {
        $launcherStartedAt = [DateTime]$existingLauncher.CreationDate
        $launcherAgeSeconds = ([DateTime]::Now - $launcherStartedAt).TotalSeconds
    }
    catch {
        $launcherAgeSeconds = [double]::PositiveInfinity
    }

    $maximumStartupAgeSeconds = [double]$StartupTimeoutSeconds + 30.0
    if ($launcherAgeSeconds -gt $maximumStartupAgeSeconds) {
        Write-Warning (
            "A stale local TTS launcher was found without a healthy backend or frontend. " +
            "Restarting it now: pid=$($existingLauncher.ProcessId), age=$([Math]::Round($launcherAgeSeconds, 1))s"
        )
        Stop-Process -Id ([int]$existingLauncher.ProcessId) -Force -ErrorAction SilentlyContinue
        $stopDeadline = [DateTime]::UtcNow.AddSeconds(10)
        do {
            Start-Sleep -Milliseconds 200
            $remaining = Get-Process -Id ([int]$existingLauncher.ProcessId) -ErrorAction SilentlyContinue
        } while ($null -ne $remaining -and [DateTime]::UtcNow -lt $stopDeadline)
        if ($null -ne $remaining) {
            throw "The stale local TTS launcher could not be stopped: pid=$($existingLauncher.ProcessId)"
        }
        $existingLauncher = $null
    }
}

$launchResult = $null
if ($null -eq $existingLauncher) {
    New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
    $arguments = @(
        '-NoLogo',
        '-NoProfile',
        '-NonInteractive',
        '-ExecutionPolicy', 'Bypass',
        '-File', $launchScript,
        '-NoOpenBrowser'
    )
    $argumentText = ($arguments | ForEach-Object { Quote-NativeArgument ([string]$_) }) -join ' '
    $launchJson = & $noWindowLauncher `
        -FilePath $powershell `
        -Arguments $argumentText `
        -WorkingDirectory $repoRoot `
        -StatePath $statePath `
        -StdoutPath $stdoutPath `
        -StderrPath $stderrPath
    $launchResult = $launchJson | ConvertFrom-Json
    if (-not $launchResult.started) {
        throw "The no-window local TTS launcher failed. See $stderrPath"
    }
}

$deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
do {
    if (Test-HttpSuccess -Url $frontHealthUrl) {
        if (-not $NoOpenBrowser) { Start-Process $frontUrl | Out-Null }
        [pscustomobject]@{
            started = ($null -ne $launchResult)
            alreadyStarting = ($null -ne $existingLauncher)
            createNoWindow = $true
            url = $frontUrl
            statePath = $statePath
            stdoutPath = $stdoutPath
            stderrPath = $stderrPath
        } | ConvertTo-Json -Compress
        exit 0
    }

    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        try {
            $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([string]$state.status -eq 'failed') {
                throw "The detached local TTS process failed. See $stderrPath"
            }
        }
        catch {
            if ($_.Exception.Message -like 'The detached local TTS process failed*') { throw }
        }
    }
    Start-Sleep -Milliseconds 500
} while ([DateTime]::UtcNow -lt $deadline)

throw "local-tts-service did not become ready within $StartupTimeoutSeconds seconds. See $stdoutPath and $stderrPath"
