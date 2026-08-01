[CmdletBinding()]
param(
    [switch]$AllowExistingState,
    [switch]$PreflightOnly,
    [switch]$OpenBrowser,
    [ValidateRange(60, 7200)][int]$TimeoutSec = 1800
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'python-runtime.ps1')
. (Join-Path $PSScriptRoot 'node-runtime.ps1')
. (Join-Path $PSScriptRoot 'clean-install-ports.ps1')

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$configPath = Join-Path $repoRoot 'config/config.local.json'
$configExamplePath = Join-Path $repoRoot 'config/config.example.json'
$venvPath = Join-Path $repoRoot '.venv'
$frontendModulesPath = Join-Path $repoRoot 'frontend/node_modules'
$modelRoot = Join-Path $repoRoot 'runtime/models/huggingface'
$defaultModelId = 'irodori_v3'
$qwenCloneModelId = 'qwen3_tts_clone_1_7b'
$modelDirectory = Join-Path $modelRoot 'Qwen__Qwen3-TTS-12Hz-1.7B-Base'
$reportDirectory = Join-Path $repoRoot 'runtime/clean-install-verification'
$reportPath = Join-Path $reportDirectory 'clean-install-report.json'
$audioPath = Join-Path $reportDirectory 'generated.wav'
$qwenCloneAudioPath = Join-Path $reportDirectory 'generated-qwen-clone.wav'
$qwenReferenceVoiceId = 'ci_qwen_clone_reference'
$qwenReferenceVoiceDirectory = Join-Path $repoRoot "reference/voices/$qwenReferenceVoiceId"
$qwenCloneText = '"\u3053\u308c\u306f\u58f0\u3092\u8907\u88fd\u3057\u305f\u97f3\u58f0\u751f\u6210\u30c6\u30b9\u30c8\u3067\u3059\u3002"' | ConvertFrom-Json
$startedAt = Get-Date
$canWriteReport = $false

$report = [ordered]@{
    schemaVersion = 1
    startedAtUtc = $startedAt.ToUniversalTime().ToString('o')
    finishedAtUtc = $null
    pass = $false
    stage = 'preflight'
    error = $null
    machine = [ordered]@{
        os = [System.Environment]::OSVersion.VersionString
        computerName = $env:COMPUTERNAME
        python = $null
        node = $null
        npm = $null
        nvidiaGpu = $null
        torch = $null
        torchaudio = $null
        cudaAvailable = $null
        cudaDevice = $null
    }
    setup = [ordered]@{
        configCreated = $false
        defaultModel = $null
        modelDirectory = $modelDirectory
        modelDownloaded = $false
    }
    runtime = [ordered]@{
        backendPort = $null
        frontendPort = $null
        frontendBaseUrl = $null
        healthStatus = $null
        modelAvailable = $false
    }
    generation = [ordered]@{
        audioUrl = $null
        audioPath = $audioPath
        bytes = 0
        sha256 = $null
        riffHeader = $false
    }
    qwenCloneGeneration = [ordered]@{
        model = $qwenCloneModelId
        runtime = $null
        referenceVoiceId = $qwenReferenceVoiceId
        referenceText = $null
        referenceDurationSec = $null
        text = $qwenCloneText
        audioUrl = $null
        audioPath = $qwenCloneAudioPath
        bytes = 0
        sha256 = $null
        riffHeader = $false
    }
}

function Assert-CommandAvailable {
    param([Parameter(Mandatory = $true)][string]$Command)
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "Required command was not found: $Command"
    }
}

function Resolve-BootstrapPython {
    param([switch]$AllowExisting)

    $existingVenvPython = Join-Path $venvPath 'Scripts/python.exe'
    if ($AllowExisting -and (Test-LocalTtsPython311 -PythonPath $existingVenvPython)) {
        return $existingVenvPython
    }

    $runtime = Install-LocalTtsManagedPythonRuntime -RepoRoot $repoRoot
    return $runtime.PythonPath
}

function Assert-CleanState {
    param([switch]$AllowExisting)

    if ($AllowExisting) {
        Write-Host '[WARN] Existing-state checks are bypassed. This run is not proof of a clean installation.' -ForegroundColor Yellow
        return
    }

    $unexpectedPaths = @(
        $configPath,
        $venvPath,
        $frontendModulesPath,
        $modelRoot
    ) | Where-Object { Test-Path -LiteralPath $_ }

    if ($unexpectedPaths.Count -gt 0) {
        throw ("This checkout is not clean. Use a fresh clone on another Windows installation. Existing paths:`n- " + ($unexpectedPaths -join "`n- "))
    }

}

function Get-CommandVersion {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()
    try {
        $process = Start-Process -FilePath $Command -ArgumentList $Arguments -Wait -PassThru -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        $stdout = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue } else { '' }
        $stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue } else { '' }
        $output = (($stdout, $stderr) -join "`n").Trim()
        if ($process.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($output)) {
            throw "Version check failed: $Command $($Arguments -join ' ')"
        }
        return $output
    }
    finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Save-Report {
    $report.finishedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
    New-Item -ItemType Directory -Force -Path $reportDirectory | Out-Null
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
}

function Invoke-JsonRequest {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('Get', 'Post')][string]$Method,
        [Parameter(Mandatory = $true)][string]$Uri,
        [object]$Body = $null
    )

    if ($Method -eq 'Get') {
        return Invoke-RestMethod -Method Get -Uri $Uri -TimeoutSec $TimeoutSec -ErrorAction Stop
    }

    $json = $Body | ConvertTo-Json -Depth 8
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    return Invoke-RestMethod -Method Post -Uri $Uri -Body $bytes -ContentType 'application/json; charset=utf-8' -TimeoutSec $TimeoutSec -ErrorAction Stop
}

try {
    Write-Host '========== Clean-install verification ==========' -ForegroundColor Cyan
    Assert-CleanState -AllowExisting:$AllowExistingState
    $bootstrapPython = Resolve-BootstrapPython -AllowExisting:$AllowExistingState
    if (-not (Test-Path -LiteralPath $configExamplePath -PathType Leaf)) {
        throw "Public configuration template not found: $configExamplePath"
    }

    $report.machine.python = Get-CommandVersion -Command $bootstrapPython -Arguments @('--version')
    if ($report.machine.python -notmatch '^Python 3\.11\.') {
        throw "Python 3.11 is required. Detected: $($report.machine.python)"
    }
    if (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue) {
        $gpuOutput = & nvidia-smi.exe --query-gpu=name,driver_version --format=csv,noheader 2>&1
        if ($LASTEXITCODE -eq 0) {
            $report.machine.nvidiaGpu = (($gpuOutput | Out-String).Trim())
        }
    }

    $canWriteReport = $true
    if ($PreflightOnly) {
        $report.stage = 'preflight-only'
        $report.pass = $true
        Save-Report
        Write-Host "[PASS] Preflight completed. This does not prove model download or generation." -ForegroundColor Green
        Write-Host "report: $reportPath"
        exit 0
    }

    New-Item -ItemType Directory -Force -Path $reportDirectory | Out-Null
    $env:PIP_NO_CACHE_DIR = '1'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $env:npm_config_cache = Join-Path $reportDirectory 'npm-cache'

    $report.stage = 'setup'
    & (Join-Path $PSScriptRoot 'setup-local-tts.ps1') `
        -PythonExecutable $bootstrapPython `
        -DownloadQwenModels `
        -QwenDefaultModelOnly `
        -SetupIrodori `
        -SkipVendorSetup `
        -SkipMediaToolsInstall `
        -NoGptSovitsStart
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "setup-local-tts.ps1 failed with exit code $LASTEXITCODE"
    }

    $nodeRuntime = Resolve-LocalTtsNodeRuntime -RepoRoot $repoRoot
    $report.machine.node = Get-CommandVersion -Command $nodeRuntime.NodePath -Arguments @('--version')
    if ($report.machine.node -notmatch '^v?(\d+)\.' -or [int]$Matches[1] -lt 18) {
        throw "Node.js 18 or newer is required. Detected: $($report.machine.node)"
    }
    $report.machine.npm = Get-CommandVersion -Command $nodeRuntime.NpmPath -Arguments @('--version')

    $venvPython = Join-Path $venvPath 'Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        throw "Python venv was not created: $venvPython"
    }
    $torchStdoutPath = [System.IO.Path]::GetTempFileName()
    $torchStderrPath = [System.IO.Path]::GetTempFileName()
    $torchProbePath = [System.IO.Path]::GetTempFileName()
    try {
        @'
import json
import torch
import torchaudio

print(json.dumps({
    "torchVersion": torch.__version__,
    "torchaudioVersion": torchaudio.__version__,
    "cudaAvailable": torch.cuda.is_available(),
    "cudaDevice": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
}))
'@ | Set-Content -LiteralPath $torchProbePath -Encoding UTF8

        $torchProcess = Start-Process -FilePath $venvPython `
            -ArgumentList @($torchProbePath) `
            -Wait `
            -PassThru `
            -NoNewWindow `
            -RedirectStandardOutput $torchStdoutPath `
            -RedirectStandardError $torchStderrPath
        $torchStdout = if (Test-Path -LiteralPath $torchStdoutPath) { Get-Content -LiteralPath $torchStdoutPath -Raw -ErrorAction SilentlyContinue } else { '' }
        $torchStderr = if (Test-Path -LiteralPath $torchStderrPath) { Get-Content -LiteralPath $torchStderrPath -Raw -ErrorAction SilentlyContinue } else { '' }
        if ($torchProcess.ExitCode -ne 0) {
            $torchFailureDetails = if (-not [string]::IsNullOrWhiteSpace($torchStderr)) {
                $torchStderr.Trim()
            }
            elseif (-not [string]::IsNullOrWhiteSpace($torchStdout)) {
                $torchStdout.Trim()
            }
            else {
                '(no stdout or stderr was produced)'
            }
            throw "PyTorch verification failed with exit code $($torchProcess.ExitCode):`n$torchFailureDetails"
        }
        if ([string]::IsNullOrWhiteSpace($torchStdout)) {
            throw 'PyTorch verification succeeded but returned no JSON on stdout.'
        }
        try {
            $torchInfo = $torchStdout.Trim() | ConvertFrom-Json
        }
        catch {
            throw "PyTorch verification returned invalid JSON:`n$($torchStdout.Trim())`n$($_.Exception.Message)"
        }
    }
    finally {
        Remove-Item -LiteralPath $torchStdoutPath, $torchStderrPath, $torchProbePath -Force -ErrorAction SilentlyContinue
    }
    $report.machine.torch = [string]$torchInfo.torchVersion
    $report.machine.torchaudio = [string]$torchInfo.torchaudioVersion
    $report.machine.cudaAvailable = [bool]$torchInfo.cudaAvailable
    $report.machine.cudaDevice = [string]$torchInfo.cudaDevice
    $expectedTorchVersion = if ($report.machine.nvidiaGpu) { '2.8.0+cu128' } else { '2.8.0+cpu' }
    if ($report.machine.torch -ne $expectedTorchVersion -or $report.machine.torchaudio -ne $expectedTorchVersion) {
        throw "Unexpected PyTorch pair. Expected torch/torchaudio $expectedTorchVersion, got $($report.machine.torch) / $($report.machine.torchaudio)"
    }
    if ($report.machine.nvidiaGpu -and -not $report.machine.cudaAvailable) {
        throw 'NVIDIA GPU was detected, but the installed PyTorch cannot use CUDA.'
    }

    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        throw 'config/config.local.json was not created from config/config.example.json'
    }
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $verificationPorts = @(Get-FreeTcpPorts -Count 2)
    if ($verificationPorts.Count -ne 2) {
        throw 'Could not allocate isolated verification ports.'
    }
    $backendPort = [int]$verificationPorts[0]
    $frontendPort = [int]$verificationPorts[1]
    Set-CleanVerificationPorts -Config $config -ConfigPath $configPath -BackendPort $backendPort -FrontendPort $frontendPort
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $report.runtime.backendPort = $backendPort
    $report.runtime.frontendPort = $frontendPort
    Write-Host "[INFO] Isolated verification ports: backend=$backendPort frontend=$frontendPort"
    $report.setup.configCreated = $true
    $report.setup.defaultModel = [string]$config.defaultModel
    if ($report.setup.defaultModel -ne $defaultModelId) {
        throw "Unexpected default model: $($report.setup.defaultModel)"
    }
    if (-not (Test-Path -LiteralPath $modelDirectory -PathType Container)) {
        throw "Qwen model directory was not downloaded: $modelDirectory"
    }
    $report.setup.modelDownloaded = $true

    $report.stage = 'backend-start'
    & (Join-Path $PSScriptRoot 'start-local-tts-stack.ps1') -ConfigPath $configPath -NoGptSovitsStart
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "start-local-tts-stack.ps1 failed with exit code $LASTEXITCODE"
    }

    $report.stage = 'frontend-start'
    & (Join-Path $PSScriptRoot 'start-tts-frontend.ps1') -ConfigPath $configPath -NoInstall
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "start-tts-frontend.ps1 failed with exit code $LASTEXITCODE"
    }

    $frontHost = if ($config.frontend.host) { [string]$config.frontend.host } else { '127.0.0.1' }
    $frontPort = [int]$config.frontend.port
    $frontBase = "http://$frontHost`:$frontPort"
    $report.runtime.frontendBaseUrl = $frontBase

    $report.stage = 'health'
    $health = Invoke-JsonRequest -Method Get -Uri "$frontBase/api/health"
    if (-not $health.ok) {
        throw 'Frontend health returned ok=false'
    }
    $report.runtime.healthStatus = [string]$health.health.status

    $models = Invoke-JsonRequest -Method Get -Uri "$frontBase/api/models"
    $defaultModel = @($models.models) | Where-Object { $_.id -eq $defaultModelId -or $_.model -eq $defaultModelId } | Select-Object -First 1
    if ($null -eq $defaultModel) {
        throw "Default model is missing from /api/models: $defaultModelId"
    }
    if (-not [bool]$defaultModel.available -or -not [bool]$defaultModel.enabled) {
        throw "Default model is unavailable: $($defaultModel.unavailableReason)"
    }
    $qwenCloneModel = @($models.models) | Where-Object { $_.id -eq $qwenCloneModelId -or $_.model -eq $qwenCloneModelId } | Select-Object -First 1
    if ($null -eq $qwenCloneModel) {
        throw "Qwen clone model is missing from /api/models: $qwenCloneModelId"
    }
    if (-not [bool]$qwenCloneModel.available -or -not [bool]$qwenCloneModel.enabled) {
        throw "Qwen clone model is unavailable: $($qwenCloneModel.unavailableReason)"
    }
    $report.runtime.modelAvailable = $true

    $report.stage = 'generation'
    $verificationText = '"\u30af\u30ea\u30fc\u30f3\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u306e\u97f3\u58f0\u751f\u6210\u30c6\u30b9\u30c8\u3067\u3059\u3002"' | ConvertFrom-Json
    $speakPayload = [ordered]@{
        model = $defaultModelId
        text = $verificationText
        language = 'Japanese'
        seed = 260711
        format = 'wav'
    }
    $speak = Invoke-JsonRequest -Method Post -Uri "$frontBase/api/speak" -Body $speakPayload
    if (-not $speak.ok) {
        throw 'Speech generation returned ok=false'
    }
    $result = if ($null -ne $speak.result) { $speak.result } else { $speak }
    $audioUrl = [string]$result.audioUrl
    if ([string]::IsNullOrWhiteSpace($audioUrl)) {
        throw 'Speech generation did not return audioUrl'
    }
    $report.generation.audioUrl = $audioUrl

    $audioUri = if ([System.Uri]::IsWellFormedUriString($audioUrl, [System.UriKind]::Absolute)) {
        [System.Uri]$audioUrl
    }
    else {
        [System.Uri]::new([System.Uri]("$frontBase/"), $audioUrl.TrimStart('/'))
    }

    New-Item -ItemType Directory -Force -Path $reportDirectory | Out-Null
    Invoke-WebRequest -Uri $audioUri.AbsoluteUri -OutFile $audioPath -TimeoutSec $TimeoutSec -ErrorAction Stop | Out-Null
    $audioBytes = [System.IO.File]::ReadAllBytes($audioPath)
    $report.generation.bytes = $audioBytes.Length
    if ($audioBytes.Length -le 44) {
        throw "Generated WAV is too small: $($audioBytes.Length) bytes"
    }
    $riff = [System.Text.Encoding]::ASCII.GetString($audioBytes, 0, 4)
    $report.generation.riffHeader = ($riff -eq 'RIFF')
    if (-not $report.generation.riffHeader) {
        throw "Generated file is not a RIFF WAV: header=$riff"
    }
    $report.generation.sha256 = (Get-FileHash -LiteralPath $audioPath -Algorithm SHA256).Hash.ToLowerInvariant()

    $report.stage = 'qwen-reference-registration'
    if (Test-Path -LiteralPath $qwenReferenceVoiceDirectory) {
        Remove-Item -LiteralPath $qwenReferenceVoiceDirectory -Recurse -Force
    }
    $referenceDataUrl = 'data:audio/wav;base64,' + [Convert]::ToBase64String($audioBytes)
    $referenceRegistration = Invoke-JsonRequest -Method Post -Uri "$frontBase/api/reference-voices" -Body ([ordered]@{
        voiceId = $qwenReferenceVoiceId
        referenceText = $verificationText
        dataUrl = $referenceDataUrl
        mimeType = 'audio/wav'
    })
    if (-not $referenceRegistration.ok) {
        throw 'Qwen reference voice registration returned ok=false'
    }
    $registeredVoice = $referenceRegistration.voice
    if ([string]$registeredVoice.voiceId -ne $qwenReferenceVoiceId) {
        throw "Unexpected registered reference voice ID: $($registeredVoice.voiceId)"
    }
    if (-not [bool]$registeredVoice.hasReferenceAudio -or -not [bool]$registeredVoice.hasReferenceText) {
        throw 'Registered Qwen reference voice is missing audio or transcript'
    }
    $referenceDurationSec = [double]$registeredVoice.audioDurationSec
    if ($referenceDurationSec -lt 3 -or $referenceDurationSec -gt 10) {
        throw "Qwen reference voice duration must be between 3 and 10 seconds: $referenceDurationSec"
    }
    $report.qwenCloneGeneration.referenceText = $verificationText
    $report.qwenCloneGeneration.referenceDurationSec = $referenceDurationSec

    $report.stage = 'qwen-clone-generation'
    $qwenSpeak = Invoke-JsonRequest -Method Post -Uri "$frontBase/api/speak" -Body ([ordered]@{
        model = $qwenCloneModelId
        voiceId = $qwenReferenceVoiceId
        text = $qwenCloneText
        language = 'Japanese'
        seed = 260712
        format = 'wav'
    })
    if (-not $qwenSpeak.ok) {
        throw 'Qwen voice-clone generation returned ok=false'
    }
    $qwenResult = if ($null -ne $qwenSpeak.result) { $qwenSpeak.result } else { $qwenSpeak }
    if ([string]$qwenResult.model -ne $qwenCloneModelId) {
        throw "Unexpected Qwen voice-clone model: $($qwenResult.model)"
    }
    if ([string]$qwenResult.runtime -ne 'qwen3_tts') {
        throw "Unexpected Qwen voice-clone runtime: $($qwenResult.runtime)"
    }
    if ([string]$qwenResult.voiceId -ne $qwenReferenceVoiceId) {
        throw "Unexpected Qwen voice-clone reference voice: $($qwenResult.voiceId)"
    }
    $qwenAudioUrl = [string]$qwenResult.audioUrl
    if ([string]::IsNullOrWhiteSpace($qwenAudioUrl)) {
        throw 'Qwen voice-clone generation did not return audioUrl'
    }
    $report.qwenCloneGeneration.runtime = [string]$qwenResult.runtime
    $report.qwenCloneGeneration.audioUrl = $qwenAudioUrl

    $qwenAudioUri = if ([System.Uri]::IsWellFormedUriString($qwenAudioUrl, [System.UriKind]::Absolute)) {
        [System.Uri]$qwenAudioUrl
    }
    else {
        [System.Uri]::new([System.Uri]("$frontBase/"), $qwenAudioUrl.TrimStart('/'))
    }
    Invoke-WebRequest -Uri $qwenAudioUri.AbsoluteUri -OutFile $qwenCloneAudioPath -TimeoutSec $TimeoutSec -ErrorAction Stop | Out-Null
    $qwenAudioBytes = [System.IO.File]::ReadAllBytes($qwenCloneAudioPath)
    $report.qwenCloneGeneration.bytes = $qwenAudioBytes.Length
    if ($qwenAudioBytes.Length -le 44) {
        throw "Generated Qwen voice-clone WAV is too small: $($qwenAudioBytes.Length) bytes"
    }
    $qwenRiff = [System.Text.Encoding]::ASCII.GetString($qwenAudioBytes, 0, 4)
    $report.qwenCloneGeneration.riffHeader = ($qwenRiff -eq 'RIFF')
    if (-not $report.qwenCloneGeneration.riffHeader) {
        throw "Generated Qwen voice-clone file is not a RIFF WAV: header=$qwenRiff"
    }
    $report.qwenCloneGeneration.sha256 = (Get-FileHash -LiteralPath $qwenCloneAudioPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($report.qwenCloneGeneration.sha256 -eq $report.generation.sha256) {
        throw 'Qwen voice-clone output unexpectedly matches the reference WAV byte-for-byte'
    }
    Remove-Item -LiteralPath $qwenReferenceVoiceDirectory -Recurse -Force -ErrorAction SilentlyContinue

    $report.stage = 'complete'
    $report.pass = $true
    Save-Report

    Write-Host '[PASS] Fresh dependency install, Irodori generation, and Qwen voice-clone generation succeeded.' -ForegroundColor Green
    Write-Host "irodori audio: $audioPath"
    Write-Host "qwen clone audio: $qwenCloneAudioPath"
    Write-Host "report: $reportPath"
    if ($OpenBrowser) {
        Start-Process $frontBase
    }
    exit 0
}
catch {
    Remove-Item -LiteralPath $qwenReferenceVoiceDirectory -Recurse -Force -ErrorAction SilentlyContinue
    $report.error = $_.Exception.Message
    $report.stage = "failed:$($report.stage)"
    if ($canWriteReport) {
        Save-Report
        Write-Host "report: $reportPath" -ForegroundColor Yellow
    }
    Write-Error $_.Exception.Message
    exit 1
}
