$ErrorActionPreference = 'Stop'

function Assert-Match {
    param([string]$Text, [string]$Pattern, [string]$Message)
    if ($Text -notmatch $Pattern) { throw $Message }
}

function Assert-NotMatch {
    param([string]$Text, [string]$Pattern, [string]$Message)
    if ($Text -match $Pattern) { throw $Message }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$startFrontend = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'start-tts-frontend.ps1') -Raw -Encoding UTF8
$startStack = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'start-local-tts-stack.ps1') -Raw -Encoding UTF8
$launcher = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'launch-local-tts.ps1') -Raw -Encoding UTF8
$startupTask = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'install-local-tts-startup-task.ps1') -Raw -Encoding UTF8
$frontendServer = Get-Content -LiteralPath (Join-Path $repoRoot 'frontend/server.js') -Raw -Encoding UTF8
$watchScriptPath = Join-Path $PSScriptRoot 'watch-local-tts-role.ps1'
if (-not (Test-Path -LiteralPath $watchScriptPath -PathType Leaf)) { throw 'role-aware watchdog script is missing' }
$watchScript = Get-Content -LiteralPath $watchScriptPath -Raw -Encoding UTF8

Assert-Match $startFrontend '/api/frontend-health' 'frontend process readiness must use a local-only health endpoint'
Assert-NotMatch $startStack 'throw\s+"[^"]*worker[^"]*"' 'frontend role must start even when the worker is currently offline'
Assert-Match $startupTask 'watch-local-tts-role\.ps1' 'scheduled task must use the role-aware watchdog'
Assert-Match $watchScript '-StartupTimeoutSec\s+\$StartupTimeoutSec' 'role-aware watchdog must forward the configured startup timeout to stack startup'
Assert-Match $launcher 'OpenBrowserByDefault' 'launcher must respect role-specific browser behavior'
Assert-Match $frontendServer 'rootConfig\.referenceVoicesDir' 'worker gateway must honor referenceVoicesDir from config'

Write-Host '[PASS] remote deployment UX contract'
