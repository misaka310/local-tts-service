param(
    [string]$ConfigPath = "",
    [int[]]$Ports = @()
)

$ErrorActionPreference = "Stop"

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path $Path -PathType Leaf)) { return $null }
    $raw = Get-Content -Path $Path -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    return ($raw | ConvertFrom-Json)
}

function Get-PropertyValue {
    param(
        [object]$Object,
        [string]$Name,
        [object]$Default = $null
    )
    if ($null -eq $Object) { return $Default }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    if ($null -eq $prop.Value) { return $Default }
    return $prop.Value
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$configCandidates = @()
if ($ConfigPath -and $ConfigPath.Trim() -ne "") {
    if ([System.IO.Path]::IsPathRooted($ConfigPath)) {
        $configCandidates += $ConfigPath
    }
    else {
        $configCandidates += (Join-Path $repoRoot $ConfigPath)
    }
}
$configCandidates += (Join-Path $repoRoot "config/config.local.json")
$configCandidates += (Join-Path $repoRoot "config.local.json")
$configCandidates += (Join-Path $repoRoot "config/config.example.json")
$configCandidates += (Join-Path $repoRoot "config/config.irodori.example.json")

$config = $null
$configSource = "(default)"
foreach ($candidate in $configCandidates | Select-Object -Unique) {
    $loaded = Read-JsonFile -Path $candidate
    if ($null -ne $loaded) {
        $config = $loaded
        $configSource = $candidate
        break
    }
}

$defaultPorts = @(8730, 8288, 5177)
$targetPorts = @()
if ($Ports.Count -gt 0) {
    $targetPorts = $Ports
}
else {
    $stack = Get-PropertyValue -Object $config -Name "stack"
    $configuredPorts = Get-PropertyValue -Object $stack -Name "portsToKill"
    if ($configuredPorts -is [System.Collections.IEnumerable]) {
        foreach ($value in $configuredPorts) {
            $p = 0
            if ([int]::TryParse([string]$value, [ref]$p) -and $p -ge 1 -and $p -le 65535) {
                $targetPorts += $p
            }
        }
    }
}

if ($targetPorts.Count -eq 0) {
    $targetPorts = $defaultPorts
}
$targetPorts = $targetPorts | Select-Object -Unique

Write-Host "[INFO] kill target ports: $($targetPorts -join ', ')"
Write-Host "[INFO] config source: $configSource"

$killErrors = @()
foreach ($port in $targetPorts) {
    $connections = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if (-not $connections) {
        Write-Host "[SKIP] port=$port no listener"
        continue
    }

    $owners = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($owner in $owners) {
        $proc = Get-Process -Id $owner -ErrorAction SilentlyContinue
        $procName = if ($proc) { $proc.ProcessName } else { "unknown" }
        $cmdLine = ""
        try {
            $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$owner" -ErrorAction Stop
            $cmdLine = [string]$cim.CommandLine
        }
        catch {
            $cmdLine = ""
        }

        try {
            Stop-Process -Id $owner -Force -ErrorAction Stop
            Write-Host "[KILLED] port=$port pid=$owner name=$procName"
            if (-not [string]::IsNullOrWhiteSpace($cmdLine)) {
                Write-Host "         cmd=$cmdLine"
            }
        }
        catch {
            $message = $_.Exception.Message
            Write-Error "[FAIL] port=$port pid=$owner name=$procName error=$message"
            $killErrors += "port=$port pid=$owner $message"
        }
    }
}

if ($killErrors.Count -gt 0) {
    throw "Failed to stop one or more listeners. $($killErrors -join ' | ')"
}

Write-Host "[DONE] kill-tts-stack-ports"
