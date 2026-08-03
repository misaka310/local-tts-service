[CmdletBinding()]
param(
  [string]$PythonExecutable = 'python',
  [switch]$SkipModelDownload,
  [switch]$Force,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'git-runtime.ps1')
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$RuntimeRoot = Join-Path $RepoRoot 'runtime'
$VendorRoot = Join-Path $RuntimeRoot 'vendor'
$ModelRoot = Join-Path $RuntimeRoot 'models\irodori'
$VenvRoot = Join-Path $RuntimeRoot 'venv-irodori'
$VenvPython = Join-Path $VenvRoot 'Scripts\python.exe'
$SourceRoot = Join-Path $VendorRoot 'Irodori-TTS-upstream'
$PinnedRevision = '8ca3acb58ab4e19ad6d594aaed6bafe3e88f7f71'
$RepositoryUrl = 'https://github.com/Aratako/Irodori-TTS.git'
$DownloadScript = Join-Path $PSScriptRoot 'download_hf_snapshot.py'
$RepoPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$PythonCommand = Get-Command $PythonExecutable -ErrorAction SilentlyContinue
$BootstrapPython = if ($PythonCommand) {
  $PythonCommand.Source
} elseif (Test-Path -LiteralPath $RepoPython -PathType Leaf) {
  $RepoPython
} else {
  $PythonExecutable
}

$Models = @(
  @{ RepoId = 'Aratako/Irodori-TTS-500M-v2'; Directory = 'Irodori-TTS-500M-v2'; AllowPatterns = @() },
  @{ RepoId = 'Aratako/Irodori-TTS-500M-v3'; Directory = 'Irodori-TTS-500M-v3'; AllowPatterns = @() },
  @{ RepoId = 'Aratako/Irodori-TTS-600M-v3-VoiceDesign'; Directory = 'Irodori-TTS-600M-v3-VoiceDesign'; AllowPatterns = @() },
  @{ RepoId = 'Aratako/Irodori-TTS-v4-Small'; Directory = 'Irodori-TTS-v4-Small'; AllowPatterns = @() },
  @{ RepoId = 'Aratako/Semantic-DACVAE-Japanese-32dim'; Directory = 'Semantic-DACVAE-Japanese-32dim'; AllowPatterns = @() },
  @{
    RepoId = 'llm-jp/llm-jp-3-150m'
    Directory = 'tokenizers\llm-jp-3-150m'
    AllowPatterns = @('tokenizer*', 'special_tokens_map.json', 'added_tokens.json', 'vocab.json', 'merges.txt', '*.model')
  }
)

function Write-Step([string]$Message) {
  if ($DryRun) { Write-Output "[DRY-RUN] $Message" }
  else { Write-Output "[STEP] $Message" }
}

function Invoke-Native {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter(Mandatory = $true)][string[]]$Arguments,
    [Parameter(Mandatory = $true)][string]$Label,
    [string]$WorkingDirectory = $RepoRoot,
    [ValidateRange(1, 10)][int]$Attempts = 1,
    [ValidateRange(0, 60)][int]$RetryDelaySeconds = 5
  )
  if ($DryRun) { return }
  for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -NoNewWindow -Wait -PassThru
    if ($process.ExitCode -eq 0) { return }
    if ($attempt -lt $Attempts) {
      Write-Warning "$Label failed once; retrying after a short delay for transient Windows file locks"
      Start-Sleep -Seconds $RetryDelaySeconds
    }
  }
  throw "$Label failed with exit code $($process.ExitCode)"
}

function Get-CheckoutRevision([string]$RepositoryRoot) {
  $gitRoot = Join-Path $RepositoryRoot '.git'
  $headPath = Join-Path $gitRoot 'HEAD'
  if (-not (Test-Path -LiteralPath $headPath -PathType Leaf)) { return '' }
  $head = (Get-Content -LiteralPath $headPath -Raw -Encoding UTF8).Trim()
  if ($head -notmatch '^ref:\s+(.+)$') { return $head }
  $refName = $Matches[1].Trim()
  $refPath = Join-Path $gitRoot $refName
  if (Test-Path -LiteralPath $refPath -PathType Leaf) {
    return (Get-Content -LiteralPath $refPath -Raw -Encoding UTF8).Trim()
  }
  $packedRefs = Join-Path $gitRoot 'packed-refs'
  if (Test-Path -LiteralPath $packedRefs -PathType Leaf) {
    foreach ($line in Get-Content -LiteralPath $packedRefs -Encoding UTF8) {
      if ($line -match '^([0-9a-f]{40})\s+(.+)$' -and $Matches[2] -eq $refName) {
        return $Matches[1]
      }
    }
  }
  return ''
}

$GitRuntime = if (-not [string]::IsNullOrWhiteSpace($env:LOCAL_TTS_GIT_DIR)) {
  Resolve-LocalTtsGitRuntime -RepoRoot $RepoRoot
} else {
  Install-LocalTtsManagedGitRuntime -RepoRoot $RepoRoot -DryRun:$DryRun
}
Add-LocalTtsGitRuntimeToPath -GitRuntime $GitRuntime
$GitExecutable = $GitRuntime.GitPath
Write-Step "use Git runtime: $($GitRuntime.Source) ($GitExecutable)"

if (-not $DryRun -and -not (Test-Path -LiteralPath $BootstrapPython -PathType Leaf)) {
  throw "Python was not found. Run local-tts.bat -ForceSetup first or pass -PythonExecutable. Resolved path: $BootstrapPython"
}

Write-Step 'create repo-local Irodori directories'
if (-not $DryRun) {
  New-Item -ItemType Directory -Force -Path $VendorRoot, $ModelRoot | Out-Null
}

if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot '.git'))) {
  Write-Step "clone Irodori-TTS into runtime/vendor at revision $PinnedRevision"
  Invoke-Native -FilePath $GitExecutable -Arguments @('clone', $RepositoryUrl, $SourceRoot) -Label 'git clone Irodori-TTS'
}

$currentRevision = if ($DryRun) { '' } else { Get-CheckoutRevision -RepositoryRoot $SourceRoot }
if ($currentRevision -eq $PinnedRevision) {
  Write-Step "reuse pinned Irodori source revision $PinnedRevision"
} else {
  Write-Step "checkout pinned Irodori source revision $PinnedRevision"
  Invoke-Native -FilePath $GitExecutable -Arguments @('-C', $SourceRoot, 'fetch', '--tags', '--force', 'origin') -Label 'git fetch Irodori-TTS'
  Invoke-Native -FilePath $GitExecutable -Arguments @('-C', $SourceRoot, 'checkout', '--force', $PinnedRevision) -Label 'git checkout Irodori-TTS revision'
}

if ($Force -and (Test-Path -LiteralPath $VenvRoot)) {
  Write-Step 'remove existing runtime/venv-irodori'
  if (-not $DryRun) { Remove-Item -LiteralPath $VenvRoot -Recurse -Force }
}

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
  Write-Step 'create runtime/venv-irodori'
  try {
    Invoke-Native -FilePath $BootstrapPython -Arguments @('-m', 'venv', $VenvRoot) -Label 'create Irodori virtual environment'
  }
  catch {
    Invoke-Native -FilePath $BootstrapPython -Arguments @('-m', 'virtualenv', $VenvRoot) -Label 'create Irodori virtual environment with virtualenv'
  }
} else {
  Write-Step 'reuse runtime/venv-irodori'
}

Write-Step 'upgrade pip tooling in runtime/venv-irodori'
Invoke-Native -FilePath $VenvPython -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip', 'setuptools', 'wheel') -Label 'upgrade Irodori pip tooling'

$NvidiaExecutable = $null
$NvidiaCommand = Get-Command 'nvidia-smi.exe' -ErrorAction SilentlyContinue
if ($NvidiaCommand) {
  $NvidiaExecutable = $NvidiaCommand.Source
} else {
  $systemNvidia = Join-Path $env:WINDIR 'System32\nvidia-smi.exe'
  if (Test-Path -LiteralPath $systemNvidia -PathType Leaf) { $NvidiaExecutable = $systemNvidia }
}

if ($DryRun -or $NvidiaExecutable) {
  Write-Step 'install tested CUDA 12.8 PyTorch for Irodori'
  Invoke-Native -FilePath $VenvPython -Arguments @('-m', 'pip', 'install', 'torch==2.10.0+cu128', 'torchaudio==2.10.0+cu128', '--index-url', 'https://download.pytorch.org/whl/cu128') -Label 'install CUDA PyTorch for Irodori'
} else {
  Write-Step 'install CPU PyTorch for Irodori'
  Invoke-Native -FilePath $VenvPython -Arguments @('-m', 'pip', 'install', 'torch==2.10.0', 'torchaudio==2.10.0') -Label 'install CPU PyTorch for Irodori'
}

Write-Step 'install pinned Irodori dependencies'
Invoke-Native -FilePath $VenvPython -Arguments @('-m', 'pip', 'install', '-r', (Join-Path $SourceRoot 'requirements.txt')) -Label 'install Irodori requirements'
Invoke-Native -FilePath $VenvPython -Arguments @('-m', 'pip', 'install', '--no-deps', '-e', $SourceRoot) -Label 'install Irodori source package'

if ($env:OS -eq 'Windows_NT') {
  Write-Step 'configure app-local Microsoft Visual C++ runtime for Irodori'
  Invoke-Native -FilePath $VenvPython -Arguments @('-m', 'pip', 'install', 'msvc-runtime==14.44.35112') -Label 'install app-local MSVC runtime for Irodori' -Attempts 2
  if (-not $DryRun) {
    $venvScripts = Split-Path -Parent $VenvPython
    $runtimeDll = Join-Path $venvScripts 'vcruntime140.dll'
    if (-not (Test-Path -LiteralPath $runtimeDll -PathType Leaf)) {
      throw "Irodori app-local Microsoft Visual C++ runtime DLL was not installed: $runtimeDll"
    }
    $sitePackagesOutput = & $VenvPython -c "import site; print(site.getsitepackages()[0])" 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'resolve Irodori site-packages path failed' }
    $sitePackages = (($sitePackagesOutput | Out-String).Trim())
    if ([string]::IsNullOrWhiteSpace($sitePackages) -or -not (Test-Path -LiteralPath $sitePackages -PathType Container)) {
      throw "Irodori site-packages directory was not found: $sitePackages"
    }
    $siteCustomizePath = Join-Path $sitePackages 'sitecustomize.py'
    $siteCustomize = @'
import os
import sys

_local_tts_msvc_dll_handles = []
if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    for _runtime_dir in (sys.prefix, os.path.join(sys.prefix, "Scripts")):
        if os.path.isdir(_runtime_dir):
            try:
                _local_tts_msvc_dll_handles.append(os.add_dll_directory(_runtime_dir))
            except OSError:
                pass
'@
    Set-Content -LiteralPath $siteCustomizePath -Value $siteCustomize -Encoding ASCII
    $torchCheckPath = Join-Path $VenvRoot 'verify_torch_runtime.py'
    Set-Content -LiteralPath $torchCheckPath -Value "import torch`nprint('Irodori torch runtime ready:', torch.__version__)" -Encoding ASCII
    try {
      Invoke-Native -FilePath $VenvPython -Arguments @($torchCheckPath) -Label 'verify app-local MSVC runtime for Irodori'
    }
    finally {
      Remove-Item -LiteralPath $torchCheckPath -Force -ErrorAction SilentlyContinue
    }
  }
}

if (-not $SkipModelDownload) {
  foreach ($model in $Models) {
    $target = Join-Path $ModelRoot $model.Directory
    Write-Step "download $($model.RepoId) into runtime/models/irodori"
    $downloadArguments = @($DownloadScript, '--repo-id', $model.RepoId, '--local-dir', $target, '--cache-dir', (Join-Path $RuntimeRoot 'hf-cache'))
    foreach ($pattern in $model.AllowPatterns) {
      $downloadArguments += @('--allow-pattern', $pattern)
    }
    Invoke-Native -FilePath $VenvPython -Arguments $downloadArguments -Label "download $($model.RepoId)"
  }
} else {
  Write-Step 'skip Irodori model downloads'
}

Write-Step 'verify repo-local Irodori imports'
Invoke-Native -FilePath $VenvPython -Arguments @((Join-Path $PSScriptRoot 'check_irodori_install.py'), $SourceRoot) -Label 'verify Irodori imports'

if (-not $DryRun) {
  foreach ($model in $Models | Where-Object { $_.Directory -like 'Irodori-TTS-*' }) {
    $modelFile = Join-Path (Join-Path $ModelRoot $model.Directory) 'model.safetensors'
    if (-not (Test-Path -LiteralPath $modelFile -PathType Leaf)) {
      throw "Irodori model file not found: $modelFile"
    }
  }
  $codecWeights = Join-Path (Join-Path $ModelRoot 'Semantic-DACVAE-Japanese-32dim') 'weights.pth'
  if (-not (Test-Path -LiteralPath $codecWeights -PathType Leaf)) {
    throw "Irodori codec files not found: $codecWeights"
  }
  $textProcessorRoot = Join-Path $ModelRoot 'tokenizers\llm-jp-3-150m'
  $textProcessorConfig = Join-Path $textProcessorRoot 'tokenizer_config.json'
  $textProcessorData = Join-Path $textProcessorRoot 'tokenizer.json'
  if (-not (Test-Path -LiteralPath $textProcessorConfig -PathType Leaf) -or -not (Test-Path -LiteralPath $textProcessorData -PathType Leaf)) {
    throw "Irodori Tokenizer files not found: $textProcessorRoot"
  }
}

Write-Output ''
if ($DryRun) {
  Write-Output '[DRY-RUN] Irodori setup plan completed without changing files.'
} else {
  Write-Output '[OK] Irodori is installed inside this repository under runtime/.'
  Write-Output 'Restart local-tts.bat, then select Irodori v4 Small, Irodori v3, Irodori v3 VoiceDesign, or Irodori v2.'
}
