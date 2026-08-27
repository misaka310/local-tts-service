[CmdletBinding()]
param(
  [switch]$ForceSetup,
  [switch]$Check,
  [switch]$PauseOnFailure,
  [switch]$NoOpenBrowser,
  [string]$ReferenceVoicesDir = '',
  [ValidateRange(-1, 86400)]
  [int]$IrodoriIdleTimeoutSeconds = -1,
  [string]$WindowTitle = ''
)

$ErrorActionPreference = 'Stop'

function Exit-LocalTtsLauncher {
  param([Parameter(Mandatory = $true)][int]$Code)
  if ($Code -ne 0 -and $PauseOnFailure) {
    Write-Host ''
    Write-Host '[ERROR] local-tts-service could not start.' -ForegroundColor Red
    [void](Read-Host 'Press Enter to close this window')
  }
  exit $Code
}

trap {
  Write-Error -ErrorAction Continue $_
  Exit-LocalTtsLauncher -Code 1
}

if (-not [string]::IsNullOrWhiteSpace($WindowTitle)) {
  try { $Host.UI.RawUI.WindowTitle = $WindowTitle } catch { }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$resolvedReferenceVoicesDir = ''
if (-not [string]::IsNullOrWhiteSpace($ReferenceVoicesDir)) {
  $resolvedReferenceVoicesDir = [IO.Path]::GetFullPath($ReferenceVoicesDir)
  if (-not [IO.Directory]::Exists($resolvedReferenceVoicesDir)) {
    throw "Reference voices directory was not found: $resolvedReferenceVoicesDir"
  }
  $env:LOCAL_TTS_REFERENCE_VOICES_DIR = $resolvedReferenceVoicesDir
}
if ($IrodoriIdleTimeoutSeconds -ge 0) {
  $env:LOCAL_TTS_IRODORI_IDLE_TIMEOUT_SEC = [string]$IrodoriIdleTimeoutSeconds
}
$configRelativePath = 'config/config.local.json'
$configPath = Join-Path $repoRoot $configRelativePath
$legacyConfigPath = Join-Path $repoRoot 'config.local.json'

if ((Test-Path -LiteralPath $legacyConfigPath -PathType Leaf) -and -not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $configPath) | Out-Null
  Move-Item -LiteralPath $legacyConfigPath -Destination $configPath
  Write-Output 'Moved the legacy root configuration into config/config.local.json.'
}

function Find-FirstFile {
  param([Parameter(Mandatory = $true)][string]$Root, [Parameter(Mandatory = $true)][string]$Filter)
  if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return $null }
  return Get-ChildItem -LiteralPath $Root -Recurse -Filter $Filter -File -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Get-MissingStandardComponents {
  $missing = New-Object System.Collections.Generic.List[string]
  $requiredFiles = @(
    @{ Path = 'config/config.local.json'; Label = 'local configuration' },
    @{ Path = '.venv/Scripts/python.exe'; Label = 'Python environment' },
    @{ Path = 'runtime/tools/node/node.exe'; Label = 'Node.js runtime' },
    @{ Path = 'runtime/venv-demucs/Scripts/python.exe'; Label = 'background-removal environment' },
    @{ Path = 'runtime/venv-irodori/Scripts/python.exe'; Label = 'Irodori runtime' }
  )
  foreach ($item in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $item.Path) -PathType Leaf)) { $missing.Add($item.Label) }
  }
  if (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'frontend/node_modules') -PathType Container)) { $missing.Add('frontend packages') }
  if (-not (Find-FirstFile -Root (Join-Path $repoRoot 'runtime/vendor/ffmpeg') -Filter 'ffmpeg.exe')) { $missing.Add('FFmpeg') }
  if (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'runtime/models/huggingface/Qwen__Qwen3-TTS-12Hz-1.7B-Base') -PathType Container)) { $missing.Add('Qwen3-TTS Voice Clone 1.7B model') }
  if (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'runtime/models/irodori') -PathType Container)) { $missing.Add('Irodori models') }
  return @($missing)
}

if ($Check) {
  & (Join-Path $PSScriptRoot 'check-local-tts.ps1') -ConfigPath $configRelativePath
  Exit-LocalTtsLauncher -Code $LASTEXITCODE
}

$missingComponents = @(Get-MissingStandardComponents)
$needsSetup = $ForceSetup -or $missingComponents.Count -gt 0
$didSetup = $false

if ($needsSetup) {
  Write-Output 'Starting first-time setup or repairing missing components.'
  if ($missingComponents.Count -gt 0) { Write-Output ('Components to prepare: ' + ($missingComponents -join ', ')) }
  Write-Output 'This also prepares FFmpeg, speech recognition, and background removal for video reference voices.'
  Write-Output ''

  & (Join-Path $PSScriptRoot 'setup-local-tts.ps1') `
    -ConfigPath $configRelativePath `
    -DownloadQwenModels `
    -QwenDefaultModelOnly `
    -DownloadFfmpeg `
    -SetupIrodori `
    -SkipVendorSetup `
    -NoGptSovitsStart
  if ($LASTEXITCODE -ne 0) { Exit-LocalTtsLauncher -Code $LASTEXITCODE }
  $didSetup = $true
}

. (Join-Path $PSScriptRoot 'managed-job.ps1')
. (Join-Path $PSScriptRoot 'managed-processes.ps1')

$sessionId = [guid]::NewGuid().ToString('N')
$env:LOCAL_TTS_MANAGED_SESSION_ID = $sessionId
$readyEventName = "LocalTtsReady-$PID-$sessionId"
$readyEvent = [Threading.EventWaitHandle]::new($false, [Threading.EventResetMode]::ManualReset, $readyEventName)
$jobHandle = [IntPtr]::Zero
$stackHost = $null
$ctrlRequested = $false
$exitCode = 0
$logDir = Join-Path $repoRoot 'runtime/logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$lifecycleStatePath = Join-Path $logDir "launcher-$sessionId.json"
$lifecycleState = [ordered]@{
  sessionId = $sessionId
  launcherPid = $PID
  stage = 'initializing'
  lastEvent = 'none'
  jobCreated = $false
  jobClosed = $false
  cleanupExecuted = $false
  updatedAtUtc = [DateTime]::UtcNow.ToString('o')
}

function Save-LifecycleState {
  try {
    $script:lifecycleState.updatedAtUtc = [DateTime]::UtcNow.ToString('o')
    $script:lifecycleState | ConvertTo-Json | Set-Content -LiteralPath $script:lifecycleStatePath -Encoding UTF8
  }
  catch { Write-Warning "could not update lifecycle state: $($_.Exception.Message)" }
}

Save-LifecycleState

try {
  if (-not [LocalTtsJobNative]::InstallCtrlHandler()) {
    throw "failed to install Ctrl+C handler: $([ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error()).Message)"
  }

  $jobHandle = New-LocalTtsManagedJob
  $lifecycleState.jobCreated = $true
  $lifecycleState.stage = 'starting-stack'
  Save-LifecycleState
  Write-Output 'Starting the prepared environment.'
  Write-Host "[INFO] launch session: $sessionId"
  $stackHost = Start-LocalTtsManagedStackHost `
    -JobHandle $jobHandle `
    -ScriptPath (Join-Path $PSScriptRoot 'run-local-tts-stack.ps1') `
    -ConfigPath $configPath `
    -ReadyEventName $readyEventName `
    -WorkingDirectory $repoRoot `
    -NoGptSovitsStart:$didSetup

  while (-not $readyEvent.WaitOne(200)) {
    if ([LocalTtsJobNative]::WaitForCtrl(0)) { $ctrlRequested = $true; break }
    if ([LocalTtsJobNative]::WaitForSingleObject($stackHost.ProcessHandle, 0) -eq [LocalTtsJobNative]::WAIT_OBJECT_0) {
      $code = Get-LocalTtsManagedProcessExitCode -ProcessHandle $stackHost.ProcessHandle
      throw "managed stack host exited during startup (exit code $code)"
    }
  }

  if (-not $ctrlRequested) {
    $lifecycleState.stage = 'opening-frontend'
    Save-LifecycleState
    & (Join-Path $PSScriptRoot 'start-tts-frontend.ps1') -ConfigPath $configPath -OpenBrowser:(-not $NoOpenBrowser) -NoInstall
    Write-Host ''
    Write-Host '========== local-tts-service is running =========='
    Write-Host 'This terminal owns the backend and frontend.'
    Write-Host 'Press Ctrl+C or close this window to stop all services started by this launch.'
    Write-Host 'Logs: runtime/logs'
    Write-Host '=================================================='
    $lifecycleState.stage = 'running'
    Save-LifecycleState

    while (-not [LocalTtsJobNative]::WaitForCtrl(250)) {
      if ([LocalTtsJobNative]::WaitForSingleObject($stackHost.ProcessHandle, 0) -eq [LocalTtsJobNative]::WAIT_OBJECT_0) {
        $code = Get-LocalTtsManagedProcessExitCode -ProcessHandle $stackHost.ProcessHandle
        throw "managed stack host exited unexpectedly (exit code $code)"
      }
    }
    $ctrlRequested = $true
  }
}
catch {
  Write-Error -ErrorAction Continue $_
  $exitCode = 1
}
finally {
  if ($ctrlRequested) {
    $ctrlType = [LocalTtsJobNative]::GetLastCtrlType()
    $lifecycleState.lastEvent = switch ($ctrlType) { 0 { 'CtrlC' } 1 { 'CtrlBreak' } 2 { 'ConsoleClose' } default { "ConsoleEvent-$ctrlType" } }
    $lifecycleState.stage = 'stopping'
    Save-LifecycleState
    Write-Host ''
    Write-Host '[STOPPING] terminal shutdown requested; asking the managed stack to stop...'
    if ($stackHost) {
      $null = [LocalTtsJobNative]::GenerateConsoleCtrlEvent(1, [uint32]$stackHost.ProcessId)
      $null = [LocalTtsJobNative]::WaitForSingleObject($stackHost.ProcessHandle, 3000)
    }
  }

  if ($jobHandle -ne [IntPtr]::Zero) {
    Close-LocalTtsManagedJob -JobHandle $jobHandle
    $lifecycleState.jobClosed = $true
    $lifecycleState.stage = 'job-closed'
    Save-LifecycleState
  }
  if ($stackHost -and $stackHost.ProcessHandle -ne [IntPtr]::Zero) { $null = [LocalTtsJobNative]::CloseHandle($stackHost.ProcessHandle) }

  try {
    $result = Stop-ManagedProcesses -RepoRoot $repoRoot -SessionId $sessionId
    Write-Host "[INFO] session cleanup: stopped=$($result.Stopped) stale=$($result.Stale) skipped=$($result.Skipped) failed=$($result.Failed)"
    if ($result.Failed -gt 0) { $exitCode = 1 }
  }
  catch {
    Write-Warning "session cleanup failed: $($_.Exception.Message)"
    $exitCode = 1
  }

  $lifecycleState.cleanupExecuted = $true
  $lifecycleState.stage = if ($exitCode -eq 0) { 'stopped' } else { 'failed' }
  Save-LifecycleState
  [LocalTtsJobNative]::RemoveCtrlHandler()
  $readyEvent.Dispose()
  Remove-Item Env:LOCAL_TTS_MANAGED_SESSION_ID -ErrorAction SilentlyContinue
  if ($ctrlRequested -and $exitCode -eq 0) { Write-Host '[DONE] local-tts-service stopped.' }
}

Exit-LocalTtsLauncher -Code $exitCode
