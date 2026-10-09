# E2E TTS Generation Validation Script for local-tts-service
# Safe ASCII encoding with Base64 to bypass Windows PowerShell encoding parser bugs.

$ErrorActionPreference = "Stop"

$Models = @("irodori_v2", "irodori_v3", "qwen3")

# Text: "こんばんどちたのキンタマは、よかぜにゆれて、ほしとなる。"
$TextBase64 = "44GT44KT44Gw44KT44Gp44Gh44Gf44Gu44Kt44Oz44K/44Oe44Gv44CB44KI44GL44Gl44Gr44KG44KM44Gm44CB44G744GX44Go44Gq44KL44CC"
$TextBytes = [System.Convert]::FromBase64String($TextBase64)
$Text = [System.Text.Encoding]::UTF8.GetString($TextBytes)

$BaseUrl = "http://127.0.0.1:8730"
$Results = @()
$Failed = $false

Write-Host "=========================================="
Write-Host " Starting E2E TTS Generation Validation"
Write-Host "=========================================="
Write-Host "Target text length: $($Text.Length)"
Write-Host "API URL: $BaseUrl"
Write-Host ""

foreach ($Model in $Models) {
    Write-Host "--- Testing Model: $Model ---"
    $RequestId = "$Model-test-001"
    
    $Body = @{
        text = $Text
        model = $Model
        requestId = $RequestId
        format = "wav"
    } | ConvertTo-Json

    $Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    
    try {
        $Response = Invoke-RestMethod -Uri "$BaseUrl/v1/speak" -Method Post -Body $Body -ContentType "application/json" -TimeoutSec 300
        $Stopwatch.Stop()
        
        $Duration = [Math]::Round($Stopwatch.Elapsed.TotalSeconds, 2)
        
        if ($Response.ok -eq $true) {
            $AudioPath = $Response.audioPath
            $AudioUrl = $Response.audioUrl
            
            Write-Host "  POST /v1/speak: OK"
            Write-Host "  audioPath: $AudioPath"
            Write-Host "  audioUrl:  $AudioUrl"
            Write-Host "  Time:      $Duration s"
            
            if (Test-Path $AudioPath) {
                $FileSize = (Get-Item $AudioPath).Length
                if ($FileSize -gt 0) {
                    Write-Host "  File exists and size is valid: $FileSize bytes"
                    
                    $Results += [PSCustomObject]@{
                        Model = $Model
                        Status = "SUCCESS"
                        TimeSec = $Duration
                        FileSize = $FileSize
                        AudioPath = $AudioPath
                        Error = ""
                    }
                } else {
                    Write-Host "  Error: File exists but size is 0 bytes."
                    $Results += [PSCustomObject]@{
                        Model = $Model
                        Status = "FAILED"
                        TimeSec = $Duration
                        FileSize = 0
                        AudioPath = $AudioPath
                        Error = "File size is 0"
                    }
                    $Failed = $true
                }
            } else {
                Write-Host "  Error: Generated audio file not found at $AudioPath"
                $Results += [PSCustomObject]@{
                    Model = $Model
                    Status = "FAILED"
                    TimeSec = $Duration
                    FileSize = 0
                    AudioPath = $AudioPath
                    Error = "File not found"
                }
                $Failed = $true
            }
        } else {
            $Stopwatch.Stop()
            $ErrorMsg = $Response.error
            Write-Host "  POST /v1/speak returned ok=false. Error: $ErrorMsg"
            $Results += [PSCustomObject]@{
                Model = $Model
                Status = "FAILED"
                TimeSec = [Math]::Round($Stopwatch.Elapsed.TotalSeconds, 2)
                FileSize = 0
                AudioPath = ""
                Error = $ErrorMsg
            }
            $Failed = $true
        }
    } catch {
        $Stopwatch.Stop()
        $Exc = $_.Exception.Message
        Write-Host "  HTTP Request Exception: $Exc"
        
        # Try to parse response error if available
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            Write-Host "  Details: $($_.ErrorDetails.Message)"
        }
        
        $Results += [PSCustomObject]@{
            Model = $Model
            Status = "FAILED"
            TimeSec = [Math]::Round($Stopwatch.Elapsed.TotalSeconds, 2)
            FileSize = 0
            AudioPath = ""
            Error = $Exc
        }
        $Failed = $true
    }
    
    Write-Host ""
}

Write-Host "=========================================="
Write-Host " E2E Validation Summary"
Write-Host "=========================================="

$Results | Format-Table -AutoSize

if ($Failed) {
    Write-Host "E2E Validation FAILED. Please check the errors above."
    exit 1
} else {
    Write-Host "E2E Validation PASSED successfully!"
    exit 0
}
