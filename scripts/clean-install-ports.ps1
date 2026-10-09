function Get-FreeTcpPorts {
    param([ValidateRange(1, 10)][int]$Count = 2)

    $listeners = @()
    try {
        for ($index = 0; $index -lt $Count; $index += 1) {
            $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
            $listener.Start()
            $listeners += $listener
        }
        return @($listeners | ForEach-Object { ([System.Net.IPEndPoint]$_.LocalEndpoint).Port })
    }
    finally {
        foreach ($listener in $listeners) {
            $listener.Stop()
        }
    }
}

function Set-CleanVerificationPorts {
    param(
        [Parameter(Mandatory = $true)][object]$Config,
        [Parameter(Mandatory = $true)][string]$ConfigPath,
        [Parameter(Mandatory = $true)][int]$BackendPort,
        [Parameter(Mandatory = $true)][int]$FrontendPort
    )

    if ($BackendPort -eq $FrontendPort) {
        throw 'Backend and frontend verification ports must be different.'
    }

    $Config.port = $BackendPort
    $Config.frontend.port = $FrontendPort
    $Config.frontend.ttsBaseUrl = "http://127.0.0.1:$BackendPort"
    $Config.stack.portsToKill = @($BackendPort, $FrontendPort)
    $origins = @($Config.corsAllowedOrigins) + @(
        "http://127.0.0.1:$FrontendPort",
        "http://localhost:$FrontendPort"
    )
    $Config.corsAllowedOrigins = @($origins | Select-Object -Unique)
    $Config | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
}
