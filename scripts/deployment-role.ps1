function Get-LocalTtsDeploymentSettings {
    param([Parameter(Mandatory = $true)][object]$Config)

    $deployment = $Config.PSObject.Properties['deployment']
    $deploymentValue = if ($null -ne $deployment) { $deployment.Value } else { $null }
    $roleProperty = if ($null -ne $deploymentValue) { $deploymentValue.PSObject.Properties['role'] } else { $null }
    $workerProperty = if ($null -ne $deploymentValue) { $deploymentValue.PSObject.Properties['workerBaseUrl'] } else { $null }

    $role = if (-not [string]::IsNullOrWhiteSpace($env:LOCAL_TTS_DEPLOYMENT_ROLE)) {
        [string]$env:LOCAL_TTS_DEPLOYMENT_ROLE
    } elseif ($null -ne $roleProperty) {
        [string]$roleProperty.Value
    } else {
        'standalone'
    }
    $role = $role.Trim().ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($role)) { $role = 'standalone' }
    if ($role -notin @('standalone', 'worker', 'frontend')) {
        throw "deployment.role must be standalone, worker, or frontend: $role"
    }

    $workerBaseUrl = if (-not [string]::IsNullOrWhiteSpace($env:LOCAL_TTS_WORKER_BASE_URL)) {
        [string]$env:LOCAL_TTS_WORKER_BASE_URL
    } elseif ($null -ne $workerProperty) {
        [string]$workerProperty.Value
    } else {
        ''
    }
    $workerBaseUrl = $workerBaseUrl.Trim().TrimEnd('/')
    if ($role -eq 'frontend' -and [string]::IsNullOrWhiteSpace($workerBaseUrl)) {
        throw 'deployment.workerBaseUrl is required for frontend role'
    }

    if (-not [string]::IsNullOrWhiteSpace($workerBaseUrl)) {
        $uri = $null
        if (-not [Uri]::TryCreate($workerBaseUrl, [UriKind]::Absolute, [ref]$uri)) {
            throw 'deployment.workerBaseUrl must be an absolute http(s) URL'
        }
        if ($uri.Scheme -notin @('http', 'https') -or [string]::IsNullOrWhiteSpace($uri.Host)) {
            throw 'deployment.workerBaseUrl must be an absolute http(s) URL'
        }
        if (-not [string]::IsNullOrWhiteSpace($uri.UserInfo)) {
            throw 'deployment.workerBaseUrl must not contain credentials'
        }
        if (($uri.AbsolutePath -ne '/') -or -not [string]::IsNullOrWhiteSpace($uri.Query) -or -not [string]::IsNullOrWhiteSpace($uri.Fragment)) {
            throw 'deployment.workerBaseUrl must not contain path, query, or fragment'
        }
        $workerBaseUrl = $uri.GetLeftPart([UriPartial]::Authority)
    }

    [pscustomobject]@{
        Role = $role
        WorkerBaseUrl = $workerBaseUrl
        WorkerHealthUrl = if ($workerBaseUrl) { "$workerBaseUrl/api/health" } else { '' }
        BackendHost = if ($role -eq 'worker') { '127.0.0.1' } else { '' }
        StartBackend = ($role -ne 'frontend')
        StartHeavyServices = ($role -ne 'frontend')
        StartGateway = ($role -ne 'standalone')
        OpenBrowserByDefault = ($role -ne 'worker')
    }
}
