[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$Port = 8731)
$ErrorActionPreference = 'Stop'
$repoRoot = [string](Resolve-Path (Join-Path $PSScriptRoot '..'))
. (Join-Path $PSScriptRoot 'no-window-process.ps1')
. (Join-Path $PSScriptRoot 'managed-processes.ps1')
$python = Join-Path $repoRoot 'runtime/venv-qwen-rocm/Scripts/python.exe'
$workerScript = Join-Path $repoRoot 'scripts/qwen-rocm-worker.py'
$healthUrl = "http://127.0.0.1:$Port/api/health"
function Test-QwenRocmReady {
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3 -ErrorAction Stop
        return ($response.ok -eq $true -and [string]$response.gpu -eq 'R9700')
    }
    catch {
        return $false
    }
}
if (Test-QwenRocmReady) {
    Write-Host "[INFO] R9700 Qwen worker already running at $healthUrl"
    exit 0
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Qwen ROCm venv missing; see docs/qwen-rocm.md (no CPU fallback)'
}
if (-not (Test-Path -LiteralPath $workerScript -PathType Leaf)) {
    throw 'Qwen ROCm worker script missing'
}
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    throw "Port $Port already in use by an unhealthy service; will not terminate it"
}
$logDir = Join-Path $repoRoot 'runtime/logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$process = Start-LocalTtsNoWindowProcess -FilePath $python -ArgumentList @('-u', $workerScript, '--port', [string]$Port) -WorkingDirectory $repoRoot -StandardOutputPath (Join-Path $logDir 'qwen-rocm-worker.out.log') -StandardErrorPath (Join-Path $logDir 'qwen-rocm-worker.err.log') -RepoRoot $repoRoot
$null = Register-ManagedProcess -RepoRoot $repoRoot -Service 'qwen-rocm' -Process $process -ExpectedCommandFragments @('qwen-rocm-worker.py','--port',[string]$Port) -HealthUrl $healthUrl -Port $Port
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if (Test-QwenRocmReady) {
        Write-Host "[DONE] R9700 Qwen worker ready (pid=$($process.Id))"
        exit 0
    }
    if ($process.HasExited) { break }
    Start-Sleep -Seconds 1
}
throw 'Qwen ROCm worker did not become ready; see runtime/logs/qwen-rocm-worker.err.log'
