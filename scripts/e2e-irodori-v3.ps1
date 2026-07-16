param(
    [string]$BaseUrl = "http://127.0.0.1:8730",
    [string]$VoiceId = "default"
)

$ErrorActionPreference = "Stop"

$requestId = "e2e-irodori-v3"
$payload = @{
    text = "irodori v3 e2e"
    model = "irodori_v3"
    voiceId = $VoiceId
    requestId = $requestId
    format = "wav"
} | ConvertTo-Json

Write-Host "[1/3] POST /v1/speak (irodori_v3 / voiceId=$VoiceId)"
$speak = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/speak" -ContentType "application/json" -Body $payload
if (-not $speak.ok) { throw "speak failed" }

Write-Host "[2/3] GET generated audio"
$audio = Invoke-WebRequest -Uri $speak.audioUrl -OutFile (Join-Path $env:TEMP ("e2e-irodori-v3-" + [guid]::NewGuid().ToString() + ".wav"))
if ($audio.StatusCode -lt 200 -or $audio.StatusCode -ge 300) { throw "audio fetch failed" }

Write-Host "[3/3] OK"
