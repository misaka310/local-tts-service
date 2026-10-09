param(
  [Parameter(Mandatory = $true)][string]$RequestJson,
  [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$Req = Get-Content -LiteralPath $RequestJson -Raw -Encoding UTF8 | ConvertFrom-Json
$ApiUrl = if ($env:LOCAL_TTS_GPT_SOVITS_API_URL) { $env:LOCAL_TTS_GPT_SOVITS_API_URL } else { 'http://127.0.0.1:9880/tts' }
$ApiBase = if ($ApiUrl.EndsWith('/tts')) { $ApiUrl.Substring(0, $ApiUrl.Length - 4) } else { $ApiUrl.TrimEnd('/') }
$CheckpointDir = [string]$Req.checkpointDir

$RefAudio = [string]$Req.referenceAudioPath
$RefTextPath = [string]$Req.referenceTextPath

if (-not $RefAudio) {
  $DefaultRefAudio = Join-Path $RepoRoot 'runtime/gpt-sovits/weights/default/default_ref/voice.wav'
  if ($env:LOCAL_TTS_GPT_SOVITS_DEFAULT_REF_AUDIO) { $DefaultRefAudio = $env:LOCAL_TTS_GPT_SOVITS_DEFAULT_REF_AUDIO }
  $RefAudio = $DefaultRefAudio
}
if (-not $RefTextPath) {
  $DefaultRefText = Join-Path $RepoRoot 'runtime/gpt-sovits/weights/default/default_ref/voice.txt'
  if ($env:LOCAL_TTS_GPT_SOVITS_DEFAULT_REF_TEXT) { $DefaultRefText = $env:LOCAL_TTS_GPT_SOVITS_DEFAULT_REF_TEXT }
  $RefTextPath = $DefaultRefText
}

if (-not (Test-Path -LiteralPath $RefAudio)) { throw "GPT-SoVITS reference wav not found. For zero-shot pass voiceId. For fine-tuned run scripts/train-gpt-sovits-voice.bat or set LOCAL_TTS_GPT_SOVITS_DEFAULT_REF_AUDIO. Missing: $RefAudio" }
if (-not (Test-Path -LiteralPath $RefTextPath)) { throw "GPT-SoVITS reference text not found: $RefTextPath" }

$RefText = (Get-Content -LiteralPath $RefTextPath -Raw -Encoding UTF8).Trim()
$RawLanguage = if ($Req.language) { [string]$Req.language } else { 'ja' }
$TextSplitMethod = if ($Req.textSplitMethod) { [string]$Req.textSplitMethod } else { 'cut0' }
$LanguageKey = $RawLanguage.Trim().ToLowerInvariant()
switch ($LanguageKey) {
  'japanese' { $Language = 'ja'; break }
  'english' { $Language = 'en'; break }
  'chinese' { $Language = 'zh'; break }
  'korean' { $Language = 'ko'; break }
  default { $Language = $RawLanguage }
}
$BodyObj = @{
  text = [string]$Req.text
  text_lang = $Language
  ref_audio_path = $RefAudio
  prompt_text = $RefText
  prompt_lang = $Language
  text_split_method = $TextSplitMethod
  batch_size = 1
  media_type = 'wav'
  streaming_mode = $false
}

function Add-RequestValue {
  param(
    [hashtable]$Target,
    [object]$Source,
    [string]$BodyKey,
    [string[]]$RequestKeys
  )
  foreach ($key in $RequestKeys) {
    if ($null -ne $Source.PSObject.Properties[$key] -and $null -ne $Source.$key -and "$($Source.$key)" -ne '') {
      $Target[$BodyKey] = $Source.$key
      return
    }
  }
}

Add-RequestValue $BodyObj $Req 'top_k' @('top_k', 'topK')
Add-RequestValue $BodyObj $Req 'top_p' @('top_p', 'topP')
Add-RequestValue $BodyObj $Req 'temperature' @('temperature')
Add-RequestValue $BodyObj $Req 'batch_size' @('batch_size', 'batchSize')
Add-RequestValue $BodyObj $Req 'batch_threshold' @('batch_threshold', 'batchThreshold')
Add-RequestValue $BodyObj $Req 'split_bucket' @('split_bucket', 'splitBucket')
Add-RequestValue $BodyObj $Req 'speed_factor' @('speed_factor', 'speedFactor', 'speedScale')
Add-RequestValue $BodyObj $Req 'fragment_interval' @('fragment_interval', 'fragmentInterval')
Add-RequestValue $BodyObj $Req 'seed' @('seed')
Add-RequestValue $BodyObj $Req 'parallel_infer' @('parallel_infer', 'parallelInfer')
Add-RequestValue $BodyObj $Req 'repetition_penalty' @('repetition_penalty', 'repetitionPenalty')
Add-RequestValue $BodyObj $Req 'sample_steps' @('sample_steps', 'sampleSteps')
Add-RequestValue $BodyObj $Req 'super_sampling' @('super_sampling', 'superSampling')
Add-RequestValue $BodyObj $Req 'overlap_length' @('overlap_length', 'overlapLength')
Add-RequestValue $BodyObj $Req 'min_chunk_length' @('min_chunk_length', 'minChunkLength')
Add-RequestValue $BodyObj $Req 'aux_ref_audio_paths' @('aux_ref_audio_paths', 'auxRefAudioPaths')

$Body = $BodyObj | ConvertTo-Json -Depth 8

if ($CheckpointDir) {
  $ResolvedCheckpointDir = Resolve-Path -LiteralPath $CheckpointDir -ErrorAction Stop
  $GptWeights = Get-ChildItem -LiteralPath $ResolvedCheckpointDir -Filter *.ckpt -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  $SovitsWeights = Get-ChildItem -LiteralPath $ResolvedCheckpointDir -Filter *.pth -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $GptWeights) { throw "GPT checkpoint not found under checkpointDir: $ResolvedCheckpointDir" }
  if (-not $SovitsWeights) { throw "SoVITS weight not found under checkpointDir: $ResolvedCheckpointDir" }
  $Utf8Json = [System.Text.UTF8Encoding]::new($false)
  $SetHeaders = @{ Accept = 'application/json' }
  $SetGptUrl = "$ApiBase/set_gpt_weights?weights_path=$([uri]::EscapeDataString($GptWeights.FullName))"
  $SetSovitsUrl = "$ApiBase/set_sovits_weights?weights_path=$([uri]::EscapeDataString($SovitsWeights.FullName))"
  $SetGpt = Invoke-WebRequest -Uri $SetGptUrl -Method Get -Headers $SetHeaders -UseBasicParsing -TimeoutSec 600
  $SetSovits = Invoke-WebRequest -Uri $SetSovitsUrl -Method Get -Headers $SetHeaders -UseBasicParsing -TimeoutSec 600
  if ($SetGpt.StatusCode -lt 200 -or $SetGpt.StatusCode -ge 300) { throw "Failed to load GPT weights: $($GptWeights.FullName)" }
  if ($SetSovits.StatusCode -lt 200 -or $SetSovits.StatusCode -ge 300) { throw "Failed to load SoVITS weights: $($SovitsWeights.FullName)" }
}

$Tmp = [System.IO.Path]::GetTempFileName()
try {
  $BodyBytes = $Utf8NoBom.GetBytes($Body)
  Invoke-WebRequest -Uri $ApiUrl -Method Post -Body $BodyBytes -ContentType 'application/json; charset=utf-8' -OutFile $Tmp -UseBasicParsing -TimeoutSec 600 | Out-Null
  Copy-Item -LiteralPath $Tmp -Destination $OutputPath -Force
} finally {
  Remove-Item -LiteralPath $Tmp -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path -LiteralPath $OutputPath) -or ((Get-Item -LiteralPath $OutputPath).Length -le 44)) { throw "GPT-SoVITS API did not return a valid wav: $OutputPath" }
