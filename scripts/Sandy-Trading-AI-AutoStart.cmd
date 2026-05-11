@echo off
setlocal

set "ROOT=%~dp0.."
set "LOG=%ROOT%\.runtime\startup.log"

if not exist "%ROOT%\.runtime" mkdir "%ROOT%\.runtime"

echo [%date% %time%] Starting Sandy-Trading-AI local stack >> "%LOG%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\start_shadow_stack.ps1" -Port 8002 -IntervalSeconds 60 >> "%LOG%" 2>&1
echo [%date% %time%] Sandy-Trading-AI startup finished with exit code %ERRORLEVEL% >> "%LOG%"

endlocal
