[CmdletBinding()]
param([string]$ConfigPath = '')

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ConfigPath)) { $ConfigPath = Join-Path $repo 'config\rvc-persistent.local.json' }
$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$python = [string]$config.rvcPythonPath
$service = Join-Path $repo 'scripts\persistent_rvc_service.py'
$storagePreflight = Join-Path $repo 'scripts\rvc_storage_preflight.py'
$launcher = 'C:\00_dev\74_windows-gui-ci-runner\scripts\host\Start-NoWindowDetached.ps1'
$stopService = Join-Path $repo 'scripts\stop-persistent-rvc-service.ps1'
$stateRoot = Join-Path $repo 'runtime\persistent-rvc'
$logRoot = Join-Path $stateRoot 'logs'
$detachState = Join-Path $stateRoot 'detached.json'
$stdout = Join-Path $logRoot 'service.stdout.log'
$stderrPath = Join-Path $logRoot 'service.stderr.log'
$healthUrl = "http://$([string]$config.host):$([int]$config.port)/health"
$upstreamHealthUrl = ([string]$config.upstreamBaseUrl).TrimEnd('/') + [string]$config.upstreamHealthPath
$upstreamStartScript = [string]$config.upstreamStartScript

foreach ($path in @($ConfigPath, $python, $service, $storagePreflight, $launcher, $stopService, $upstreamStartScript)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required persistent RVC component not found: $path" }
}

$preflightInfo = New-Object System.Diagnostics.ProcessStartInfo
$preflightInfo.FileName = $python
$preflightInfo.Arguments = "-X utf8 `"$storagePreflight`" --config `"$ConfigPath`" --json"
$preflightInfo.WorkingDirectory = $repo
$preflightInfo.UseShellExecute = $false
$preflightInfo.CreateNoWindow = $true
$preflightInfo.RedirectStandardOutput = $true
$preflightInfo.RedirectStandardError = $true
$preflightInfo.StandardOutputEncoding = [Text.Encoding]::UTF8
$preflightInfo.StandardErrorEncoding = [Text.Encoding]::UTF8
$preflightProcess = New-Object System.Diagnostics.Process
$preflightProcess.StartInfo = $preflightInfo
$null = $preflightProcess.Start()
$preflightStdout = $preflightProcess.StandardOutput.ReadToEnd()
$preflightStderr = $preflightProcess.StandardError.ReadToEnd()
$preflightProcess.WaitForExit()
$preflightExitCode = $preflightProcess.ExitCode
$preflightProcess.Dispose()
$preflightText = [string](($preflightStdout -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) | Select-Object -Last 1)
$preflight = $null
try { $preflight = $preflightText | ConvertFrom-Json } catch { }
if ($preflightExitCode -ne 0 -or $null -eq $preflight -or -not [bool]$preflight.ok) {
    $message = if ($null -ne $preflight -and -not [string]::IsNullOrWhiteSpace([string]$preflight.message)) {
        [string]$preflight.message
    } elseif (-not [string]::IsNullOrWhiteSpace($preflightStderr)) {
        "RVC storage preflight failed: $($preflightStderr.Trim())"
    } else {
        "RVC storage preflight failed: $preflightText"
    }
    throw $message
}
if (-not (Test-Path -LiteralPath ([string]$config.rvcCwd) -PathType Container)) { throw "Required RVC working directory not found: $($config.rvcCwd)" }

function Test-UpstreamReady {
    try {
        $health = Invoke-RestMethod -Uri $upstreamHealthUrl -TimeoutSec 5
        return ([bool]$health.ok) -and ([string]$health.status -eq 'healthy') -and (@($health.availableModels) -contains [string]$config.defaultModel)
    } catch { return $false }
}
if (-not (Test-UpstreamReady)) {
    & $upstreamStartScript -NoOpenBrowser | Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds([int]$config.upstreamStartupTimeoutSeconds)
    do { Start-Sleep -Milliseconds 500 } while (-not (Test-UpstreamReady) -and [DateTime]::UtcNow -lt $deadline)
    if (-not (Test-UpstreamReady)) { throw "Local TTS Service did not become healthy at $upstreamHealthUrl" }
}

try {
    $existing = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
    if ([bool]$existing.ok -and [string]$existing.voiceRuntime.modelId -eq [string]$config.rvcModelId) {
        [pscustomobject]@{ status='already_ready'; health=$existing } | ConvertTo-Json -Depth 15 -Compress
        return
    }
    & $stopService -ConfigPath $ConfigPath | Out-Null
} catch { }

New-Item -ItemType Directory -Force -Path $stateRoot, $logRoot | Out-Null
function Quote-NativeArgument {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    return '"' + $Value.Replace('"', '\"') + '"'
}
$argumentText = (@($service, '--config', $ConfigPath) | ForEach-Object { Quote-NativeArgument ([string]$_) }) -join ' '
$launchJson = & $launcher -FilePath $python -Arguments $argumentText -WorkingDirectory $repo -StatePath $detachState -StdoutPath $stdout -StderrPath $stderrPath -StartupTimeoutSeconds 15
$launch = $launchJson | Select-Object -Last 1 | ConvertFrom-Json
if (-not [bool]$launch.started) { throw "Persistent RVC service did not detach. See $stderrPath" }
$deadline = [DateTime]::UtcNow.AddSeconds([int]$config.startupTimeoutSeconds)
do {
    Start-Sleep -Milliseconds 300
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
        if ([bool]$health.ok) {
            [pscustomobject]@{ status='ready'; launchId=$launch.launchId; processId=$launch.childProcessId; healthUrl=$healthUrl; health=$health } | ConvertTo-Json -Depth 18 -Compress
            return
        }
    } catch { }
    if (Test-Path -LiteralPath $detachState -PathType Leaf) {
        try {
            $state = Get-Content -LiteralPath $detachState -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([string]$state.status -eq 'failed') { throw "Persistent RVC service exited during startup. See $stderrPath" }
        } catch [System.Management.Automation.RuntimeException] { throw } catch { }
    }
} while ([DateTime]::UtcNow -lt $deadline)
throw "Persistent RVC service did not become healthy. See $stderrPath"
