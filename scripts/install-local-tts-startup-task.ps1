param(
    [string]$TaskName = "LocalTTS Managed Stack",
    [int]$IntervalMinutes = 5,
    [int]$StartupTimeoutSec = 180
)

$ErrorActionPreference = "Stop"

if ($IntervalMinutes -lt 1) {
    throw "IntervalMinutes must be at least 1."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$watchScript = Join-Path $repoRoot "scripts\watch-local-tts-role.ps1"
if (-not (Test-Path -LiteralPath $watchScript -PathType Leaf)) {
    throw "watch-local-tts-role.ps1 was not found: $watchScript"
}

. (Join-Path $PSScriptRoot "no-window-process.ps1")
$noWindowLauncher = Get-LocalTtsNoWindowLauncher -RepoRoot $repoRoot
$powerShellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
$watchdogStdoutPath = Join-Path $repoRoot "runtime\logs\scheduled-watchdog.stdout.log"
$watchdogStderrPath = Join-Path $repoRoot "runtime\logs\scheduled-watchdog.stderr.log"

$userDomain = [string]$env:USERDOMAIN
$userName = [string]$env:USERNAME
$userId = if ([string]::IsNullOrWhiteSpace($userDomain)) {
    $userName
} else {
    "$userDomain\$userName"
}

$powerShellArguments = @(
    "-NoLogo",
    "-NoProfile",
    "-NonInteractive",
    "-WindowStyle", "Hidden",
    "-ExecutionPolicy", "Bypass",
    "-File", $watchScript,
    "-StartupTimeoutSec", [string]$StartupTimeoutSec
)

$launcherArguments = @(
    "--file", $powerShellPath,
    "--working-directory", $repoRoot,
    "--stdout", $watchdogStdoutPath,
    "--stderr", $watchdogStderrPath,
    "--"
) + $powerShellArguments

$arguments = ($launcherArguments | ForEach-Object {
    ConvertTo-LocalTtsWindowsArgument -Value ([string]$_)
}) -join " "

$action = New-ScheduledTaskAction `
    -Execute $noWindowLauncher `
    -Argument $arguments `
    -WorkingDirectory $repoRoot

$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$watchdogTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

$principal = New-ScheduledTaskPrincipal `
    -UserId $userId `
    -LogonType Interactive `
    -RunLevel Limited

$task = New-ScheduledTask `
    -Action $action `
    -Trigger @($logonTrigger, $watchdogTrigger) `
    -Settings $settings `
    -Principal $principal `
    -Description "Keep local-tts-service available without visible console windows."

Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null

$registered = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName

Write-Host "[DONE] scheduled task installed: $TaskName"
Write-Host "[INFO] user=$userId"
Write-Host "[INFO] watchdogInterval=$($IntervalMinutes)m"
Write-Host "[INFO] nextRun=$($info.NextRunTime)"
Write-Host "[INFO] noWindowLauncher=$noWindowLauncher"
Write-Host "[INFO] action=$($registered.Actions[0].Execute) $($registered.Actions[0].Arguments)"

