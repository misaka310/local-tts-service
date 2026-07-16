[CmdletBinding()]
param(
    [string]$ConfigPath = "config/config.local.json",
    [switch]$SkipKillPorts,
    [switch]$RunSmoke,
    [switch]$OpenFrontend
)

Write-Warning "start-irodori-stack.ps1 is deprecated. Use local-tts.bat or start-local-tts-stack.ps1."

$params = @{}
if ($PSBoundParameters.ContainsKey('ConfigPath')) { $params['ConfigPath'] = $ConfigPath }
if ($SkipKillPorts) { $params['SkipKillPorts'] = $true }
if ($RunSmoke) { $params['RunSmoke'] = $true }
if ($OpenFrontend) { $params['OpenFrontend'] = $true }

& (Join-Path $PSScriptRoot "start-local-tts-stack.ps1") @params
