param(
  [ValidateRange(24, 48)][int]$MemoryGB = 32,
  [ValidateRange(8, 32)][int]$SwapGB = 16,
  [switch]$Apply,
  [switch]$RestartWSL
)

$ErrorActionPreference = 'Stop'
$Path = Join-Path $env:USERPROFILE '.wslconfig'
$HostGB = [math]::Floor((Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize / 1MB)
if ($HostGB -lt ($MemoryGB + 24)) {
  throw "Not enough physical RAM for WSL $MemoryGB GB plus 24 GB host reserve: detected $HostGB GB."
}
if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
  throw "Existing .wslconfig is absent. Refusing to create unreviewed global configuration."
}
$Current = [System.IO.File]::ReadAllText($Path)
if ($Current -notmatch '(?m)^memory=16GB\s*$' -or $Current -notmatch '(?m)^swap=4GB\s*$') {
  throw "Existing WSL settings differ from the audited 16GB / 4GB configuration; review manually."
}
$Updated = $Current.Replace('memory=16GB', "memory=${MemoryGB}GB").Replace('swap=4GB', "swap=${SwapGB}GB")
Write-Host "Existing WSL memory 16GB + 4GB swap; proposed ${MemoryGB}GB + ${SwapGB}GB swap."
Write-Host "All WSL 2 distributions will be briefly stopped if RestartWSL is requested."
if (-not $Apply) {
  Write-Host 'Dry run; rerun with -Apply and -RestartWSL only when no unrelated WSL jobs are active.'
  exit 0
}
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Backup = "$Path.before-fish-s2-$Stamp"
[System.IO.File]::Copy($Path, $Backup, $false)
$Temp = "$Path.new-$Stamp"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($Temp, $Updated, $Utf8NoBom)
if ([System.IO.File]::ReadAllText($Path) -ne $Current) {
  Remove-Item -LiteralPath $Temp -Force
  throw 'A concurrent WSL config change was detected. Existing configuration was not replaced.'
}
Move-Item -LiteralPath $Temp -Destination $Path -Force
Write-Host "WSL resource config updated. Backup: $Backup"
if ($RestartWSL) {
  & wsl.exe --shutdown
  if ($LASTEXITCODE -ne 0) { throw "WSL shutdown failed: $LASTEXITCODE" }
  & wsl.exe --exec bash -lc 'free -h'
  if ($LASTEXITCODE -ne 0) { throw "WSL memory verification failed: $LASTEXITCODE" }
}
