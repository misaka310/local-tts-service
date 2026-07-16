$ErrorActionPreference = 'Stop'

$repoRoot = [string](Resolve-Path (Join-Path $PSScriptRoot '..'))
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) { $python = $command.Source }
    else { throw 'Python 3 executable was not found. Run local-tts.bat -ForceSetup first.' }
}

$scriptPath = Join-Path $PSScriptRoot 'test_public_history_audit.py'
$runId = [Guid]::NewGuid().ToString('N')
$stdoutPath = Join-Path ([System.IO.Path]::GetTempPath()) "local-tts-audit-test-$runId.out.txt"
$stderrPath = Join-Path ([System.IO.Path]::GetTempPath()) "local-tts-audit-test-$runId.err.txt"
try {
    $process = Start-Process -FilePath $python -ArgumentList @('"' + $scriptPath + '"') -WorkingDirectory $repoRoot -Wait -PassThru -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    if (Test-Path -LiteralPath $stdoutPath) {
        Get-Content -LiteralPath $stdoutPath -Encoding UTF8 | Write-Host
    }
    if (Test-Path -LiteralPath $stderrPath) {
        Get-Content -LiteralPath $stderrPath -Encoding UTF8 | Write-Host
    }
    if ($process.ExitCode -ne 0) { exit $process.ExitCode }
}
finally {
    Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
}
