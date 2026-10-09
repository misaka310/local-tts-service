param(
    [string]$BaseUrl = "http://127.0.0.1:8730",
    [string]$OutputPath = "runtime/audio/verification/irodori-v4-small-smoke.wav"
)

$ErrorActionPreference = "Stop"
$modelName = "irodori_v4_small"

function Fail-Step {
    param([string]$Step, [string]$Message)
    throw "[$Step] $Message"
}

function ConvertFrom-Utf8Base64 {
    param([Parameter(Mandatory = $true)][string]$Value)
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Value))
}

$health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/health" -TimeoutSec 5
if (-not $health.ok) { Fail-Step "health" "/health returned ok=false" }

$models = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/models?probe=false" -TimeoutSec 30
$model = $models.models | Where-Object { $_.model -eq $modelName } | Select-Object -First 1
if ($null -eq $model) { Fail-Step "models" "$modelName is not registered" }
if (-not [bool]$model.available) { Fail-Step "models" "$modelName is unavailable: $($model.unavailableReason)" }
if ([string]$model.runtime -ne "irodori_voicedesign_direct") {
    Fail-Step "models" "$modelName must use irodori_voicedesign_direct, actual=$($model.runtime)"
}

$requestId = "irodori-v4-small-smoke-$([guid]::NewGuid().ToString('N'))"
$text = ConvertFrom-Utf8Base64 "SXJvZG9yaSB2NCBTbWFsbCDjga7pn7Plo7DnlJ/miJDjg4bjgrnjg4jjgafjgZnjgILoh6rnhLbjgafogZ7jgY3lj5bjgorjgoTjgZnjgY/oqq3jgb/kuIrjgZLjgb7jgZnjgII="
$instruction = ConvertFrom-Utf8Base64 "5piO44KL44GP6Ieq54S244Gq5pel5pys6Kqe44Gn44CB6JC944Gh552A44GE44Gf6YCf44GV44Gn6Kqt44G/5LiK44GS44Gm44GP44Gg44GV44GE44CC"
$payload = @{
    text = $text
    model = $modelName
    requestId = $requestId
    instruction = $instruction
    styleStrength = 3.5
    seed = 20260802
    format = "wav"
} | ConvertTo-Json -Compress

$speak = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/speak" -ContentType "application/json; charset=utf-8" -Body $payload -TimeoutSec 1800
if (-not $speak.ok) { Fail-Step "speak" "/v1/speak returned ok=false" }
if ([string]$speak.model -ne $modelName) { Fail-Step "speak" "unexpected model in response: $($speak.model)" }
if ([string]$speak.runtime -ne "irodori_voicedesign_direct") { Fail-Step "speak" "unexpected runtime in response: $($speak.runtime)" }
if ([string]$speak.requestId -ne $requestId) { Fail-Step "speak" "request id mismatch: $($speak.requestId)" }

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$resolvedOutput = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputPath))
$parent = Split-Path -Parent $resolvedOutput
New-Item -ItemType Directory -Force -Path $parent | Out-Null
if (Test-Path -LiteralPath $resolvedOutput -PathType Leaf) {
    Remove-Item -LiteralPath $resolvedOutput -Force
}
$audioUri = if ([System.Uri]::IsWellFormedUriString([string]$speak.audioUrl, [System.UriKind]::Absolute)) {
    [string]$speak.audioUrl
} else {
    ([System.Uri]::new([System.Uri]$BaseUrl, [string]$speak.audioUrl)).AbsoluteUri
}
Invoke-WebRequest -Method Get -Uri $audioUri -OutFile $resolvedOutput -UseBasicParsing -TimeoutSec 60

$bytes = [System.IO.File]::ReadAllBytes($resolvedOutput)
if ($bytes.Length -lt 44) { Fail-Step "audio" "generated WAV is too small" }
$riff = [System.Text.Encoding]::ASCII.GetString($bytes[0..3])
$wave = [System.Text.Encoding]::ASCII.GetString($bytes[8..11])
if ($riff -ne "RIFF" -or $wave -ne "WAVE") { Fail-Step "audio" "invalid WAV header: $riff/$wave" }

$irodoriPython = Join-Path $repoRoot 'runtime/venv-irodori/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $irodoriPython -PathType Leaf)) {
    Fail-Step "audio" "Irodori Python runtime is missing: $irodoriPython"
}
$inspectorPath = Join-Path ([System.IO.Path]::GetTempPath()) ("local-tts-audio-inspect-$([guid]::NewGuid().ToString('N')).py")
$inspectorSource = @'
import json
import math
import sys

import numpy as np
import soundfile as sf

audio, sample_rate = sf.read(sys.argv[1], dtype="float32", always_2d=True)
frames = int(audio.shape[0])
channels = int(audio.shape[1])
duration_sec = frames / float(sample_rate) if sample_rate else 0.0
peak = float(np.max(np.abs(audio))) if audio.size else 0.0
rms = float(math.sqrt(float(np.mean(np.square(audio))))) if audio.size else 0.0
print(json.dumps({
    "sampleRate": int(sample_rate),
    "channels": channels,
    "frames": frames,
    "durationSec": duration_sec,
    "peak": peak,
    "rms": rms,
}))
'@
$inspectOutPath = [System.IO.Path]::GetTempFileName()
$inspectErrPath = [System.IO.Path]::GetTempFileName()
try {
    [System.IO.File]::WriteAllText($inspectorPath, $inspectorSource, [System.Text.UTF8Encoding]::new($false))
    $inspectProcess = Start-Process -FilePath $irodoriPython -ArgumentList @($inspectorPath, $resolvedOutput) -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput $inspectOutPath -RedirectStandardError $inspectErrPath -Wait -PassThru
    $inspectionText = if (Test-Path -LiteralPath $inspectOutPath) { [System.IO.File]::ReadAllText($inspectOutPath, [System.Text.Encoding]::UTF8) } else { "" }
    $inspectionError = if (Test-Path -LiteralPath $inspectErrPath) { [System.IO.File]::ReadAllText($inspectErrPath, [System.Text.Encoding]::UTF8) } else { "" }
    $inspectionText = ([string]$inspectionText).Trim()
    $inspectionError = ([string]$inspectionError).Trim()
    if ($inspectProcess.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($inspectionText)) {
        Fail-Step "audio" "audio inspection failed: exit=$($inspectProcess.ExitCode) stderr=$inspectionError"
    }
    $inspection = $inspectionText | ConvertFrom-Json
} finally {
    Remove-Item -LiteralPath $inspectorPath, $inspectOutPath, $inspectErrPath -Force -ErrorAction SilentlyContinue
}

if ([int]$inspection.sampleRate -ne 48000) { Fail-Step "audio" "unexpected sample rate: $($inspection.sampleRate)" }
if ([int]$inspection.channels -lt 1) { Fail-Step "audio" "generated WAV has no channels" }
if ([double]$inspection.durationSec -lt 0.5) { Fail-Step "audio" "generated WAV is too short: $($inspection.durationSec)s" }
if ([double]$inspection.rms -lt 0.0001) { Fail-Step "audio" "generated WAV is effectively silent: rms=$($inspection.rms)" }
if ([double]$inspection.peak -gt 1.05) { Fail-Step "audio" "generated WAV exceeds expected peak range: peak=$($inspection.peak)" }

Write-Host "[OK] $modelName direct-runtime smoke passed" -ForegroundColor Green
Write-Host "requestId=$requestId"
Write-Host "runtime=$($speak.runtime)"
Write-Host "audio=$resolvedOutput"
Write-Host "bytes=$($bytes.Length)"
Write-Host ("durationSec={0:N3}" -f [double]$inspection.durationSec)
Write-Host "sampleRate=$($inspection.sampleRate)"
Write-Host "channels=$($inspection.channels)"
Write-Host ("rms={0:N6}" -f [double]$inspection.rms)
