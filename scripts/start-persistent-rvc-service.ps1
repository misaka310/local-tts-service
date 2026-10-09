[CmdletBinding()]
param([string]$ConfigPath = '')

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ConfigPath)) { $ConfigPath = Join-Path $repo 'config\rvc-persistent.local.json' }
$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
function Assert-LoopbackHost {
    param([Parameter(Mandatory = $true)][string]$EndpointHost)
    if ($EndpointHost.Trim().ToLowerInvariant() -eq 'localhost') { return }
    $address = $null
    if (-not [Net.IPAddress]::TryParse($EndpointHost, [ref]$address) -or -not [Net.IPAddress]::IsLoopback($address)) {
        throw "Persistent RVC endpoints must use loopback addresses: $EndpointHost"
    }
}
function Assert-LoopbackUri {
    param([Parameter(Mandatory = $true)][string]$Value)
    $uri = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -notin @('http', 'https')) {
        throw "Persistent RVC upstreamBaseUrl must be an absolute HTTP(S) URL: $Value"
    }
    Assert-LoopbackHost -EndpointHost $uri.Host
}
Assert-LoopbackHost -EndpointHost ([string]$config.host)
Assert-LoopbackUri -Value ([string]$config.upstreamBaseUrl)
$python = [string]$config.rvcPythonPath
$service = Join-Path $repo 'scripts\persistent_rvc_service.py'
$storagePreflight = Join-Path $repo 'scripts\rvc_storage_preflight.py'
$detachedHelper = Join-Path $repo 'scripts\start_detached_process.py'
$stopService = Join-Path $repo 'scripts\stop-persistent-rvc-service.ps1'
$stateRoot = Join-Path $repo 'runtime\persistent-rvc'
$logRoot = Join-Path $stateRoot 'logs'
$stdout = Join-Path $logRoot 'service.stdout.log'
$stderrPath = Join-Path $logRoot 'service.stderr.log'
$healthUrl = "http://$([string]$config.host):$([int]$config.port)/health"
$upstreamHealthUrl = ([string]$config.upstreamBaseUrl).TrimEnd('/') + [string]$config.upstreamHealthPath
$upstreamStartScript = [string]$config.upstreamStartScript

foreach ($path in @($ConfigPath, $python, $service, $storagePreflight, $detachedHelper, $stopService)) {
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
    if ([string]::IsNullOrWhiteSpace($upstreamStartScript) -or -not (Test-Path -LiteralPath $upstreamStartScript -PathType Leaf)) {
        throw "Local TTS Service is not ready and upstreamStartScript was not found: $upstreamStartScript"
    }
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
$launchJson = & $python -X utf8 $detachedHelper --file $python --working-directory $repo --stdout $stdout --stderr $stderrPath $service --config $ConfigPath
if ($LASTEXITCODE -ne 0) { throw "Persistent RVC service did not detach. See $stderrPath" }
$launch = $launchJson | Select-Object -Last 1 | ConvertFrom-Json
if (-not [bool]$launch.started) { throw "Persistent RVC service did not detach. See $stderrPath" }
$childProcessId = [int]$launch.childProcessId
$deadline = [DateTime]::UtcNow.AddSeconds([int]$config.startupTimeoutSeconds)
do {
    Start-Sleep -Milliseconds 300
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
        if ([bool]$health.ok) {
            [pscustomobject]@{ status='ready'; launchId=$launch.launchId; processId=$childProcessId; healthUrl=$healthUrl; health=$health } | ConvertTo-Json -Depth 18 -Compress
            return
        }
    } catch { }
    if ($null -eq (Get-Process -Id $childProcessId -ErrorAction SilentlyContinue)) {
        $detail = if (Test-Path -LiteralPath $stderrPath -PathType Leaf) { (Get-Content -LiteralPath $stderrPath -Tail 20 -ErrorAction SilentlyContinue) -join "`n" } else { '' }
        throw "Persistent RVC service exited during startup. $detail"
    }
} while ([DateTime]::UtcNow -lt $deadline)
throw "Persistent RVC service did not become healthy. See $stderrPath"
