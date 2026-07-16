@echo off
cd /d %~dp0\..
powershell -NoProfile -File .\scripts\setup-gpt-sovits.ps1
pause
