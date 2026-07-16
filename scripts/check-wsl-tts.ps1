param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('sarashina2_2_tts', 'fireredtts2', 't5gemma_tts_2b_2b', 'fish_s1_mini')]
  [string]$Model
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

function Convert-ToWslPath {
  param([Parameter(Mandatory = $true)][string]$WindowsPath)
  $full = [System.IO.Path]::GetFullPath($WindowsPath)
  $root = [System.IO.Path]::GetPathRoot($full)
  if (-not $root -or $root.Length -lt 2 -or $root[1] -ne ':') {
    throw "unsupported Windows path for WSL: $full"
  }
  $drive = $root[0].ToString().ToLowerInvariant()
  $relative = $full.Substring($root.Length).Replace('\', '/')
  return "/mnt/$drive/$relative"
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
  throw 'WSL is not installed or wsl.exe is unavailable.'
}

$CheckScript = Join-Path $PSScriptRoot 'check_wsl_tts.sh'
if (-not (Test-Path -LiteralPath $CheckScript -PathType Leaf)) {
  throw "WSL model check script not found: $CheckScript"
}
$CheckScriptWsl = Convert-ToWslPath $CheckScript

$StdoutLog = [System.IO.Path]::GetTempFileName()
$StderrLog = [System.IO.Path]::GetTempFileName()
try {
  $Arguments = @('--exec', 'bash', $CheckScriptWsl, $Model)
  $Process = Start-Process -FilePath 'wsl.exe' -ArgumentList $Arguments -RedirectStandardOutput $StdoutLog -RedirectStandardError $StderrLog -WindowStyle Hidden -PassThru -Wait
  [string]$Stdout = if (Test-Path -LiteralPath $StdoutLog) { Get-Content -LiteralPath $StdoutLog -Raw -Encoding UTF8 } else { '' }
  [string]$Stderr = if (Test-Path -LiteralPath $StderrLog) { Get-Content -LiteralPath $StderrLog -Raw -Encoding UTF8 } else { '' }
  if ($Stdout.Trim()) { Write-Output $Stdout.Trim() }
  if ($Process.ExitCode -ne 0) {
    $Details = if ($Stderr.Trim()) { $Stderr.Trim() } elseif ($Stdout.Trim()) { $Stdout.Trim() } else { "exit code $($Process.ExitCode)" }
    [Console]::Error.WriteLine($Details)
    exit $Process.ExitCode
  }
} finally {
  Remove-Item -LiteralPath $StdoutLog -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $StderrLog -Force -ErrorAction SilentlyContinue
}
