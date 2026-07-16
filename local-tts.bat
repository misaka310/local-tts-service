@echo off
setlocal
cd /d "%~dp0"

set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "CONSOLE_LAUNCHER=%~dp0scripts\start-local-tts-console.ps1"

if /I "%~1"=="-Check" goto check

rem The helper uses Start-Process with conhost.exe to create one isolated classic
rem console. Closing it cannot close unrelated Windows Terminal tabs.
"%POWERSHELL_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%CONSOLE_LAUNCHER%" %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
    echo.
    echo [ERROR] local-tts-service console could not start.
    echo Run local-tts.bat -Check to diagnose the problem.
    echo.
    pause
    exit /b %RESULT%
)
exit /b 0

:check
"%SystemRoot%\System32\chcp.com" 65001 >nul
"%POWERSHELL_EXE%" -NoProfile -ExecutionPolicy Bypass -File ".\scripts\launch-local-tts.ps1" %*
set "RESULT=%ERRORLEVEL%"

if not "%RESULT%"=="0" (
    echo.
    echo [ERROR] local-tts-service check failed.
    echo.
    pause
    exit /b %RESULT%
)

exit /b 0
