@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (python deploy\pair.py %*) else (py -3 deploy\pair.py %*)
pause
