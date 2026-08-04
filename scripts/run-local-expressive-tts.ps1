param(
  [Parameter(Mandatory = $true)][string]$RequestJson,
  [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'no-window-process.ps1')
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

if (-not (Test-Path -LiteralPath $RequestJson -PathType Leaf)) {
  throw "request JSON not found: $RequestJson"
}
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$RequestJsonFull = [System.IO.Path]::GetFullPath($RequestJson)
$Request = Get-Content -LiteralPath $RequestJsonFull -Raw -Encoding UTF8 | ConvertFrom-Json
$Model = [string]$Request.model
$EnvironmentKey = switch ($Model) {
  'chatterbox_multilingual_v3' { 'chatterbox' }
  'fun_cosyvoice3_0_5b' { 'cosyvoice' }
  default { throw "unsupported local expressive TTS model: $Model" }
}

$Python = Join-Path $RepoRoot "runtime/venvs/$EnvironmentKey/Scripts/python.exe"
$Runner = Join-Path $PSScriptRoot 'local_expressive_tts_infer.py'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "local expressive TTS environment is not installed: $Python"
}
if (-not (Test-Path -LiteralPath $Runner -PathType Leaf)) {
  throw "local expressive TTS runner not found: $Runner"
}

$OutputFull = [System.IO.Path]::GetFullPath($OutputPath)
$OutputParent = Split-Path -Parent $OutputFull
if (-not (Test-Path -LiteralPath $OutputParent -PathType Container)) {
  New-Item -ItemType Directory -Force -Path $OutputParent | Out-Null
}

$StdoutLog = "$RequestJsonFull.local-expressive.stdout.log"
$StderrLog = "$RequestJsonFull.local-expressive.stderr.log"
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
  throw "local expressive TTS inference failed for $Model`: $Details"
}

if (-not (Test-Path -LiteralPath $OutputFull -PathType Leaf) -or ((Get-Item -LiteralPath $OutputFull).Length -le 44)) {
  throw "local expressive TTS did not create a valid WAV: $OutputFull"
}
