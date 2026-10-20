$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$project = $PSScriptRoot
$scenes = Get-Content -LiteralPath (Join-Path $project 'storyboard.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$outDir = Join-Path $project 'narration'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Haruka Desktop')
$s.Rate = -1
$s.Volume = 90
try {
    for ($i=0; $i -lt $scenes.Count; $i++) {
        $filename = Join-Path $outDir ('narration_{0:D2}.wav' -f $i)
        $s.SetOutputToWaveFile($filename)
        $s.Speak([string]$scenes[$i].subtitle)
        $s.SetOutputToNull()
        Write-Output ('CREATED {0}' -f $filename)
    }
} finally { $s.Dispose() }
