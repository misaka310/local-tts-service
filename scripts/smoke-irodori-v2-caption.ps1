param(
    [string]$BaseUrl = "http://127.0.0.1:8730",
    [string]$ConfigPath = "config/config.local.json"
)

$ErrorActionPreference = "Stop"
$modelName = "irodori_v3_voicedesign"
$tempPath = $null

function Fail-Step {
    param([string]$Step, [string]$Message)
    throw "[$Step] $Message"
}

try {
    $health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/health" -TimeoutSec 5
    if (-not $health.ok) { Fail-Step "health" "/health returned ok=false" }

    $models = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/models?probe=false" -TimeoutSec 30
    $model = $models.models | Where-Object { $_.model -eq $modelName } | Select-Object -First 1
    if ($null -eq $model) { Fail-Step "models" "$modelName is not registered" }
    if (-not [bool]$model.available) { Fail-Step "models" "$modelName is unavailable: $($model.unavailableReason)" }
    if ([string]$model.runtime -ne "irodori_voicedesign_direct") {
        Fail-Step "models" "$modelName must use irodori_voicedesign_direct, actual=$($model.runtime)"
    }
    if (-not [bool]$model.supportsCaption) { Fail-Step "models" "$modelName does not support caption" }

    $payload = @{
        text = "Good evening. Tonight we will calmly explore the history of old clocks."
        model = $modelName
        caption = "Use a calm gentle female voice with natural delivery."
        requestId = "irodori-voicedesign-caption-smoke"
        format = "wav"
    } | ConvertTo-Json
    $speak = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/speak" -ContentType "application/json" -Body $payload
    if (-not $speak.ok) { Fail-Step "speak" "/v1/speak returned ok=false" }

    $tempPath = Join-Path $env:TEMP ("irodori-voicedesign-caption-smoke-" + [guid]::NewGuid().ToString() + ".wav")
    Invoke-WebRequest -Method Get -Uri $speak.audioUrl -OutFile $tempPath -UseBasicParsing
    $bytes = [System.IO.File]::ReadAllBytes($tempPath)
    if ($bytes.Length -lt 12) { Fail-Step "audio" "generated WAV is too small" }
    $riff = [System.Text.Encoding]::ASCII.GetString($bytes[0..3])
    $wave = [System.Text.Encoding]::ASCII.GetString($bytes[8..11])
    if ($riff -ne "RIFF" -or $wave -ne "WAVE") { Fail-Step "audio" "invalid WAV header: $riff/$wave" }

    Write-Host "[OK] $modelName caption smoke passed ($($bytes.Length) bytes)" -ForegroundColor Green
}
finally {
    if ($tempPath -and (Test-Path -LiteralPath $tempPath)) { Remove-Item -LiteralPath $tempPath -Force }
}
