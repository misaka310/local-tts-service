[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateRange(1, 3650)][int]$OlderThanDays = 30,
    [ValidateRange(1, 1000)][int]$KeepRecent = 20,
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtimeRoot = (Join-Path $repoRoot 'runtime')
$cutoff = (Get-Date).AddDays(-$OlderThanDays)
$roots = @(
    (Join-Path $runtimeRoot 'audio\chunks'),
    (Join-Path $runtimeRoot 'rvc\intermediate'),
    (Join-Path $runtimeRoot 'rvc\output')
)

$candidates = foreach ($root in $roots) {
    if (-not (Test-Path -LiteralPath $root)) { continue }
    $resolvedRoot = (Resolve-Path -LiteralPath $root).Path
    Get-ChildItem -LiteralPath $resolvedRoot -File -Recurse |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $KeepRecent |
        Where-Object { $_.LastWriteTime -lt $cutoff -and $_.FullName.StartsWith($resolvedRoot, [StringComparison]::OrdinalIgnoreCase) }
}

if (-not $candidates) {
    Write-Host 'No old runtime artifacts matched the cleanup policy.'
    exit 0
}

$candidates | ForEach-Object { Write-Host ("{0}  {1}" -f $_.LastWriteTime.ToString('s'), $_.FullName) }
if (-not $Apply) {
    Write-Host 'Dry run only. Re-run with -Apply to delete the listed files.'
    exit 0
}

foreach ($file in $candidates) {
    if ($PSCmdlet.ShouldProcess($file.FullName, 'Delete old runtime artifact')) {
        Remove-Item -LiteralPath $file.FullName -Force
    }
}
