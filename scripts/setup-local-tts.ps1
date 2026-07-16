[CmdletBinding()]
param(
  [string]$ConfigPath = 'config/config.local.json',
  [string]$PythonExecutable = 'python',
  [switch]$SkipPythonInstall,
  [switch]$SkipCudaTorchInstall,
  [switch]$SkipMediaToolsInstall,
  [switch]$SkipFrontendInstall,
  [switch]$SkipVendorSetup,
  [switch]$DownloadQwenModels,
  [switch]$QwenDefaultModelOnly,
  [switch]$DownloadFfmpeg,
  [switch]$SetupWslTtsModels,
  [switch]$SetupIrodori,
  [switch]$NoGptSovitsStart,
  [switch]$StartAfterSetup,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'python-runtime.ps1')
. (Join-Path $PSScriptRoot 'node-runtime.ps1')
. (Join-Path $PSScriptRoot 'git-runtime.ps1')

function Write-Step {
  param([string]$Message)
  if ($DryRun) { Write-Output "[DRY-RUN] $Message" }
  else { Write-Output "[STEP] $Message" }
}

function Assert-CommandAvailable {
  param(
    [Parameter(Mandatory = $true)][string]$Command,
    [Parameter(Mandatory = $true)][string]$InstallHint
  )
  Write-Step "check prerequisite: $Command"
  if ($DryRun) { return }
  if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
    throw "Required command '$Command' was not found. $InstallHint"
  }
}

function Assert-LastExitCode {
  param([Parameter(Mandatory = $true)][string]$CommandLabel)
  if ($LASTEXITCODE -ne 0) {
    throw "$CommandLabel failed with exit code $LASTEXITCODE"
  }
}

function Invoke-SetupCommand {
  param(
    [string]$Display,
    [scriptblock]$Action
  )
  Write-Step $Display
  if (-not $DryRun) { & $Action }
}

function Resolve-RepoPath {
  param([string]$Root, [string]$RawPath)
  if ([string]::IsNullOrWhiteSpace($RawPath)) { return '' }
  if ([System.IO.Path]::IsPathRooted($RawPath)) { return $RawPath }
  return [System.IO.Path]::GetFullPath((Join-Path $Root $RawPath))
}

function Read-JsonFile {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
  $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
  if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
  return ($raw | ConvertFrom-Json)
}

function Get-PropertyValue {
  param(
    [object]$Object,
    [string]$Name,
    [object]$Default = $null
  )
  if ($null -eq $Object) { return $Default }
  $prop = $Object.PSObject.Properties[$Name]
  if ($null -eq $prop) { return $Default }
  if ($null -eq $prop.Value) { return $Default }
  return $prop.Value
}

function Get-PythonPath {
  param([string]$RepoRoot, [string]$RequestedPython)
  $venvPython = Join-Path $RepoRoot '.venv/Scripts/python.exe'
  if (Test-Path -LiteralPath $venvPython) { return $venvPython }
  return $RequestedPython
}

function Get-QwenModelIds {
  param(
    [string]$RepoRoot,
    [string]$ConfigLocalPath,
    [switch]$DefaultModelOnly
  )
  if ($DefaultModelOnly) {
    return @('Qwen/Qwen3-TTS-12Hz-1.7B-Base')
  }
  $configs = @(
    $ConfigLocalPath,
    (Join-Path $RepoRoot 'config/config.example.json'),
    (Join-Path $RepoRoot 'config/config.qwen3.example.json')
  ) | Select-Object -Unique
  $ids = New-Object System.Collections.Generic.List[string]
  foreach ($configPath in $configs) {
    $config = Read-JsonFile -Path $configPath
    if ($null -eq $config) { continue }
    $models = Get-PropertyValue -Object $config -Name 'models'
    if ($null -eq $models) { continue }
    foreach ($modelProp in $models.PSObject.Properties) {
      $model = $modelProp.Value
      $runtime = [string](Get-PropertyValue -Object $model -Name 'runtime' -Default '')
      $family = [string](Get-PropertyValue -Object $model -Name 'family' -Default '')
      $modelId = [string](Get-PropertyValue -Object $model -Name 'modelId' -Default '')
      if ($modelProp.Name -eq 'qwen3_tts_design_1_7b' -or $modelId -eq 'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign') { continue }
      if ($modelId -and ($runtime -eq 'qwen3_tts' -or $family -eq 'qwen3_tts')) {
        if (-not $ids.Contains($modelId)) { $ids.Add($modelId) }
      }
    }
  }
  return @($ids)
}

function Convert-RepoIdToDirName {
  param([string]$RepoId)
  return ($RepoId -replace '[^A-Za-z0-9_.-]+', '__')
}

function Get-PyTorchPairInfo {
  param([Parameter(Mandatory = $true)][string]$PythonPath)

  $stdoutPath = [System.IO.Path]::GetTempFileName()
  $stderrPath = [System.IO.Path]::GetTempFileName()
  $probePath = [System.IO.Path]::GetTempFileName()
  try {
    @'
import json
import torch
import torchaudio

print(json.dumps({
    "torchVersion": torch.__version__,
    "torchaudioVersion": torchaudio.__version__,
    "cudaAvailable": torch.cuda.is_available(),
}))
'@ | Set-Content -LiteralPath $probePath -Encoding UTF8

    $process = Start-Process -FilePath $PythonPath `
      -ArgumentList @($probePath) `
      -Wait `
      -PassThru `
      -NoNewWindow `
      -RedirectStandardOutput $stdoutPath `
      -RedirectStandardError $stderrPath
    $stdout = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue } else { '' }
    $stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue } else { '' }
    if ($process.ExitCode -ne 0) {
      $details = if (-not [string]::IsNullOrWhiteSpace($stderr)) { $stderr.Trim() } elseif (-not [string]::IsNullOrWhiteSpace($stdout)) { $stdout.Trim() } else { '(no stdout or stderr was produced)' }
      throw "PyTorch import verification failed with exit code $($process.ExitCode):`n$details"
    }
    if ([string]::IsNullOrWhiteSpace($stdout)) {
      throw 'PyTorch import verification returned no JSON on stdout.'
    }
    try {
      return ($stdout.Trim() | ConvertFrom-Json)
    }
    catch {
      throw "PyTorch import verification returned invalid JSON:`n$($stdout.Trim())`n$($_.Exception.Message)"
    }
  }
  finally {
    Remove-Item -LiteralPath $stdoutPath, $stderrPath, $probePath -Force -ErrorAction SilentlyContinue
  }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$configLocalPath = Resolve-RepoPath -Root $repoRoot -RawPath $ConfigPath
$configExamplePath = Join-Path $repoRoot 'config/config.example.json'
$requirementsPath = Join-Path $repoRoot 'config/requirements.txt'
$frontendDir = Join-Path $repoRoot 'frontend'
$runtimeDir = Join-Path $repoRoot 'runtime'
$vendorDir = Join-Path $runtimeDir 'vendor'
$modelRoot = Join-Path $runtimeDir 'models/huggingface'
$hfCacheDir = Join-Path $runtimeDir 'hf-cache'
$logsDir = Join-Path $runtimeDir 'logs'
$pythonRuntime = $null
$nodeRuntime = $null
$gitRuntime = $null
$torchBaseVersion = '2.8.0'
$expectedTorchVersion = $null

Write-Output '========== local-tts-service setup =========='
if ($DryRun) { Write-Output '[DRY-RUN] no files will be changed and no network downloads will run' }
Write-Output "repo: $repoRoot"
Write-Output "config: $configLocalPath"

if (-not $SkipFrontendInstall) {
  if (-not [string]::IsNullOrWhiteSpace($env:LOCAL_TTS_NODE_DIR)) {
    Write-Step 'use Node.js from LOCAL_TTS_NODE_DIR'
    $nodeRuntime = Resolve-LocalTtsNodeRuntime -RepoRoot $repoRoot
  } else {
    Write-Step 'prepare repo-managed portable Node.js (first setup may download it)'
    $nodeRuntime = Install-LocalTtsManagedNodeRuntime -RepoRoot $repoRoot -DryRun:$DryRun
  }
  Write-Output "Node.js runtime: $($nodeRuntime.Source) ($($nodeRuntime.NodeDir))"
}

if (-not $SkipPythonInstall -or -not $SkipMediaToolsInstall -or $DownloadQwenModels -or $SetupIrodori) {
  Write-Step 'prepare Python 3.11 runtime (first setup may download it)'
  $pythonRuntime = Install-LocalTtsManagedPythonRuntime -RepoRoot $repoRoot -RequestedPython $PythonExecutable -DryRun:$DryRun
  $PythonExecutable = $pythonRuntime.PythonPath
  Write-Output "Python runtime: $($pythonRuntime.Source) ($PythonExecutable)"
}
if (-not $SkipVendorSetup -or $SetupIrodori) {
  if (-not [string]::IsNullOrWhiteSpace($env:LOCAL_TTS_GIT_DIR)) {
    Write-Step 'use Git from LOCAL_TTS_GIT_DIR'
    $gitRuntime = Resolve-LocalTtsGitRuntime -RepoRoot $repoRoot
  } else {
    Write-Step 'prepare repo-managed portable MinGit (first setup may download it)'
    $gitRuntime = Install-LocalTtsManagedGitRuntime -RepoRoot $repoRoot -DryRun:$DryRun
  }
  Add-LocalTtsGitRuntimeToPath -GitRuntime $gitRuntime
  Write-Output "Git runtime: $($gitRuntime.Source) ($($gitRuntime.GitPath))"
}
if ($SetupWslTtsModels) {
  Assert-CommandAvailable -Command 'wsl.exe' -InstallHint 'Install WSL2 and an Ubuntu distribution first.'
}

if (-not (Test-Path -LiteralPath $configLocalPath -PathType Leaf)) {
  Invoke-SetupCommand "create config/config.local.json from config/config.example.json" {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $configLocalPath) | Out-Null
    Copy-Item -LiteralPath $configExamplePath -Destination $configLocalPath -Force
  }
} else {
  Write-Step "config/config.local.json already exists"
}

foreach ($dir in @($runtimeDir, $vendorDir, $modelRoot, $hfCacheDir, $logsDir, (Join-Path $repoRoot 'reference/voices'))) {
  Invoke-SetupCommand "ensure directory: $dir" {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }
}

if ($SkipPythonInstall) {
  Write-Step 'skip Python dependency install'
} else {
  $venvPython = Join-Path $repoRoot '.venv/Scripts/python.exe'
  if (-not (Test-Path -LiteralPath $venvPython)) {
    Invoke-SetupCommand 'create Python venv: python -m venv .venv' {
      & $PythonExecutable -m venv (Join-Path $repoRoot '.venv')
      if ($LASTEXITCODE -ne 0) {
        & $PythonExecutable -m virtualenv (Join-Path $repoRoot '.venv')
      }
      Assert-LastExitCode -CommandLabel 'Python virtual environment creation'
    }
  } else {
    Write-Step 'Python venv already exists'
  }
  $pythonPath = Get-PythonPath -RepoRoot $repoRoot -RequestedPython $PythonExecutable
  Invoke-SetupCommand 'upgrade pip' {
    & $pythonPath -m pip install --upgrade pip
    Assert-LastExitCode -CommandLabel 'pip install --upgrade pip'
  }

  if ($SkipCudaTorchInstall) {
    Write-Step 'skip pinned PyTorch install'
  } elseif ($DryRun) {
    Write-Step 'if NVIDIA GPU is detected, install torch==2.8.0+cu128 and torchaudio==2.8.0+cu128 from https://download.pytorch.org/whl/cu128'
    Write-Step 'if NVIDIA GPU is not detected, install torch==2.8.0+cpu and torchaudio==2.8.0+cpu from https://download.pytorch.org/whl/cpu'
  } else {
    $nvidiaSmi = Get-Command 'nvidia-smi.exe' -ErrorAction SilentlyContinue
    $hasNvidiaGpu = $false
    if ($nvidiaSmi) {
      & $nvidiaSmi.Source --query-gpu=name --format=csv,noheader *> $null
      $hasNvidiaGpu = ($LASTEXITCODE -eq 0)
    }
    if ($hasNvidiaGpu) {
      $expectedTorchVersion = "$torchBaseVersion+cu128"
      Invoke-SetupCommand 'install CUDA 12.8 PyTorch for NVIDIA GPU' {
        & $pythonPath -m pip install "torch==$expectedTorchVersion" "torchaudio==$expectedTorchVersion" --index-url 'https://download.pytorch.org/whl/cu128'
        Assert-LastExitCode -CommandLabel 'CUDA PyTorch install'
      }
    } else {
      $expectedTorchVersion = "$torchBaseVersion+cpu"
      Invoke-SetupCommand 'install CPU PyTorch for non-NVIDIA systems' {
        & $pythonPath -m pip install "torch==$expectedTorchVersion" "torchaudio==$expectedTorchVersion" --index-url 'https://download.pytorch.org/whl/cpu'
        Assert-LastExitCode -CommandLabel 'CPU PyTorch install'
      }
    }
  }

  Invoke-SetupCommand 'pip install -r config/requirements.txt' {
    & $pythonPath -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) {
      Write-Warning 'dependency install failed once; retrying after a short delay for transient Windows file locks'
      Start-Sleep -Seconds 5
      & $pythonPath -m pip install -r $requirementsPath
    }
    Assert-LastExitCode -CommandLabel 'pip install -r config/requirements.txt'
  }

  if ($SkipCudaTorchInstall) {
    Write-Step 'skip pinned PyTorch post-install verification'
  } else {
    Invoke-SetupCommand 'verify pinned PyTorch versions after requirements install' {
      if ([string]::IsNullOrWhiteSpace($expectedTorchVersion)) {
        throw 'Expected PyTorch version was not selected.'
      }
      $torchInfo = Get-PyTorchPairInfo -PythonPath $pythonPath
      $actualTorchVersion = [string]$torchInfo.torchVersion
      $actualTorchaudioVersion = [string]$torchInfo.torchaudioVersion
      if ($actualTorchVersion -ne $expectedTorchVersion -or $actualTorchaudioVersion -ne $expectedTorchVersion) {
        throw "config/requirements.txt changed the pinned PyTorch pair. Expected torch/torchaudio $expectedTorchVersion, got $actualTorchVersion / $actualTorchaudioVersion"
      }
      Write-Output "[OK] torch $actualTorchVersion / torchaudio $actualTorchaudioVersion"
    }
  }

  if ($env:OS -eq 'Windows_NT') {
    Invoke-SetupCommand 'configure app-local Microsoft Visual C++ runtime' {
      $venvScripts = Split-Path -Parent $pythonPath
      $runtimeDll = Join-Path $venvScripts 'vcruntime140.dll'
      if (-not (Test-Path -LiteralPath $runtimeDll -PathType Leaf)) {
        throw "App-local Microsoft Visual C++ runtime DLL was not installed: $runtimeDll"
      }

      $sitePackagesOutput = & $pythonPath -c "import site; print(site.getsitepackages()[0])" 2>&1
      Assert-LastExitCode -CommandLabel 'resolve Python site-packages path'
      $sitePackages = (($sitePackagesOutput | Out-String).Trim())
      if ([string]::IsNullOrWhiteSpace($sitePackages) -or -not (Test-Path -LiteralPath $sitePackages -PathType Container)) {
        throw "Python site-packages directory was not found: $sitePackages"
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

      & $pythonPath -c "import torch; print('torch runtime ready:', torch.__version__)"
      Assert-LastExitCode -CommandLabel 'app-local Microsoft Visual C++ runtime verification'
    }
  }
}

if ($SkipMediaToolsInstall) {
  Write-Step 'skip YouTube/Whisper/background-removal media tool install'
} else {
  $pythonPath = Get-PythonPath -RepoRoot $repoRoot -RequestedPython $PythonExecutable
  Invoke-SetupCommand 'verify YouTube and Whisper dependencies' {
    & $pythonPath -c "import yt_dlp, faster_whisper; print('yt-dlp/faster-whisper ready')"
    Assert-LastExitCode -CommandLabel 'YouTube/Whisper dependency verification'
  }
  $demucsVenvDir = Join-Path $runtimeDir 'venv-demucs'
  $demucsPython = Join-Path $demucsVenvDir 'Scripts/python.exe'
  if (-not (Test-Path -LiteralPath $demucsPython -PathType Leaf)) {
    Invoke-SetupCommand 'create background-removal venv' {
      & $PythonExecutable -m venv $demucsVenvDir
      if ($LASTEXITCODE -ne 0) { & $PythonExecutable -m virtualenv $demucsVenvDir }
      Assert-LastExitCode -CommandLabel 'background-removal virtual environment creation'
    }
  } else {
    Write-Step 'background-removal venv already exists'
  }
  Invoke-SetupCommand 'install background-music removal engine' {
    & $demucsPython -m pip install --upgrade pip
    Assert-LastExitCode -CommandLabel 'background-removal pip upgrade'
    & $demucsPython -m pip install 'demucs==4.0.1'
    Assert-LastExitCode -CommandLabel 'background-removal engine install'
  }
}

if ($SkipFrontendInstall) {
  Write-Step 'skip frontend npm install'
} else {
  $nodeModules = Join-Path $frontendDir 'node_modules'
  $packageLock = Join-Path $frontendDir 'package-lock.json'
  if (Test-Path -LiteralPath $packageLock -PathType Leaf) {
    Invoke-SetupCommand 'frontend npm ci' {
      Push-Location $frontendDir
      try {
        & $nodeRuntime.NpmPath ci
        Assert-LastExitCode -CommandLabel 'npm ci'
      }
      finally { Pop-Location }
    }
  } else {
    Invoke-SetupCommand 'frontend npm install' {
      Push-Location $frontendDir
      try {
        & $nodeRuntime.NpmPath install
        Assert-LastExitCode -CommandLabel 'npm install'
      }
      finally { Pop-Location }
    }
  }
  if ($DryRun) { Write-Output "[DRY-RUN] frontend node_modules target: $nodeModules" }
}

if ($SkipVendorSetup) {
  Write-Step 'skip vendor setup'
} else {
  Invoke-SetupCommand 'setup GPT-SoVITS vendor repository' {
    & (Join-Path $PSScriptRoot 'setup-gpt-sovits.ps1')
  }
}

if ($DownloadFfmpeg) {
  $ffmpegRoot = Join-Path $vendorDir 'ffmpeg'
  $ffmpegZip = Join-Path $vendorDir 'ffmpeg-release-essentials.zip'
  $ffmpegUrl = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
  Invoke-SetupCommand "download FFmpeg essentials to $ffmpegRoot" {
    if (-not (Test-Path -LiteralPath $ffmpegRoot)) { New-Item -ItemType Directory -Force -Path $ffmpegRoot | Out-Null }
    if (-not (Get-ChildItem -LiteralPath $ffmpegRoot -Recurse -Filter 'ffmpeg.exe' -File -ErrorAction SilentlyContinue | Select-Object -First 1)) {
      Invoke-WebRequest -Uri $ffmpegUrl -OutFile $ffmpegZip
      Expand-Archive -LiteralPath $ffmpegZip -DestinationPath $ffmpegRoot -Force
    }
  }
} else {
  Write-Step 'FFmpeg download not requested'
}

if ($DownloadQwenModels) {
  $pythonPath = Get-PythonPath -RepoRoot $repoRoot -RequestedPython $PythonExecutable
  Invoke-SetupCommand 'pip install huggingface_hub for model downloads' {
    & $pythonPath -m pip install 'huggingface_hub>=0.24.0'
    Assert-LastExitCode -CommandLabel 'huggingface_hub install'
  }
  $qwenIds = Get-QwenModelIds -RepoRoot $repoRoot -ConfigLocalPath $configLocalPath -DefaultModelOnly:$QwenDefaultModelOnly
  if ($qwenIds.Count -eq 0) {
    Write-Step 'no Qwen model ids found in config'
  }
  foreach ($repoId in $qwenIds) {
    $localDir = Join-Path $modelRoot (Convert-RepoIdToDirName -RepoId $repoId)
    Invoke-SetupCommand "download Qwen model: $repoId -> $localDir" {
      & $pythonPath (Join-Path $PSScriptRoot 'download_hf_snapshot.py') --repo-id $repoId --local-dir $localDir --cache-dir $hfCacheDir
      Assert-LastExitCode -CommandLabel "Qwen model download: $repoId"
    }
  }
} else {
  Write-Step 'Qwen model downloads not requested'
}

if ($SetupIrodori) {
  Invoke-SetupCommand 'setup repo-local Irodori models and runtime' {
    & (Join-Path $PSScriptRoot 'setup-irodori.ps1') -PythonExecutable $PythonExecutable
  }
} else {
  Write-Step 'Irodori setup not requested (standard first-run BAT includes it)'
}

if ($SetupWslTtsModels) {
  Invoke-SetupCommand 'setup WSL zero-shot TTS models (Sarashina, FireRedTTS-2, T5Gemma-TTS, FishAudio S1-mini)' {
    & (Join-Path $PSScriptRoot 'setup-wsl-tts-models.ps1') -Model all
  }
} else {
  Write-Step 'WSL zero-shot TTS model setup not requested'
}

Write-Output ''
Write-Output '========== Setup Summary =========='
Write-Output 'Run local-tts.bat for future startup.'
Write-Output 'The public default profile uses Irodori v3. Standard setup also installs Qwen3-TTS Voice Clone 1.7B for reference-voice generation.'
Write-Output 'The standard local-tts.bat setup includes repo-local Irodori and media tools under runtime/ without requiring ComfyUI.'
Write-Output 'Large/generated files are under runtime/ and are ignored by Git.'
Write-Output 'RVC voice models/indexes are user-provided; put their paths in config/config.local.json.'
Write-Output 'GPT-SoVITS pretrained weights may still require the upstream project license/manual steps if the upstream layout changes.'
Write-Output '=================================='

if ($StartAfterSetup) {
  Invoke-SetupCommand 'start stack after setup' {
    & (Join-Path $PSScriptRoot 'start-local-tts-stack.ps1') -ConfigPath $configLocalPath -OpenFrontend -NoGptSovitsStart:$NoGptSovitsStart
  }
}
