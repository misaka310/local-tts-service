$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'clean-install-ports.ps1')

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("local-tts-clean-ports-" + [guid]::NewGuid().ToString('N'))
$configPath = Join-Path $tempRoot 'config.local.json'
try {
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    $config = @{
        port = 8730
        corsAllowedOrigins = @('http://127.0.0.1:5177')
        stack = @{ portsToKill = @(8730, 5177) }
        frontend = @{ port = 5177; ttsBaseUrl = 'http://127.0.0.1:8730' }
    } | ConvertTo-Json -Depth 5 | ConvertFrom-Json

    $ports = @(Get-FreeTcpPorts -Count 2)
    Assert-True ($ports.Count -eq 2) 'exactly two verification ports must be allocated'
    Assert-True ($ports[0] -ne $ports[1]) 'backend and frontend ports must be different'
    Assert-True ($ports[0] -notin @(8730, 5177)) 'backend verification port must not reuse the normal service ports'
    Assert-True ($ports[1] -notin @(8730, 5177)) 'frontend verification port must not reuse the normal service ports'

    Set-CleanVerificationPorts -Config $config -ConfigPath $configPath -BackendPort $ports[0] -FrontendPort $ports[1]
    $saved = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json

    Assert-True ([int]$saved.port -eq [int]$ports[0]) 'backend port was not written to the generated config'
    Assert-True ([int]$saved.frontend.port -eq [int]$ports[1]) 'frontend port was not written to the generated config'
    Assert-True ($saved.frontend.ttsBaseUrl -eq "http://127.0.0.1:$($ports[0])") 'frontend backend URL was not updated'
    Assert-True (@($saved.stack.portsToKill).Count -eq 2) 'managed port list must contain only the isolated verification ports'
    Assert-True (@($saved.corsAllowedOrigins) -contains "http://127.0.0.1:$($ports[1])") 'dynamic frontend origin was not added'

    Write-Output "[PASS] isolated clean-install ports: backend=$($ports[0]) frontend=$($ports[1])"
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
