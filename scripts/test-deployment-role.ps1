$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'deployment-role.ps1')

function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ($Actual -ne $Expected) { throw "$Message (actual=$Actual expected=$Expected)" }
}

$standalone = Get-LocalTtsDeploymentSettings -Config ([pscustomobject]@{})
Assert-Equal $standalone.Role 'standalone' 'missing deployment must default to standalone'
Assert-Equal $standalone.StartBackend $true 'standalone starts backend'
Assert-Equal $standalone.StartHeavyServices $true 'standalone starts heavy services'
Assert-Equal $standalone.StartGateway $false 'standalone does not force gateway mode'
Assert-Equal $standalone.OpenBrowserByDefault $true 'standalone opens the browser by default'

$worker = Get-LocalTtsDeploymentSettings -Config ([pscustomobject]@{
    deployment = [pscustomobject]@{ role = 'worker'; workerBaseUrl = '' }
})
Assert-Equal $worker.Role 'worker' 'worker role must be preserved'
Assert-Equal $worker.StartBackend $true 'worker starts backend'
Assert-Equal $worker.StartHeavyServices $true 'worker starts heavy services'
Assert-Equal $worker.StartGateway $true 'worker starts node gateway'
Assert-Equal $worker.BackendHost '127.0.0.1' 'worker backend must stay loopback-only'
Assert-Equal $worker.OpenBrowserByDefault $false 'worker must not open a browser by default'

$frontend = Get-LocalTtsDeploymentSettings -Config ([pscustomobject]@{
    deployment = [pscustomobject]@{ role = 'frontend'; workerBaseUrl = 'http://worker.example.invalid:5177/' }
})
Assert-Equal $frontend.Role 'frontend' 'frontend role must be preserved'
Assert-Equal $frontend.StartBackend $false 'frontend must not start backend'
Assert-Equal $frontend.StartHeavyServices $false 'frontend must not start heavy services'
Assert-Equal $frontend.StartGateway $true 'frontend starts local UI gateway'
Assert-Equal $frontend.WorkerBaseUrl 'http://worker.example.invalid:5177' 'worker URL is normalized'
Assert-Equal $frontend.WorkerHealthUrl 'http://worker.example.invalid:5177/api/health' 'frontend health checks worker gateway'
Assert-Equal $frontend.OpenBrowserByDefault $true 'frontend opens the local UI by default'

$invalid = $false
try {
    Get-LocalTtsDeploymentSettings -Config ([pscustomobject]@{
        deployment = [pscustomobject]@{ role = 'frontend'; workerBaseUrl = '' }
    }) | Out-Null
} catch {
    $invalid = $true
}
Assert-Equal $invalid $true 'frontend without workerBaseUrl must fail'

$oldRole = $env:LOCAL_TTS_DEPLOYMENT_ROLE
$oldWorker = $env:LOCAL_TTS_WORKER_BASE_URL
try {
    $env:LOCAL_TTS_DEPLOYMENT_ROLE = 'frontend'
    $env:LOCAL_TTS_WORKER_BASE_URL = 'http://worker.example.invalid:5177/'
    $overridden = Get-LocalTtsDeploymentSettings -Config ([pscustomobject]@{})
    Assert-Equal $overridden.Role 'frontend' 'environment role override must win'
    Assert-Equal $overridden.WorkerBaseUrl 'http://worker.example.invalid:5177' 'environment worker URL override must win'
}
finally {
    $env:LOCAL_TTS_DEPLOYMENT_ROLE = $oldRole
    $env:LOCAL_TTS_WORKER_BASE_URL = $oldWorker
}

foreach ($unsafeUrl in @('ftp://worker.example.invalid:5177', 'http://user@worker.example.invalid:5177', 'http://worker.example.invalid:5177/path')) {
    $unsafeRejected = $false
    try {
        Get-LocalTtsDeploymentSettings -Config ([pscustomobject]@{
            deployment = [pscustomobject]@{ role = 'frontend'; workerBaseUrl = $unsafeUrl }
        }) | Out-Null
    } catch {
        $unsafeRejected = $true
    }
    Assert-Equal $unsafeRejected $true "unsafe worker URL must fail: $unsafeUrl"
}

Write-Host '[PASS] deployment role contract'
