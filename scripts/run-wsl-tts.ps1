param(
  [Parameter(Mandatory = $true)][string]$RequestJson,
  [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'no-window-process.ps1')
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
  throw 'WSL is not installed or wsl.exe is not available.'
}
if (-not (Test-Path -LiteralPath $RequestJson -PathType Leaf)) {
  throw "request JSON not found: $RequestJson"
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$Req = Get-Content -LiteralPath $RequestJson -Raw -Encoding UTF8 | ConvertFrom-Json
$Model = [string]$Req.model
if ($Model -notin @('sarashina2_2_tts', 'fireredtts2', 't5gemma_tts_2b_2b', 'fish_s1_mini', 'orpheus_3b_asmr', 'ming_omni_tts_0_5b')) {
  throw "unsupported WSL TTS model: $Model"
}

$ReferenceAudioWsl = if ([string]$Req.referenceAudioPath) { Convert-ToWslPath ([string]$Req.referenceAudioPath) } else { '' }
$ReferenceTextWsl = if ([string]$Req.referenceTextPath) { Convert-ToWslPath ([string]$Req.referenceTextPath) } else { '' }
$OutputFull = [System.IO.Path]::GetFullPath($OutputPath)
$OutputParent = Split-Path -Parent $OutputFull
if (-not (Test-Path -LiteralPath $OutputParent -PathType Container)) {
  New-Item -ItemType Directory -Force -Path $OutputParent | Out-Null
}
$OutputWsl = Convert-ToWslPath $OutputFull
$CliWsl = Convert-ToWslPath (Join-Path $RepoRoot 'scripts/wsl_tts_cli.py')
$ShellWsl = Convert-ToWslPath (Join-Path $RepoRoot 'scripts/run_wsl_tts.sh')
$RepoWsl = Convert-ToWslPath ([string]$RepoRoot)

$Req | Add-Member -NotePropertyName referenceAudioPath -NotePropertyValue $ReferenceAudioWsl -Force
$Req | Add-Member -NotePropertyName referenceTextPath -NotePropertyValue $ReferenceTextWsl -Force
$Req | Add-Member -NotePropertyName outputPath -NotePropertyValue $OutputWsl -Force
$ConvertedJson = "$RequestJson.wsl.json"
$StdoutLog = "$RequestJson.wsl.stdout.log"
$StderrLog = "$RequestJson.wsl.stderr.log"
[System.IO.File]::WriteAllText($ConvertedJson, ($Req | ConvertTo-Json -Depth 12), $Utf8NoBom)
$ConvertedJsonWsl = Convert-ToWslPath $ConvertedJson
$Succeeded = $false

try {
  $RawArgs = @('--exec', 'bash', $ShellWsl, $Model, $RepoWsl, $CliWsl, $ConvertedJsonWsl, $OutputWsl)
  $WslExe = (Get-Command wsl.exe -ErrorAction Stop).Source
  $Process = Start-LocalTtsNoWindowProcess -FilePath $WslExe -ArgumentList $RawArgs -WorkingDirectory $RepoRoot -StandardOutputPath $StdoutLog -StandardErrorPath $StderrLog -RepoRoot $RepoRoot
  $Process.WaitForExit()
  $Stdout = if (Test-Path -LiteralPath $StdoutLog) { [string](Get-Content -LiteralPath $StdoutLog -Raw -Encoding UTF8) } else { '' }
  $Stderr = if (Test-Path -LiteralPath $StderrLog) { [string](Get-Content -LiteralPath $StderrLog -Raw -Encoding UTF8) } else { '' }
  if ($Stdout) { Write-Output $Stdout.TrimEnd() }
  if ($Process.ExitCode -ne 0) {
    $Details = if ($Stderr.Trim()) { $Stderr.Trim() } elseif ($Stdout.Trim()) { $Stdout.Trim() } else { "exit code $($Process.ExitCode)" }
    throw "WSL TTS inference failed for $Model. Diagnostics retained: request=$ConvertedJson stdout=$StdoutLog stderr=$StderrLog`n$Details"
  }
  $Succeeded = $true
} finally {
  if ($Succeeded) {
    Remove-Item -LiteralPath $ConvertedJson -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $StdoutLog -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $StderrLog -Force -ErrorAction SilentlyContinue
  }
}

if (-not (Test-Path -LiteralPath $OutputFull -PathType Leaf) -or ((Get-Item -LiteralPath $OutputFull).Length -le 44)) {
  throw "WSL TTS did not create a valid WAV: $OutputFull"
}