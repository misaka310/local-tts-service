@echo off
cd /d %~dp0\..
powershell -NoProfile -File .\scripts\train-gpt-sovits-voice.ps1 %*
pause
