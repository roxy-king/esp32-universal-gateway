@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start-demo.ps1"
set "demo_exit=%errorlevel%"
pause
exit /b %demo_exit%
