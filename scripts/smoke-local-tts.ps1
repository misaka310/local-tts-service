param(
    [string]$BaseUrl = "http://127.0.0.1:8730",
    [string]$Text = "smoke test from local-tts-service"
)

$ErrorActionPreference = "Stop"

Write-Host "[1/3] GET /health"
$health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/health"
if (-not $health.ok) {
    throw "/health failed"
}
$health | ConvertTo-Json -Depth 5 | Write-Host

Write-Host "[2/3] POST /v1/speak (mock_wav)"
$reqBody = @{
    text = $Text
    model = "mock"
    requestId = "smoke"
    format = "wav"
} | ConvertTo-Json

$speak = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/speak" -ContentType "application/json" -Body $reqBody
if (-not $speak.ok) {
    throw "/v1/speak failed"
}
$speak | ConvertTo-Json -Depth 5 | Write-Host

Write-Host "[3/3] GET generated audio"
$tempPath = Join-Path $env:TEMP ("local-tts-smoke-" + [guid]::NewGuid().ToString() + ".wav")
Invoke-WebRequest -Method Get -Uri $speak.audioUrl -OutFile $tempPath -UseBasicParsing

if (-not (Test-Path $tempPath)) {
    throw "audio fetch failed: temp file not created"
}
if ((Get-Item $tempPath).Length -le 0) {
    throw "audio fetch failed: empty file"
}
Remove-Item $tempPath -Force

Write-Host "smoke success"
