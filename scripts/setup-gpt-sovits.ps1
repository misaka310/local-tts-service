$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$VendorRoot = Join-Path $RepoRoot 'runtime/vendor'
$GptSovitsRoot = Join-Path $VendorRoot 'GPT-SoVITS'

New-Item -ItemType Directory -Force -Path $VendorRoot | Out-Null
if (-not (Test-Path -LiteralPath $GptSovitsRoot)) {
  git clone https://github.com/RVC-Boss/GPT-SoVITS.git $GptSovitsRoot
}

Write-Host "GPT-SoVITS repo is at: $GptSovitsRoot"
Write-Host 'Install pretrained models with the official GPT-SoVITS instructions, then start api_v2.py on 127.0.0.1:9880.'
