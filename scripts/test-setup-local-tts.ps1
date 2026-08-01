$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$entryBat = Join-Path $RepoRoot 'local-tts.bat'
$consoleLauncherScript = Join-Path $RepoRoot 'scripts/start-local-tts-console.ps1'
$launcherScript = Join-Path $RepoRoot 'scripts/launch-local-tts.ps1'
$setupScript = Join-Path $RepoRoot 'scripts/setup-local-tts.ps1'
$checkScript = Join-Path $RepoRoot 'scripts/check-local-tts.ps1'
$cleanVerifyScript = Join-Path $RepoRoot 'scripts/verify-clean-install.ps1'
$cleanVerifyBat = Join-Path $RepoRoot 'scripts/verify-clean-install.bat'
$cleanInstallPortsScript = Join-Path $RepoRoot 'scripts/clean-install-ports.ps1'
$cleanInstallPortsTest = Join-Path $RepoRoot 'scripts/test-clean-install-ports.ps1'
$pythonRuntimeScript = Join-Path $RepoRoot 'scripts/python-runtime.ps1'
$pythonRuntimeTest = Join-Path $RepoRoot 'scripts/test-python-runtime.ps1'
$nodeRuntimeScript = Join-Path $RepoRoot 'scripts/node-runtime.ps1'
$nodeRuntimeTest = Join-Path $RepoRoot 'scripts/test-node-runtime.ps1'
$gitRuntimeScript = Join-Path $RepoRoot 'scripts/git-runtime.ps1'
$gitRuntimeTest = Join-Path $RepoRoot 'scripts/test-git-runtime.ps1'
$managedProcessScript = Join-Path $RepoRoot 'scripts/managed-processes.ps1'
$managedJobScript = Join-Path $RepoRoot 'scripts/managed-job.ps1'
$noWindowProcessScript = Join-Path $RepoRoot 'scripts/no-window-process.ps1'
$noWindowLauncherSource = Join-Path $RepoRoot 'src/LocalTtsNoWindowLauncher.cs'
$noWindowProcessTest = Join-Path $RepoRoot 'scripts/test-no-window-process.ps1'
$stackHostScript = Join-Path $RepoRoot 'scripts/run-local-tts-stack.ps1'
$stopManagedScript = Join-Path $RepoRoot 'scripts/stop-managed-processes.ps1'
$startStackScript = Join-Path $RepoRoot 'scripts/start-local-tts-stack.ps1'
$startLocalScript = Join-Path $RepoRoot 'scripts/start-local-tts.ps1'
$startFrontendScript = Join-Path $RepoRoot 'scripts/start-tts-frontend.ps1'
$setupIrodoriScript = Join-Path $RepoRoot 'scripts/setup-irodori.ps1'
$gitignorePath = Join-Path $RepoRoot '.gitignore'
$gitattributesPath = Join-Path $RepoRoot '.gitattributes'
$licensePath = Join-Path $RepoRoot 'LICENSE'
$agentsPath = Join-Path $RepoRoot 'AGENTS.md'
$requirementsPath = Join-Path $RepoRoot 'config/requirements.txt'
$pytestPath = Join-Path $RepoRoot 'config/pytest.ini'
$readmePath = Join-Path $RepoRoot 'README.md'
$userGuidePath = Join-Path $RepoRoot 'docs/user-guide.md'
$developmentDocPath = Join-Path $RepoRoot 'docs/development.md'
$setupDocPath = Join-Path $RepoRoot 'docs/setup.md'
$cleanVerifyDoc = Join-Path $RepoRoot 'docs/clean-install-verification.md'
$configExample = Join-Path $RepoRoot 'config/config.example.json'
$configIrodoriExample = Join-Path $RepoRoot 'config/config.irodori.example.json'
$configQwenExample = Join-Path $RepoRoot 'config/config.qwen3.example.json'
$ciWorkflow = Join-Path $RepoRoot '.github/workflows/ci.yml'

function Assert-True {
  param([bool]$Condition, [string]$Message)
  if (-not $Condition) { throw $Message }
}

foreach ($path in @(
  $entryBat,
  $consoleLauncherScript,
  $launcherScript,
  $setupScript,
  $checkScript,
  $cleanVerifyScript,
  $cleanVerifyBat,
  $cleanInstallPortsScript,
  $cleanInstallPortsTest,
  $pythonRuntimeScript,
  $pythonRuntimeTest,
  $nodeRuntimeScript,
  $nodeRuntimeTest,
  $gitRuntimeScript,
  $gitRuntimeTest,
  $managedProcessScript,
  $managedJobScript,
  $noWindowProcessScript,
  $noWindowLauncherSource,
  $noWindowProcessTest,
  $stackHostScript,
  $stopManagedScript,
  $startStackScript,
  $startLocalScript,
  $startFrontendScript,
  $setupIrodoriScript,
  $gitignorePath,
  $gitattributesPath,
  $licensePath,
  $agentsPath,
  $requirementsPath,
  $pytestPath,
  $readmePath,
  $userGuidePath,
  $developmentDocPath,
  $setupDocPath,
  $cleanVerifyDoc,
  $configExample,
  $configIrodoriExample,
  $configQwenExample,
  $ciWorkflow
)) {
  Assert-True (Test-Path -LiteralPath $path -PathType Leaf) "required file is missing: $path"
}

$rootBatNames = @(Get-ChildItem -LiteralPath $RepoRoot -Filter '*.bat' -File | Select-Object -ExpandProperty Name | Sort-Object)
Assert-True ($rootBatNames.Count -eq 1) "repository root must contain exactly one BAT entrypoint: $($rootBatNames -join ', ')"
Assert-True ($rootBatNames[0] -eq 'local-tts.bat') 'the only root BAT must be local-tts.bat'
$expectedVisibleRootFiles = @('AGENTS.md', 'LICENSE', 'README.md', 'local-tts.bat') | Sort-Object
$visibleRootFiles = @(Get-ChildItem -LiteralPath $RepoRoot -File | Where-Object { $_.Name -notmatch '^\.' } | Select-Object -ExpandProperty Name | Sort-Object)
$rootFileDifference = @(Compare-Object -ReferenceObject $expectedVisibleRootFiles -DifferenceObject $visibleRootFiles)
Assert-True ($rootFileDifference.Count -eq 0) "unexpected visible root files: $($visibleRootFiles -join ', ')"

$entryText = Get-Content -LiteralPath $entryBat -Raw -Encoding UTF8
$consoleLauncherText = Get-Content -LiteralPath $consoleLauncherScript -Raw -Encoding UTF8
$launcherText = Get-Content -LiteralPath $launcherScript -Raw -Encoding UTF8
$setupText = Get-Content -LiteralPath $setupScript -Raw -Encoding UTF8
$checkText = Get-Content -LiteralPath $checkScript -Raw -Encoding UTF8
$cleanVerifyText = Get-Content -LiteralPath $cleanVerifyScript -Raw -Encoding UTF8
$cleanVerifyBatText = Get-Content -LiteralPath $cleanVerifyBat -Raw -Encoding UTF8
$cleanInstallPortsText = Get-Content -LiteralPath $cleanInstallPortsScript -Raw -Encoding UTF8
$pythonRuntimeText = Get-Content -LiteralPath $pythonRuntimeScript -Raw -Encoding UTF8
$nodeRuntimeText = Get-Content -LiteralPath $nodeRuntimeScript -Raw -Encoding UTF8
$gitRuntimeText = Get-Content -LiteralPath $gitRuntimeScript -Raw -Encoding UTF8
$managedProcessText = Get-Content -LiteralPath $managedProcessScript -Raw -Encoding UTF8
$managedJobText = Get-Content -LiteralPath $managedJobScript -Raw -Encoding UTF8
$noWindowProcessText = Get-Content -LiteralPath $noWindowProcessScript -Raw -Encoding UTF8
$noWindowLauncherText = Get-Content -LiteralPath $noWindowLauncherSource -Raw -Encoding UTF8
$stackHostText = Get-Content -LiteralPath $stackHostScript -Raw -Encoding UTF8
$agentsText = Get-Content -LiteralPath $agentsPath -Raw -Encoding UTF8
$readmeText = Get-Content -LiteralPath $readmePath -Raw -Encoding UTF8
$setupDocText = Get-Content -LiteralPath $setupDocPath -Raw -Encoding UTF8
$requirementsText = Get-Content -LiteralPath $requirementsPath -Raw -Encoding UTF8
$pytestText = Get-Content -LiteralPath $pytestPath -Raw -Encoding UTF8
$gitignoreText = Get-Content -LiteralPath $gitignorePath -Raw -Encoding UTF8
$gitattributesText = Get-Content -LiteralPath $gitattributesPath -Raw -Encoding UTF8
$licenseText = Get-Content -LiteralPath $licensePath -Raw -Encoding UTF8
$configExampleText = Get-Content -LiteralPath $configExample -Raw -Encoding UTF8
$configIrodoriExampleText = Get-Content -LiteralPath $configIrodoriExample -Raw -Encoding UTF8
$configQwenExampleText = Get-Content -LiteralPath $configQwenExample -Raw -Encoding UTF8
$stackText = Get-Content -LiteralPath $startStackScript -Raw -Encoding UTF8
$localText = Get-Content -LiteralPath $startLocalScript -Raw -Encoding UTF8
$frontendText = Get-Content -LiteralPath $startFrontendScript -Raw -Encoding UTF8
$setupIrodoriText = Get-Content -LiteralPath $setupIrodoriScript -Raw -Encoding UTF8
$ciText = Get-Content -LiteralPath $ciWorkflow -Raw -Encoding UTF8

Assert-True ($entryText -match 'scripts\\start-local-tts-console\.ps1') 'local-tts.bat must start the isolated console helper'
Assert-True ($entryText -match 'scripts\\launch-local-tts\.ps1') 'local-tts.bat must keep the unified diagnostic launcher path'
Assert-True ($entryText -match '%\*') 'local-tts.bat must forward optional switches'
Assert-True ($entryText -match 'set "RESULT=%ERRORLEVEL%"') 'local-tts.bat must preserve the exit code'
Assert-True ($entryText -match 'local-tts\.bat -Check') 'local-tts.bat must show the unified diagnostic command on failure'
Assert-True ($consoleLauncherText -match 'conhost\.exe') 'console helper must use an isolated classic console host'
Assert-True ($consoleLauncherText -match 'Start-Process') 'console helper must create the isolated console as a separate process'
Assert-True ($consoleLauncherText -match 'launch-local-tts\.ps1') 'console helper must run the unified launcher'

Assert-True ($launcherText -notmatch '[^\x00-\x7F]') 'launcher must remain ASCII-compatible with Windows PowerShell 5'
$launcherTokens = $null
$launcherParseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($launcherScript, [ref]$launcherTokens, [ref]$launcherParseErrors)
Assert-True ($launcherParseErrors.Count -eq 0) 'launcher must parse in Windows PowerShell'
Assert-True ($launcherText -match '\[switch\]\$ForceSetup') 'launcher must expose repair setup'
Assert-True ($launcherText -match '\[switch\]\$Check') 'launcher must expose diagnostics'
Assert-True ($launcherText -match 'setup-local-tts\.ps1') 'launcher must call the setup script'
Assert-True ($launcherText -match 'run-local-tts-stack\.ps1') 'launcher must start the managed stack host'
Assert-True ($launcherText -match 'config/config\.local\.json') 'launcher must keep local configuration out of the repository root'
Assert-True ($launcherText -match 'Move-Item.*legacyConfigPath') 'launcher must migrate the legacy root configuration'
Assert-True ($launcherText -match '-DownloadQwenModels') 'first run must download the default Qwen model'
Assert-True ($launcherText -match '-QwenDefaultModelOnly') 'first run must avoid optional Qwen model downloads'
Assert-True ($launcherText -match '-DownloadFfmpeg') 'first run must install FFmpeg for media imports'
Assert-True ($launcherText -match '-SetupIrodori') 'first run must install Irodori'
Assert-True ($launcherText -match '-SkipVendorSetup') 'first run must not require optional GPT-SoVITS vendor setup'
Assert-True ($launcherText -match '-NoGptSovitsStart') 'first run must not start optional GPT-SoVITS'
Assert-True ($launcherText -match 'Start-LocalTtsManagedStackHost') 'first run must join the managed lifecycle before opening the app'
Assert-True ($launcherText -match 'InstallCtrlHandler') 'launcher must keep running and handle Ctrl+C'
Assert-True ($launcherText -match 'Press Ctrl\+C or close this window') 'launcher must explain how to stop the stack'
Assert-True ($managedJobText -match 'JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE') 'managed job must terminate children when the launcher handle closes'
Assert-True ($managedJobText -match 'CREATE_SUSPENDED') 'stack host must be assigned before it can create children'
Assert-True ($stackHostText -match '-StartFrontend') 'managed stack host must start the frontend without owning the browser'
Assert-True ($managedProcessText -match 'sessionId') 'managed process records must identify the launch session'
Assert-True ($launcherText -notmatch '-SkipMediaToolsInstall') 'first run must include video-reference media tools'
Assert-True ($launcherText -match 'runtime/venv-demucs') 'launcher must detect the background-removal environment'
Assert-True ($launcherText -match 'ffmpeg\.exe') 'launcher must detect FFmpeg before skipping setup'
Assert-True ($launcherText -match 'Qwen__Qwen3-TTS-12Hz-1\.7B-Base') 'launcher must detect the standard Qwen clone model before skipping setup'

Assert-True ($setupText -match '\[switch\]\$DryRun') 'setup must support a dry run'
Assert-True ($setupText.Contains("return @('Qwen/Qwen3-TTS-12Hz-1.7B-Base')")) 'default-only Qwen setup must always select Voice Clone 1.7B'
Assert-True ($setupText.Contains("if (`$modelProp.Name -eq 'qwen3_tts_design_1_7b' -or `$modelId -eq 'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign') { continue }")) 'setup must ignore retired Qwen Voice Design entries in existing local configs'
Assert-True ($setupText -match 'config/requirements\.txt') 'setup must use the relocated requirements file'
Assert-True ($setupText -match 'faster_whisper') 'setup must verify speech recognition dependencies'
Assert-True ($setupText -match 'yt_dlp') 'setup must verify video download dependencies'
Assert-True ($setupText -match 'demucs==4\.0\.1') 'setup must install the pinned background-removal engine'
Assert-True ($setupText -match 'ffmpeg-release-essentials\.zip') 'setup must download FFmpeg from the configured distribution'
Assert-True ($setupText -match 'torch==2\.8\.0\+cu128') 'setup must install the tested CUDA build on NVIDIA systems'
Assert-True ($setupText -match 'torchaudio==2\.8\.0\+cu128') 'setup must install the matching CUDA torchaudio build'
Assert-True ($setupText -match 'torch==2\.8\.0\+cpu') 'setup must install the pinned CPU PyTorch build when NVIDIA is unavailable'
Assert-True ($setupText -match 'torchaudio==2\.8\.0\+cpu') 'setup must install the matching CPU torchaudio build'
Assert-True ($setupText -match 'download\.pytorch\.org/whl/cpu') 'setup must use the official CPU PyTorch index'
Assert-True ($setupText -match 'verify pinned PyTorch versions after requirements install') 'setup must verify requirements did not replace the pinned PyTorch pair'
$cpuTorchInstallPosition = $setupText.IndexOf("torch==2.8.0+cpu", [System.StringComparison]::Ordinal)
$requirementsInstallPosition = $setupText.IndexOf("pip install -r config/requirements.txt", [System.StringComparison]::Ordinal)
$torchPostVerifyPosition = $setupText.IndexOf("verify pinned PyTorch versions after requirements install", [System.StringComparison]::Ordinal)
Assert-True ($cpuTorchInstallPosition -ge 0 -and $cpuTorchInstallPosition -lt $requirementsInstallPosition) 'CPU PyTorch must be pinned before config/requirements.txt is installed'
Assert-True ($torchPostVerifyPosition -gt $requirementsInstallPosition) 'PyTorch versions must be rechecked after config/requirements.txt is installed'
Assert-True ($setupText -match 'sitecustomize\.py') 'setup must configure app-local Windows DLL discovery'
Assert-True ($setupText -match 'app-local Microsoft Visual C\+\+ runtime verification') 'setup must verify the app-local MSVC runtime'
Assert-True ($setupText -match 'python-runtime\.ps1') 'setup and clean verification must share the Python resolver'
Assert-True ($setupText -match 'Install-LocalTtsManagedPythonRuntime') 'setup must install repo-managed Python 3.11 when needed'
Assert-True ($pythonRuntimeText -match 'python-3\.11\.9-amd64\.exe') 'managed Python must pin the final Windows installer for Python 3.11'
Assert-True ($pythonRuntimeText -match '5EE42C4EEE1E6B4464BB23722F90B45303F79442DF63083F05322F1785F5FDDE') 'managed Python must verify the pinned installer SHA-256'
Assert-True ($pythonRuntimeText -match 'pip-26\.1\.2-py3-none-any\.whl') 'embedded Python fallback must pin a versioned pip wheel'
Assert-True ($pythonRuntimeText -match '382FF9F685EE3BC25864F820AA50505825F10F5458FFFF07E30A6D96E5715CAB') 'embedded Python fallback must verify the pinned pip wheel SHA-256'
Assert-True ($pythonRuntimeText -notmatch 'bootstrap\.pypa\.io/get-pip\.py') 'embedded Python fallback must not depend on the mutable get-pip.py payload'
Assert-True ($pythonRuntimeText -match 'Lib\\site-packages') 'embedded Python fallback must expose the wheel installation directory'
Assert-True ($pythonRuntimeText -match 'ZipFile\]::ExtractToDirectory') 'embedded Python fallback must extract the verified wheel without requiring pip first'
Assert-True ($pythonRuntimeText -match 'Start-Process -FilePath \$managedPath') 'embedded Python fallback must capture pip process exit codes through Start-Process'
Assert-True ($pythonRuntimeText -notmatch '& \$managedPath -m pip') 'embedded Python fallback must not rely on nullable LASTEXITCODE from direct native invocation'
Assert-True ($pythonRuntimeText -match "'virtualenv', '--disable-pip-version-check', '--no-warn-script-location'") 'embedded Python fallback must suppress the expected repo-local Scripts PATH warning'
Assert-True ($pythonRuntimeText -match 'Microsoft\\\\WindowsApps') 'managed Python resolver must reject the Windows Store execution alias'
Assert-True ($setupText -match 'node-runtime\.ps1') 'setup and startup must share the Node.js resolver'
Assert-True ($setupText -match 'Install-LocalTtsManagedNodeRuntime') 'setup must install portable Node.js'
Assert-True ($setupText -match 'git-runtime\.ps1') 'setup and Irodori must share the Git resolver'
Assert-True ($setupText -match 'Install-LocalTtsManagedGitRuntime') 'setup must install portable MinGit'
Assert-True ($gitRuntimeText -match 'MinGit-2\.55\.0\.2-64-bit\.zip') 'managed Git must pin the verified MinGit archive'
Assert-True ($gitRuntimeText -match 'E3EA2944CEA4B3FABCD69C7C1669EF69B1B66C05AC7806D81224D0ABAD2DEC31') 'managed Git must verify the published SHA-256'

Assert-True ($checkText -match '\[string\]\$ConfigPath') 'diagnostics must accept the relocated config path'
Assert-True ($checkText -match '\[switch\]\$Deep') 'deep diagnostics must remain opt-in'
Assert-True ($checkText -match '\[switch\]\$CheckOptionalServices') 'optional service diagnostics must remain opt-in'
Assert-True ($cleanVerifyText -notmatch '[^\x00-\x7F]') 'clean-install verification must remain ASCII-compatible with Windows PowerShell 5'
Assert-True ($cleanVerifyText -match 'Assert-CleanState') 'clean-install verification must reject pre-populated state'
Assert-True ($cleanVerifyText -match '/api/speak') 'clean-install verification must generate through the frontend API'
Assert-True ($cleanVerifyText -match '/api/reference-voices') 'clean-install verification must register a real reference voice through the frontend API'
Assert-True ($cleanVerifyText -match 'qwen3_tts_clone_1_7b') 'clean-install verification must exercise Qwen3-TTS Voice Clone 1.7B'
Assert-True ($cleanVerifyText -match 'generated-qwen-clone\.wav') 'clean-install verification must preserve the generated Qwen clone WAV'
Assert-True ($cleanVerifyText -match "runtime -ne 'qwen3_tts'") 'clean-install verification must require the native Qwen runtime'
Assert-True ($cleanVerifyText -match 'RIFF') 'clean-install verification must validate WAV output'
Assert-True ($cleanVerifyText -match 'Install-LocalTtsManagedPythonRuntime') 'clean-install verification must install repo-managed Python 3.11 when needed'
Assert-True ($cleanVerifyText -match 'Resolve-LocalTtsNodeRuntime') 'clean-install verification must use the repo-managed Node.js runtime'
Assert-True ($cleanVerifyText -match 'torchaudio\.__version__') 'clean-install verification must record the matching torchaudio version'
Assert-True ($cleanVerifyText -match 'Start-Process -FilePath \$venvPython') 'PyTorch diagnostics must use Start-Process instead of direct native invocation'
Assert-True ($cleanVerifyText -match 'RedirectStandardOutput \$torchStdoutPath') 'PyTorch diagnostics must capture stdout separately'
Assert-True ($cleanVerifyText -match 'RedirectStandardError \$torchStderrPath') 'PyTorch diagnostics must capture stderr separately'
Assert-True ($cleanVerifyText -match 'PyTorch verification failed with exit code') 'PyTorch diagnostic failures must include the process exit code'
Assert-True ($cleanVerifyText -match '\$torchStderr\.Trim\(\)') 'PyTorch diagnostic failures must preserve complete stderr text'
Assert-True ($cleanVerifyText -notmatch '\$torchJson\s*=\s*&\s*\$venvPython') 'PyTorch diagnostics must not use direct PowerShell native invocation'
Assert-True ($cleanVerifyText -notmatch "Assert-CommandAvailable -Command 'git\.exe'") 'clean-install verification must not require system Git for the Qwen-only path'
Assert-True ($cleanVerifyBatText -match 'verify-clean-install\.ps1') 'clean-install BAT must call the PowerShell verifier'
Assert-True ($cleanVerifyBatText -match '%\*') 'clean-install BAT must forward optional switches'
Assert-True ($cleanVerifyText -match 'clean-install-ports\.ps1') 'clean-install verification must load the isolated-port helper'
Assert-True ($cleanInstallPortsText -match 'Get-FreeTcpPorts') 'clean-install verification must allocate isolated free ports'
Assert-True ($cleanInstallPortsText -match 'Set-CleanVerificationPorts') 'clean-install verification must rewrite its generated config to isolated ports'
Assert-True ($cleanVerifyText -notmatch 'Required ports are already in use') 'clean-install verification must not fail only because the normal service ports are occupied'

$launchSectionMatch = [regex]::Match($readmeText, '(?ms)^## [^\r\n]+\r?\n(?<body>(?:(?!^## ).)*local-tts\.bat -ForceSetup(?:(?!^## ).)*)')
Assert-True ($launchSectionMatch.Success) 'README must contain a launch section with the repair command'
$launchSectionText = $launchSectionMatch.Groups['body'].Value
Assert-True ($launchSectionText -match 'local-tts\.bat') 'README must document the single user entrypoint'
Assert-True ($launchSectionText -match '\*\*30.*1.*\*\*') 'README must document the expected first-run setup duration'
Assert-True ($launchSectionText -match 'docs/setup\.md') 'README launch section must link to the setup guide'
Assert-True ($launchSectionText -notmatch 'FFmpeg|yt-dlp|Python|Node\.js|PyTorch|Irodori|Qwen') 'README launch section must leave the detailed setup inventory to docs/setup.md'
Assert-True ($setupDocText -match 'FFmpeg') 'setup guide must retain media-tool details'
Assert-True ($setupDocText -match 'yt-dlp') 'setup guide must retain video-reference tooling details'
Assert-True ($setupDocText -match 'Node\.js.*Git') 'setup guide must retain managed Node.js and Git details'
Assert-True ($readmeText -notmatch '(?m)^- Git for Windows$') 'README must not require a system-wide Git installation'
Assert-True ($readmeText -notmatch 'setup-and-start-local-tts\.bat|start-local-tts\.bat|check-local-tts\.bat') 'README must not mention removed entrypoints'
Assert-True ($agentsText -match 'README') 'AGENTS.md must enforce README rules'
Assert-True ($agentsText -match '140') 'AGENTS.md must enforce the README size limit'
Assert-True ($agentsText -match 'local-tts\.bat') 'AGENTS.md must enforce the unified entrypoint'
Assert-True ($agentsText -match 'python -m pytest --rootdir=\. -c config/pytest\.ini tests') 'AGENTS.md must document backend verification'
Assert-True ($agentsText -match 'public history') 'AGENTS.md must require public history review'

Assert-True ($requirementsText -match 'qwen-tts==') 'requirements must install Qwen3-TTS'
Assert-True ($requirementsText -match 'msvc-runtime==14\.44\.35112') 'Windows requirements must install the pinned app-local MSVC runtime'
Assert-True ($requirementsText -match 'faster-whisper') 'requirements must install speech recognition'
Assert-True ($requirementsText -match 'yt-dlp') 'requirements must install video URL support'
Assert-True ($pytestText -match 'StarletteDeprecationWarning') 'pytest must reject the deprecated TestClient fallback'
Assert-True ($gitattributesText -match '\* text=auto eol=lf') 'repository must use stable LF normalization'
Assert-True ($licenseText -match '^MIT License') 'LICENSE must be MIT'
Assert-True ($gitignoreText -match '(?m)^config/config\.local\.json$') 'config/config.local.json must remain ignored'
Assert-True ($gitignoreText -match '!reference/workflows/') 'public workflows must remain tracked'

Assert-True ($configExampleText -match '"defaultModel"\s*:\s*"irodori_v3"') 'public config must default to Irodori v3 without reference audio'
Assert-True ($configExampleText -notmatch '"comfyui"\s*:') 'standard config must not expose unused ComfyUI settings'
Assert-True ($configIrodoriExampleText -notmatch '"runtime"\s*:\s*"comfyui"') 'Irodori config must use the direct runtime'
Assert-True ($configQwenExampleText -notmatch 'irodori|comfyui') 'Qwen-only config must not include unrelated runtimes'

Assert-True ($stackText -match 'stop-managed-processes\.ps1') 'startup must stop only previously managed processes'
Assert-True ($stackText -notmatch 'kill-tts-stack-ports\.ps1') 'startup must not kill arbitrary port owners'
Assert-True ($stackText -match '/v1/models\?probe=false') 'normal startup must use lightweight model checks'
Assert-True ($localText -match 'Register-ManagedProcess') 'backend startup must register its process'
Assert-True ($localText -match 'no-window-process\.ps1') 'backend startup must load the no-window process helper'
Assert-True ($localText -match 'Start-LocalTtsNoWindowProcess') 'backend startup must use the no-window launcher for unattended Python processes'
Assert-True ($localText -notmatch 'Start-Process -FilePath \$python .*WindowStyle Hidden') 'backend startup must not rely on WindowStyle Hidden for Python processes'
Assert-True ($frontendText -match 'Register-ManagedProcess') 'frontend startup must register its process'
Assert-True ($frontendText -match 'no-window-process\.ps1') 'frontend startup must load the no-window process helper'
Assert-True ($frontendText -match 'Start-LocalTtsNoWindowProcess') 'frontend startup must use the no-window launcher for Node.js'
Assert-True ($frontendText -match 'node-runtime\.ps1') 'frontend startup must use the shared Node.js resolver'
Assert-True ($noWindowProcessText -match 'CreateNoWindow\s*=\s*\$true') 'PowerShell helper must create the launcher without a console'
Assert-True ($noWindowProcessText -match 'UseShellExecute\s*=\s*\$false') 'PowerShell helper must disable shell execution'
Assert-True ($noWindowLauncherText -match 'CreateNoWindow\s*=\s*true') 'native launcher must create the child without a console'
Assert-True ($noWindowLauncherText -match 'UseShellExecute\s*=\s*false') 'native launcher must disable shell execution'
Assert-True ($noWindowLauncherText -match 'RedirectStandardOutput\s*=\s*true') 'native launcher must preserve stdout diagnostics'
Assert-True ($noWindowLauncherText -match 'RedirectStandardError\s*=\s*true') 'native launcher must preserve stderr diagnostics'
Assert-True ($setupIrodoriText -match 'eaf74d6a19138f743acb5b71a445fd25a57db987') 'Irodori setup must pin the verified revision'
Assert-True ($setupIrodoriText -match 'git-runtime\.ps1') 'Irodori setup must use the shared Git resolver'
Assert-True ($setupIrodoriText -match 'Install-LocalTtsManagedGitRuntime') 'Irodori setup must repair missing Git automatically'
Assert-True ($setupIrodoriText -match 'msvc-runtime==14\.44\.35112') 'Irodori setup must install the pinned app-local MSVC runtime'
Assert-True ($setupIrodoriText -match "msvc-runtime==14\.44\.35112'\) -Label 'install app-local MSVC runtime for Irodori' -Attempts 2") 'Irodori setup must retry transient app-local MSVC runtime file locks'
Assert-True ($setupIrodoriText -match 'sitecustomize\.py') 'Irodori setup must configure app-local Windows DLL discovery'

$dryRun = & $setupScript -DryRun -DownloadQwenModels -QwenDefaultModelOnly -DownloadFfmpeg -SetupIrodori -SkipVendorSetup -NoGptSovitsStart -StartAfterSetup
$dryRunText = ($dryRun | Out-String)
Assert-True ($dryRunText -match 'DRY-RUN') 'dry run output must be explicit'
Assert-True ($dryRunText -match 'config\\config\.local\.json') 'dry run must target the relocated local config'
Assert-True ($dryRunText -match 'MinGit') 'standard setup must include portable MinGit'
Assert-True ($dryRunText -match 'Qwen/Qwen3-TTS-12Hz-1\.7B-Base') 'standard setup must include Qwen3-TTS Voice Clone 1.7B'
Assert-True ($dryRunText -notmatch 'Qwen/Qwen3-TTS-12Hz-1\.7B-VoiceDesign') 'standard setup must not download Qwen3-TTS Voice Design'
Assert-True ($dryRunText -notmatch 'Qwen/Qwen3-TTS-12Hz-0\.6B-Base') 'standard setup must not download the optional 0.6B clone model'
Assert-True ($dryRunText -match 'FFmpeg') 'standard setup must include FFmpeg'
Assert-True ($dryRunText -match 'YouTube and Whisper') 'standard setup must include video and speech-recognition tools'
Assert-True ($dryRunText -match 'torch==2\.8\.0\+cpu') 'standard setup dry run must document the pinned CPU PyTorch path'
Assert-True ($dryRunText -match 'torchaudio==2\.8\.0\+cpu') 'standard setup dry run must document the matching CPU torchaudio path'
Assert-True ($dryRunText -match 'background-removal') 'standard setup must include background removal'
Assert-True ($dryRunText -match 'setup repo-local Irodori') 'standard setup must include Irodori'

Assert-True ($ciText -match 'actions/checkout@v6') 'CI must use the Node 24-compatible checkout action'
Assert-True ($ciText -match 'actions/setup-python@v6') 'CI must use the Node 24-compatible Python setup action'
Assert-True ($ciText -match 'actions/setup-node@v6') 'CI must use the Node 24-compatible Node setup action'
Assert-True ($ciText -match '(?m)^\s*- main\s*$') 'CI must target the main branch'
Assert-True ($ciText -notmatch '(?m)^\s*- public-release\s*$') 'CI must not target the retired public-release branch'
Assert-True ($ciText -match 'python -m pytest --rootdir=\. -c config/pytest\.ini tests') 'CI must run backend tests with relocated pytest config'
Assert-True ($ciText -match 'config/requirements\.txt') 'CI must install relocated requirements'
Assert-True ($ciText -match 'npm ci') 'CI must use npm ci'
Assert-True ($ciText -match 'e2e:qwen-ui') 'CI must run qwen UI E2E'
Assert-True ($ciText -match 'e2e:rvc-tabs') 'CI must run RVC E2E'
Assert-True ($ciText -match 'test-setup-local-tts\.ps1') 'CI must verify setup behavior'

& $pythonRuntimeTest
& $nodeRuntimeTest
& $gitRuntimeTest
& $noWindowProcessTest

Write-Host '[OK] setup-local-tts tests passed'
