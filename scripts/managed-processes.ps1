function ConvertTo-PowerShellSingleQuotedLiteral {
    param([Parameter(Mandatory = $true)][string]$Value)
    return "'" + ($Value -replace "'", "''") + "'"
}

function Get-ManagedProcessDirectory {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)
    $resolvedRoot = [System.IO.Path]::GetFullPath([string]$RepoRoot)
    return Join-Path $resolvedRoot 'runtime/processes'
}

function Get-ManagedProcessRecordPath {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Service
    )
    if ($Service -notmatch '^[A-Za-z0-9._-]+$') {
        throw "invalid managed service name: $Service"
    }
    return Join-Path (Get-ManagedProcessDirectory -RepoRoot $RepoRoot) "$Service.json"
}

function Add-ManagedProcessMarker {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Service
    )
    $rootLiteral = ConvertTo-PowerShellSingleQuotedLiteral -Value ([System.IO.Path]::GetFullPath([string]$RepoRoot))
    $serviceLiteral = ConvertTo-PowerShellSingleQuotedLiteral -Value $Service
    return "`$env:LOCAL_TTS_MANAGED_REPO=$rootLiteral; `$env:LOCAL_TTS_MANAGED_SERVICE=$serviceLiteral; $Command"
}

function Get-ManagedProcessIdentity {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }

    $commandLine = ''
    $executablePath = ''
    try {
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        $commandLine = [string]$cim.CommandLine
        $executablePath = [string]$cim.ExecutablePath
    }
    catch {
        $commandLine = ''
        $executablePath = ''
    }

    try {
        $process.Refresh()
        $startTime = $process.StartTime
        if ($null -eq $startTime) { return $null }
        $startTimeUtc = $startTime.ToUniversalTime()
    }
    catch {
        return $null
    }

    return [PSCustomObject]@{
        process = $process
        processId = $ProcessId
        processStartTimeUtc = $startTimeUtc
        commandLine = $commandLine
        executablePath = $executablePath
    }
}

function Register-ManagedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)][string[]]$ExpectedCommandFragments,
        [string]$HealthUrl = '',
        [int]$Port = 0
    )

    if ($global:LocalTtsManagedJobHandle -and $global:LocalTtsManagedJobHandle -ne [IntPtr]::Zero) {
        try {
            Add-ProcessToLocalTtsManagedJob -JobHandle $global:LocalTtsManagedJobHandle -ProcessHandle $Process.Handle -ProcessId $Process.Id
        }
        catch {
            Start-Process -FilePath 'taskkill.exe' -ArgumentList @('/PID', [string]$Process.Id, '/T', '/F') -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
            throw
        }
    }

    $identity = Get-ManagedProcessIdentity -ProcessId $Process.Id
    if ($null -eq $identity) {
        throw "cannot register exited process for service $Service (pid=$($Process.Id))"
    }

    $resolvedRoot = [System.IO.Path]::GetFullPath([string]$RepoRoot)
    $recordPath = Get-ManagedProcessRecordPath -RepoRoot $resolvedRoot -Service $Service
    $recordDir = Split-Path -Parent $recordPath
    New-Item -ItemType Directory -Path $recordDir -Force | Out-Null

    $record = [PSCustomObject]@{
        schemaVersion = 1
        service = $Service
        pid = $Process.Id
        registeredAtUtc = [DateTime]::UtcNow.ToString('o')
        sessionId = [string]$env:LOCAL_TTS_MANAGED_SESSION_ID
        processStartTimeUtc = $identity.processStartTimeUtc.ToString('o')
        repoRoot = $resolvedRoot
        expectedCommandFragments = @($ExpectedCommandFragments | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
        executablePath = $identity.executablePath
        healthUrl = $HealthUrl
        port = $Port
    }

    $tempPath = "$recordPath.tmp"
    $record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $tempPath -Encoding UTF8
    Move-Item -LiteralPath $tempPath -Destination $recordPath -Force
    Write-Host "[INFO] managed process registered: service=$Service pid=$($Process.Id) record=$recordPath"
    return $recordPath
}

function Test-ManagedProcessRecord {
    param(
        [Parameter(Mandatory = $true)][object]$Record,
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    $resolvedRoot = [System.IO.Path]::GetFullPath([string]$RepoRoot)
    if ([string]$Record.repoRoot -ne $resolvedRoot) {
        return [PSCustomObject]@{ valid = $false; reason = 'repo root mismatch'; identity = $null }
    }

    $processId = 0
    if (-not [int]::TryParse([string]$Record.pid, [ref]$processId) -or $processId -le 0) {
        return [PSCustomObject]@{ valid = $false; reason = 'invalid pid'; identity = $null }
    }

    $identity = Get-ManagedProcessIdentity -ProcessId $processId
    if ($null -eq $identity) {
        return [PSCustomObject]@{ valid = $false; reason = 'process is not running'; identity = $null }
    }

    $storedStart = [DateTime]::MinValue
    if (-not [DateTime]::TryParse([string]$Record.processStartTimeUtc, [ref]$storedStart)) {
        return [PSCustomObject]@{ valid = $false; reason = 'invalid stored start time'; identity = $identity }
    }
    $startDelta = [Math]::Abs(($identity.processStartTimeUtc - $storedStart.ToUniversalTime()).TotalSeconds)
    if ($startDelta -gt 1.0) {
        return [PSCustomObject]@{ valid = $false; reason = 'process start time mismatch'; identity = $identity }
    }

    if ([string]::IsNullOrWhiteSpace($identity.commandLine)) {
        return [PSCustomObject]@{ valid = $false; reason = 'command line unavailable'; identity = $identity }
    }

    foreach ($fragment in @($Record.expectedCommandFragments)) {
        $expected = [string]$fragment
        if ([string]::IsNullOrWhiteSpace($expected)) { continue }
        if ($identity.commandLine.IndexOf($expected, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
            return [PSCustomObject]@{ valid = $false; reason = "command marker mismatch: $expected"; identity = $identity }
        }
    }

    return [PSCustomObject]@{ valid = $true; reason = ''; identity = $identity }
}

function Stop-ManagedProcesses {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [string]$Service = '',
        [string]$SessionId = ''
    )

    $recordDir = Get-ManagedProcessDirectory -RepoRoot $RepoRoot
    if (-not (Test-Path -LiteralPath $recordDir -PathType Container)) {
        return [PSCustomObject]@{ Stopped = 0; Stale = 0; Skipped = 0; Failed = 0 }
    }

    $recordFiles = if ([string]::IsNullOrWhiteSpace($Service)) {
        @(Get-ChildItem -LiteralPath $recordDir -Filter '*.json' -File -ErrorAction SilentlyContinue)
    }
    else {
        $path = Get-ManagedProcessRecordPath -RepoRoot $RepoRoot -Service $Service
        if (Test-Path -LiteralPath $path -PathType Leaf) { @((Get-Item -LiteralPath $path)) } else { @() }
    }

    $stopped = 0
    $stale = 0
    $skipped = 0
    $failed = 0

    foreach ($file in $recordFiles) {
        $record = $null
        try {
            $record = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        }
        catch {
            Write-Warning "invalid managed process record; leaving it untouched: $($file.FullName)"
            $skipped++
            continue
        }

        if (-not [string]::IsNullOrWhiteSpace($SessionId) -and [string]$record.sessionId -ne $SessionId) {
            continue
        }

        $check = Test-ManagedProcessRecord -Record $record -RepoRoot $RepoRoot
        if (-not $check.valid) {
            if ($check.reason -eq 'process is not running') {
                Remove-Item -LiteralPath $file.FullName -Force -ErrorAction SilentlyContinue
                Write-Host "[STALE] removed process record: service=$($record.service) pid=$($record.pid)"
                $stale++
            }
            else {
                Write-Warning "managed process identity check failed; process was not stopped: service=$($record.service) pid=$($record.pid) reason=$($check.reason)"
                $skipped++
            }
            continue
        }

        try {
            $taskkill = Start-Process -FilePath 'taskkill.exe' -ArgumentList @('/PID', [string]$record.pid, '/T', '/F') -Wait -PassThru -WindowStyle Hidden
            if ($taskkill.ExitCode -ne 0 -and (Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue)) {
                throw "taskkill exit code $($taskkill.ExitCode)"
            }
            $deadline = [DateTime]::UtcNow.AddSeconds(5)
            while ([DateTime]::UtcNow -lt $deadline -and (Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue)) {
                Start-Sleep -Milliseconds 100
            }
            if (Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue) {
                throw 'process did not exit'
            }
            Remove-Item -LiteralPath $file.FullName -Force -ErrorAction SilentlyContinue
            Write-Host "[STOPPED] managed process: service=$($record.service) pid=$($record.pid)"
            $stopped++
        }
        catch {
            Write-Warning "failed to stop managed process: service=$($record.service) pid=$($record.pid) error=$($_.Exception.Message)"
            $failed++
        }
    }

    return [PSCustomObject]@{ Stopped = $stopped; Stale = $stale; Skipped = $skipped; Failed = $failed }
}
