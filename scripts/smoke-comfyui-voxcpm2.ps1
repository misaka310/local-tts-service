param(
    [string]$BaseUrl = "http://127.0.0.1:8730",
    [string]$ConfigPath = "config/config.local.json",
    [string]$Model = "voxcpm2_tts"
)

$ErrorActionPreference = "Stop"

function Fail-Step {
    param([string]$Step, [string]$Message)
    Write-Host "[FAIL][$Step] $Message" -ForegroundColor Red
    exit 1
}

function Resolve-RepoPath {
    param([string]$RepoRoot, [string]$RawPath)
    if ([string]::IsNullOrWhiteSpace($RawPath)) { return "" }
    if ([System.IO.Path]::IsPathRooted($RawPath)) { return $RawPath }
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $RawPath))
}

function Parse-ErrorMessage {
    param([System.Management.Automation.ErrorRecord]$ErrRecord)
    $message = $ErrRecord.Exception.Message
    if ($ErrRecord.ErrorDetails -and $ErrRecord.ErrorDetails.Message) {
        $message = "$message | $($ErrRecord.ErrorDetails.Message)"
    }
    return $message
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

Write-Host "[0/8] GET /health"
try {
    $health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/health"
} catch {
    Fail-Step "local-tts-service" "service is not running or not reachable at $BaseUrl"
}
if (-not $health.ok) { Fail-Step "local-tts-service" "/health returned ok=false" }
if (-not ($health.availableProviders -contains "comfyui_voxcpm2")) {
    Fail-Step "health" "availableProviders does not include comfyui_voxcpm2"
}

$configAbs = Resolve-RepoPath -RepoRoot $repoRoot -RawPath $ConfigPath
if (-not (Test-Path $configAbs -PathType Leaf)) {
    Fail-Step "config" "config file not found: $configAbs"
}
$config = Get-Content -Path $configAbs -Raw | ConvertFrom-Json

$modelCfg = $config.models.$Model
if (-not $modelCfg) { Fail-Step "config" "models.$Model is missing" }
if ([string]$modelCfg.runtime -ne "comfyui_voxcpm2") {
    Fail-Step "config" "models.$Model.runtime must be comfyui_voxcpm2"
}

$workflowPath = Resolve-RepoPath -RepoRoot $repoRoot -RawPath ([string]$modelCfg.workflowPath)
if (-not (Test-Path $workflowPath -PathType Leaf)) { Fail-Step "workflowPath" "workflowPath not found: $workflowPath" }

if ([bool]$modelCfg.requiresReferenceAudio) {
    $referenceAudioPath = Resolve-RepoPath -RepoRoot $repoRoot -RawPath ([string]$modelCfg.referenceAudioPath)
    $referenceTextPath = Resolve-RepoPath -RepoRoot $repoRoot -RawPath ([string]$modelCfg.referenceTextPath)
    if (-not (Test-Path $referenceAudioPath -PathType Leaf)) { Fail-Step "referenceAudioPath" "referenceAudioPath not found: $referenceAudioPath" }
    if (-not (Test-Path $referenceTextPath -PathType Leaf)) { Fail-Step "referenceTextPath" "referenceTextPath not found: $referenceTextPath" }
}

$voxcpm2 = $config.runtimes.comfyui_voxcpm2
if (-not $voxcpm2) { Fail-Step "config" "runtimes.comfyui_voxcpm2 is missing" }
$inputDir = Resolve-RepoPath -RepoRoot $repoRoot -RawPath ([string]$voxcpm2.inputDir)
$outputDir = Resolve-RepoPath -RepoRoot $repoRoot -RawPath ([string]$voxcpm2.outputDir)
if (-not (Test-Path $inputDir -PathType Container)) { Fail-Step "ComfyUI inputDir" "ComfyUI inputDir not found: $inputDir" }
if (-not (Test-Path $outputDir -PathType Container)) { Fail-Step "ComfyUI outputDir" "ComfyUI outputDir not found: $outputDir" }

$comfyBase = [string]$voxcpm2.baseUrl
if ([string]::IsNullOrWhiteSpace($comfyBase)) { $comfyBase = "http://127.0.0.1:8288" }
Write-Host "[1/8] check ComfyUI: $comfyBase"
try {
    Invoke-RestMethod -Method Get -Uri "$comfyBase/system_stats" | Out-Null
} catch {
    Fail-Step "ComfyUI" "cannot connect to ComfyUI: $comfyBase"
}

Write-Host "[2/8] GET /v1/voices"
$voices = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/voices"
if (-not $voices.ok) { Fail-Step "voices" "/v1/voices returned ok=false" }
$voice = $voices.voices | Where-Object { $_.voice -eq $Model }
if (-not $voice) { Fail-Step "voices" "$Model not found in /v1/voices" }
if ([string]$voice.provider -ne "comfyui_voxcpm2") {
    Fail-Step "voices" "provider mismatch for ${Model}: $($voice.provider)"
}

Write-Host "[3/8] POST /v1/speak (model=$Model)"
$payload = @{
    text = "Hello from VoxCPM2 smoke test."
    model = $Model
    engine = "comfyui_voxcpm2"
    requestId = "voxcpm2-smoke"
    format = "wav"
} | ConvertTo-Json

try {
    $speak = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/speak" -ContentType "application/json" -Body $payload
} catch {
    $errorText = Parse-ErrorMessage -ErrRecord $_
    if ($errorText -match "cannot connect to http://|cannot connect to https://") { Fail-Step "ComfyUI" $errorText }
    if ($errorText -match "workflowPath not found") { Fail-Step "workflowPath" $errorText }
    if ($errorText -match "referenceAudioPath not found") { Fail-Step "referenceAudioPath" $errorText }
    if ($errorText -match "referenceTextPath not found") { Fail-Step "referenceTextPath" $errorText }
    if ($errorText -match "VoxCPM2 workflow text patch target was not found") { Fail-Step "workflow text target" $errorText }
    if ($errorText -match "SaveAudio-compatible node") { Fail-Step "workflow save node" $errorText }
    if ($errorText -match "ComfyUI history error") { Fail-Step "ComfyUI /history" $errorText }
    if ($errorText -match "HTTP\s+\d+\s+from\s+.+/prompt") { Fail-Step "ComfyUI /prompt" $errorText }
    Fail-Step "speak" $errorText
}
if (-not $speak.ok) { Fail-Step "speak" "/v1/speak returned ok=false" }

Write-Host "[4/8] validate audioPath and size"
$audioPath = [string]$speak.audioPath
if (-not (Test-Path $audioPath -PathType Leaf)) { Fail-Step "audioPath" "audioPath not found: $audioPath" }
$localSize = (Get-Item $audioPath).Length
if ($localSize -le 44) { Fail-Step "audioPath" "generated file is too small (${localSize} bytes)" }

Write-Host "[5/8] validate WAV header and non-silent bytes"
$bytes = [System.IO.File]::ReadAllBytes($audioPath)
if ($bytes.Length -le 44) { Fail-Step "wav header" "file is too small for WAV content" }
$riff = [System.Text.Encoding]::ASCII.GetString($bytes[0..3])
$wave = [System.Text.Encoding]::ASCII.GetString($bytes[8..11])
if ($riff -ne "RIFF" -or $wave -ne "WAVE") { Fail-Step "wav header" "invalid WAV header (RIFF=$riff, WAVE=$wave)" }
$nonSilent = $false
for ($i = 44; $i -lt $bytes.Length; $i++) {
    if ($bytes[$i] -ne 0) {
        $nonSilent = $true
        break
    }
}
if (-not $nonSilent) { Fail-Step "audio content" "all sampled bytes are zero (appears silent)" }

Write-Host "[6/8] GET /audio/{filename}"
$audioName = Split-Path -Path $audioPath -Leaf
$downloadPath = Join-Path $env:TEMP ("voxcpm2-smoke-" + [guid]::NewGuid().ToString() + ".wav")
Invoke-WebRequest -Method Get -Uri "$BaseUrl/audio/$audioName" -OutFile $downloadPath -UseBasicParsing
if (-not (Test-Path $downloadPath -PathType Leaf)) { Fail-Step "audio endpoint" "downloaded file was not created" }
$downloadSize = (Get-Item $downloadPath).Length
if ($downloadSize -le 44) { Fail-Step "audio endpoint" "downloaded file is too small (${downloadSize} bytes)" }

Write-Host "[7/8] success" -ForegroundColor Green
Write-Host "audioPath: $audioPath"
Write-Host "audioUrl : $($speak.audioUrl)"
Remove-Item $downloadPath -Force -ErrorAction SilentlyContinue
