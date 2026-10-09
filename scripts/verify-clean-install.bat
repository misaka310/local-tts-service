@echo off
setlocal
cd /d "%~dp0\.."
chcp 65001 >nul

echo ==============================================
echo local-tts-service clean-install verification
echo ==============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\verify-clean-install.ps1" %*
set "RESULT=%ERRORLEVEL%"

if not "%RESULT%"=="0" (
    echo.
    echo [ERROR] Clean-install verification failed.
    echo Check runtime\clean-install-verification\clean-install-report.json when it exists.
    echo.
    pause
    exit /b %RESULT%
)

echo.
echo [PASS] Clean-install verification completed.
echo Report: runtime\clean-install-verification\clean-install-report.json
echo Audio:  runtime\clean-install-verification\generated.wav
exit /b 0
