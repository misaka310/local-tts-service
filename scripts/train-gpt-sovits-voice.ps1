param(
  [string]$VoiceId = 'default',
  [string]$InputDir = '',
  [string]$GptSovitsRoot = ''
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
if (-not $InputDir) { $InputDir = Join-Path $RepoRoot "reference/gpt_sovits_ft/$VoiceId" }
if (-not $GptSovitsRoot) {
  $GptSovitsRoot = if ($env:LOCAL_TTS_GPT_SOVITS_ROOT) { $env:LOCAL_TTS_GPT_SOVITS_ROOT } else { Join-Path $RepoRoot 'runtime/vendor/GPT-SoVITS' }
}

$InputDir = Resolve-Path -LiteralPath $InputDir
$RawDir = Join-Path $InputDir 'raw'
$MetadataPath = Join-Path $InputDir 'metadata.list'
$VoiceWav = Join-Path $InputDir 'voice.wav'
$VoiceTxt = Join-Path $InputDir 'voice.txt'
$WeightsDir = Join-Path $RepoRoot "runtime/gpt-sovits/weights/$VoiceId"
$DefaultRefDir = Join-Path $WeightsDir 'default_ref'

New-Item -ItemType Directory -Force -Path $WeightsDir, $DefaultRefDir | Out-Null
if (Test-Path -LiteralPath $VoiceWav) { Copy-Item -LiteralPath $VoiceWav -Destination (Join-Path $DefaultRefDir 'voice.wav') -Force }
if (Test-Path -LiteralPath $VoiceTxt) { Copy-Item -LiteralPath $VoiceTxt -Destination (Join-Path $DefaultRefDir 'voice.txt') -Force }

if (-not (Test-Path -LiteralPath $MetadataPath) -and -not ((Test-Path -LiteralPath $VoiceWav) -and (Test-Path -LiteralPath $VoiceTxt))) {
  throw "Training input is missing. Put voice.wav + voice.txt or metadata.list under $InputDir"
}
if (-not (Test-Path -LiteralPath $GptSovitsRoot)) {
  throw "GPT-SoVITS repo not found. Run scripts/setup-gpt-sovits.bat first or set LOCAL_TTS_GPT_SOVITS_ROOT."
}

$Message = @"
Prepared GPT-SoVITS training folder.
Input: $InputDir
Output marker: $WeightsDir

Next step in GPT-SoVITS official WebUI/API environment:
1. Open GPT-SoVITS WebUI.
2. Use the files under $InputDir as the training dataset.
3. Save produced GPT and SoVITS weights under $WeightsDir.
4. Start api_v2.py with those weights loaded.

This script also copied default_ref/voice.wav and voice.txt so local-tts-service can call gpt_sovits_finetuned without passing voiceId.
"@
$Message | Tee-Object -FilePath (Join-Path $WeightsDir 'TRAINING_NEXT_STEPS.txt')
