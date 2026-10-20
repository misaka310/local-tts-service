@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-comfyui-runtime.ps1" %*
exit /b %ERRORLEVEL%
