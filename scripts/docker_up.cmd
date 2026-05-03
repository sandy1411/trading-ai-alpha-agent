@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0docker_up.ps1" %*
exit /b %ERRORLEVEL%
