[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ConfigPath,
    [Parameter(Mandatory = $true)][string]$ReadyEventName,
    [switch]$NoGptSovitsStart
)

$ErrorActionPreference = 'Stop'
$readyEvent = [Threading.EventWaitHandle]::OpenExisting($ReadyEventName)
try {
    & (Join-Path $PSScriptRoot 'start-local-tts-stack.ps1') -ConfigPath $ConfigPath -StartFrontend -NoGptSovitsStart:$NoGptSovitsStart
    $null = $readyEvent.Set()
    Write-Host '[RUNNING] managed stack host is waiting for the launcher to stop it.'
    $wait = New-Object Threading.ManualResetEvent($false)
    $null = $wait.WaitOne()
}
catch {
    Write-Error $_
    exit 1
}
finally {
    $readyEvent.Dispose()
}
