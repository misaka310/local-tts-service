param(
  [string]$GptSovitsRoot = '',
  [string]$Revision = 'bf81cdb14a38b674b6e9996dabc97340bc9978d2'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $GptSovitsRoot) {
  $GptSovitsRoot = if ($env:LOCAL_TTS_GPT_SOVITS_ROOT) {
    $env:LOCAL_TTS_GPT_SOVITS_ROOT
  } else {
    Join-Path $RepoRoot 'runtime/vendor/GPT-SoVITS-clean'
  }
}
if (-not [System.IO.Path]::IsPathRooted($GptSovitsRoot)) {
  $GptSovitsRoot = Join-Path $RepoRoot $GptSovitsRoot
}
$GptSovitsRoot = [System.IO.Path]::GetFullPath($GptSovitsRoot)
$VendorRoot = Split-Path -Parent $GptSovitsRoot
New-Item -ItemType Directory -Force -Path $VendorRoot | Out-Null

if (-not (Test-Path -LiteralPath $GptSovitsRoot)) {
  git clone --filter=blob:none --no-checkout https://github.com/RVC-Boss/GPT-SoVITS.git $GptSovitsRoot
  if ($LASTEXITCODE -ne 0) {
    throw "GPT-SoVITS clone failed (exit=$LASTEXITCODE): $GptSovitsRoot"
  }
  git -C $GptSovitsRoot checkout --detach $Revision
  if ($LASTEXITCODE -ne 0) {
    throw "GPT-SoVITS revision checkout failed (exit=$LASTEXITCODE): $Revision"
  }
}
if (-not (Test-Path -LiteralPath (Join-Path $GptSovitsRoot 'api_v2.py') -PathType Leaf)) {
  throw "GPT-SoVITS source path exists but is incomplete; it was left untouched: $GptSovitsRoot"
}
$actualRevision = (git -C $GptSovitsRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualRevision -ne $Revision) {
  throw "GPT-SoVITS checkout revision mismatch: expected=$Revision actual=$actualRevision"
}
$dirty = git -C $GptSovitsRoot status --porcelain
if ($LASTEXITCODE -ne 0 -or $dirty) {
  throw "GPT-SoVITS source checkout must stay clean and read-only: $GptSovitsRoot"
}

Write-Host "GPT-SoVITS source checkout is at: $GptSovitsRoot ($actualRevision)"
Write-Host 'Keep this checkout read-only. Use runtime/venvs/gpt-sovits and runtime/gpt-sovits for mutable environment and config.'
