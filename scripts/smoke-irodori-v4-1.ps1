[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8730",
    [string]$OutputDirectory = "runtime/clean-install-verification/irodori-v4-1"
)

$ErrorActionPreference = "Stop"

function Fail-Step {
    param([string]$Step, [string]$Message)
    throw "[$Step] $Message"
}

function ConvertFrom-Utf8Base64 {
    param([Parameter(Mandatory = $true)][string]$Value)
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Value))
}

$modelSpecs = @(
    [ordered]@{
        Name = "irodori_v4_1_small"
        FileName = "irodori-v4.1-small.wav"
        Seed = 202609071
        TextBase64 = "SXJvZG9yaSB2NC4xIFNtYWxsIOOBruWun+eUn+aIkOeiuuiqjeOBp+OBmeOAguiHqueEtuOBquaXpeacrOiqnuOBp+iqreOBv+S4iuOBkuOBpuOBj+OBoOOBleOBhOOAgg=="
        InstructionBase64 = "5piO44KL44GP6Ieq54S244Gq5pel5pys6Kqe44Gn44CB6JC944Gh552A44GE44Gf6YCf44GV44Gn6Kqt44G/5LiK44GS44Gm44GP44Gg44GV44GE44CC"
    },
    [ordered]@{
        Name = "irodori_v4_1_anime"
        FileName = "irodori-v4.1-anime.wav"
        Seed = 202609072
        TextBase64 = "SXJvZG9yaSB2NC4xIEFuaW1lIOOBruWun+eUn+aIkOeiuuiqjeOBp+OBmeOAguaYjuOCi+OBhOOCouODi+ODoeiqv+OBp+iqreOBv+S4iuOBkuOBpuOBj+OBoOOBleOBhOOAgg=="
        InstructionBase64 = "44Ki44OL44Oh44Gu6Iul44GE5aWz5oCn44Kt44Oj44Op44Kv44K/44O844Gu44KI44GG44Gr44CB5piO44KL44GP6Ieq54S244Gr6Kqt44G/5LiK44GS44Gm44GP44Gg44GV44GE44CC"
    }
)

$health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/health" -TimeoutSec 10
if (-not $health.ok) { Fail-Step "health" "/health returned ok=false" }

$models = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/models?probe=false" -TimeoutSec 30
foreach ($spec in $modelSpecs) {
    $modelName = [string]$spec.Name
    $model = @($models.models) | Where-Object { $_.model -eq $modelName -or $_.id -eq $modelName } | Select-Object -First 1
    if ($null -eq $model) { Fail-Step "models" "$modelName is not registered" }
    if (-not [bool]$model.available) { Fail-Step "models" "$modelName is unavailable: $($model.unavailableReason)" }
    if ([string]$model.runtime -ne "irodori_voicedesign_direct") {
        Fail-Step "models" "$modelName must use irodori_voicedesign_direct, actual=$($model.runtime)"
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$outputRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDirectory))
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

$irodoriPython = Join-Path $repoRoot 'runtime/venv-irodori/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $irodoriPython -PathType Leaf)) {
    Fail-Step "audio" "Irodori Python runtime is missing: $irodoriPython"
}

$inspectorPath = Join-Path ([System.IO.Path]::GetTempPath()) ("local-tts-v41-audio-inspect-$([guid]::NewGuid().ToString('N')).py")
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
[System.IO.File]::WriteAllText($inspectorPath, $inspectorSource, [System.Text.UTF8Encoding]::new($false))

try {
    foreach ($spec in $modelSpecs) {
        $modelName = [string]$spec.Name
        $requestId = "irodori-v4-1-smoke-$modelName-$([guid]::NewGuid().ToString('N'))"
        $payload = @{
            text = ConvertFrom-Utf8Base64 ([string]$spec.TextBase64)
            model = $modelName
            requestId = $requestId
            instruction = ConvertFrom-Utf8Base64 ([string]$spec.InstructionBase64)
            styleStrength = 3.0
            seed = [int]$spec.Seed
            format = "wav"
        } | ConvertTo-Json -Compress

        Write-Host "[SMOKE] generating with $modelName" -ForegroundColor Cyan
        $speak = Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/speak" -ContentType "application/json; charset=utf-8" -Body $payload -TimeoutSec 1800
        if (-not $speak.ok) { Fail-Step "speak" "$modelName returned ok=false" }
        if ([string]$speak.model -ne $modelName) { Fail-Step "speak" "$modelName response model mismatch: $($speak.model)" }
        if ([string]$speak.runtime -ne "irodori_voicedesign_direct") { Fail-Step "speak" "$modelName runtime mismatch: $($speak.runtime)" }
        if ([string]$speak.requestId -ne $requestId) { Fail-Step "speak" "$modelName request id mismatch: $($speak.requestId)" }

        $resolvedOutput = Join-Path $outputRoot ([string]$spec.FileName)
        if (Test-Path -LiteralPath $resolvedOutput -PathType Leaf) {
            Remove-Item -LiteralPath $resolvedOutput -Force
        }
        $audioUrl = [string]$speak.audioUrl
        if ([string]::IsNullOrWhiteSpace($audioUrl)) { Fail-Step "audio" "$modelName returned no audioUrl" }
        $audioUri = if ([System.Uri]::IsWellFormedUriString($audioUrl, [System.UriKind]::Absolute)) {
            $audioUrl
        } else {
            ([System.Uri]::new([System.Uri]$BaseUrl, $audioUrl)).AbsoluteUri
        }
        Invoke-WebRequest -Method Get -Uri $audioUri -OutFile $resolvedOutput -UseBasicParsing -TimeoutSec 120

        $bytes = [System.IO.File]::ReadAllBytes($resolvedOutput)
        if ($bytes.Length -lt 44) { Fail-Step "audio" "$modelName generated WAV is too small" }
        $riff = [System.Text.Encoding]::ASCII.GetString($bytes[0..3])
        $wave = [System.Text.Encoding]::ASCII.GetString($bytes[8..11])
        if ($riff -ne "RIFF" -or $wave -ne "WAVE") { Fail-Step "audio" "$modelName invalid WAV header: $riff/$wave" }

        $inspectionOutput = & $irodoriPython $inspectorPath $resolvedOutput 2>&1
        $inspectionExitCode = $LASTEXITCODE
        $inspectionText = (($inspectionOutput | Out-String).Trim())
        if ($inspectionExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($inspectionText)) {
            Fail-Step "audio" "$modelName audio inspection failed: exit=$inspectionExitCode output=$inspectionText"
        }
        try {
            $inspection = $inspectionText | ConvertFrom-Json
        } catch {
            Fail-Step "audio" "$modelName audio inspection returned invalid JSON: $inspectionText"
        }

        if ([int]$inspection.sampleRate -ne 48000) { Fail-Step "audio" "$modelName unexpected sample rate: $($inspection.sampleRate)" }
        if ([int]$inspection.channels -lt 1) { Fail-Step "audio" "$modelName generated WAV has no channels" }
        if ([double]$inspection.durationSec -lt 0.5) { Fail-Step "audio" "$modelName generated WAV is too short: $($inspection.durationSec)s" }
        if ([double]$inspection.rms -lt 0.0001) { Fail-Step "audio" "$modelName generated WAV is effectively silent: rms=$($inspection.rms)" }
        if ([double]$inspection.peak -gt 1.05) { Fail-Step "audio" "$modelName generated WAV exceeds expected peak range: peak=$($inspection.peak)" }

        Write-Host "[OK] $modelName real-generation smoke passed" -ForegroundColor Green
        Write-Host "requestId=$requestId"
        Write-Host "audio=$resolvedOutput"
        Write-Host "bytes=$($bytes.Length)"
        Write-Host ("durationSec={0:N3}" -f [double]$inspection.durationSec)
        Write-Host "sampleRate=$($inspection.sampleRate)"
        Write-Host ("rms={0:N6}" -f [double]$inspection.rms)
    }
} finally {
    Remove-Item -LiteralPath $inspectorPath -Force -ErrorAction SilentlyContinue
}

Write-Host "[PASS] Irodori v4.1 Small and Anime real-generation smoke completed." -ForegroundColor Green
