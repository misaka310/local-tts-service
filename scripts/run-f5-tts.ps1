param(
  [string]$RequestJson = '',
  [string]$OutputPath = '',
  [switch]$Check
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'no-window-process.ps1')
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$RuntimeRoot = Get-LocalTtsRuntimeRoot -RepoRoot $RepoRoot
$env:LOCAL_TTS_RUNTIME_ROOT = $RuntimeRoot
$Python = Join-Path $RuntimeRoot 'venvs\f5-tts\Scripts\python.exe'
$Runner = Join-Path $PSScriptRoot 'f5_tts_runtime.py'
$PackageRoot = Join-Path $RuntimeRoot 'venvs\f5-tts\Lib\site-packages\f5_tts'
$ModelRoot = Join-Path $RuntimeRoot 'models\f5-tts\JA_21999120'
$requiredPaths = @(
  $Python,
  $Runner,
  (Join-Path $PackageRoot 'infer\infer_cli.py'),
  (Join-Path $PackageRoot 'infer\examples\basic\basic.toml'),
  (Join-Path $PackageRoot 'configs\F5TTS_v1_Base.yaml'),
  (Join-Path $ModelRoot 'model_21999120.pt'),
  (Join-Path $ModelRoot 'vocab_japanese.txt')
)
$missing = @($requiredPaths | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
if ($missing.Count -gt 0) {
  throw "F5-TTS is not prepared. Missing: $($missing -join ', ')"
}
if ($Check) {
  Write-Output '[DONE] F5-TTS Japanese runtime files are present.'
  exit 0
}

if (-not $RequestJson -or -not (Test-Path -LiteralPath $RequestJson -PathType Leaf)) {
  throw "request JSON not found: $RequestJson"
}
if (-not $OutputPath) { throw 'OutputPath is required when generating audio.' }

$RequestJsonFull = [System.IO.Path]::GetFullPath($RequestJson)
$OutputFull = [System.IO.Path]::GetFullPath($OutputPath)
$OutputParent = Split-Path -Parent $OutputFull
if (-not (Test-Path -LiteralPath $OutputParent -PathType Container)) {
  New-Item -ItemType Directory -Force -Path $OutputParent | Out-Null
}

$StdoutLog = "$RequestJsonFull.f5-tts.stdout.log"
$StderrLog = "$RequestJsonFull.f5-tts.stderr.log"
$Arguments = @('-X', 'utf8', $Runner, '--request-json', $RequestJsonFull, '--output-path', $OutputFull)
$Process = Start-LocalTtsNoWindowProcess -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $RepoRoot -StandardOutputPath $StdoutLog -StandardErrorPath $StderrLog -RepoRoot $RepoRoot
$Process.WaitForExit()
$Stdout = ''
$Stderr = ''
if (Test-Path -LiteralPath $StdoutLog) {
  $RawStdout = Get-Content -LiteralPath $StdoutLog -Raw -Encoding UTF8
  if ($null -ne $RawStdout) { $Stdout = [string]$RawStdout }
}
if (Test-Path -LiteralPath $StderrLog) {
  $RawStderr = Get-Content -LiteralPath $StderrLog -Raw -Encoding UTF8
  if ($null -ne $RawStderr) { $Stderr = [string]$RawStderr }
}
if (-not [string]::IsNullOrWhiteSpace($Stdout)) { Write-Output $Stdout.TrimEnd() }
if (-not [string]::IsNullOrWhiteSpace($Stderr)) { [Console]::Error.WriteLine($Stderr.TrimEnd()) }
if ($Process.ExitCode -ne 0) {
  $Details = if (-not [string]::IsNullOrWhiteSpace($Stderr)) { $Stderr.Trim() } elseif (-not [string]::IsNullOrWhiteSpace($Stdout)) { $Stdout.Trim() } else { "exit code $($Process.ExitCode)" }
  throw "F5-TTS inference failed: $Details"
}
if (-not (Test-Path -LiteralPath $OutputFull -PathType Leaf) -or ((Get-Item -LiteralPath $OutputFull).Length -le 44)) {
  throw "F5-TTS did not create a valid WAV: $OutputFull"
}
