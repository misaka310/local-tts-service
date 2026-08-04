param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('chatterbox', 'cosyvoice')]
  [string]$Model
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'no-window-process.ps1')
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$Python = Join-Path $RepoRoot "runtime/venvs/$Model/Scripts/python.exe"
$Checker = Join-Path $PSScriptRoot 'check_local_expressive_tts.py'

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "Dedicated Python environment is missing: $Python"
}
if (-not (Test-Path -LiteralPath $Checker -PathType Leaf)) {
  throw "Availability checker is missing: $Checker"
}

$StdoutLog = Join-Path $RepoRoot "runtime/logs/check-local-expressive-$Model.stdout.log"
$StderrLog = Join-Path $RepoRoot "runtime/logs/check-local-expressive-$Model.stderr.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $StdoutLog) | Out-Null
$Arguments = @('-X', 'utf8', $Checker, '--model', $Model, '--repo-root', [string]$RepoRoot)
$Process = Start-LocalTtsNoWindowProcess -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $RepoRoot -StandardOutputPath $StdoutLog -StandardErrorPath $StderrLog -RepoRoot $RepoRoot
$Process.WaitForExit()
$Stdout = if (Test-Path -LiteralPath $StdoutLog) { [string](Get-Content -LiteralPath $StdoutLog -Raw -Encoding UTF8) } else { '' }
$Stderr = if (Test-Path -LiteralPath $StderrLog) { [string](Get-Content -LiteralPath $StderrLog -Raw -Encoding UTF8) } else { '' }
if ($Process.ExitCode -ne 0) {
  $Details = if ($Stderr.Trim()) { $Stderr.Trim() } elseif ($Stdout.Trim()) { $Stdout.Trim() } else { "exit code $($Process.ExitCode)" }
  throw "Availability verification failed for $Model`: $Details"
}
Write-Output $Stdout.Trim()
