@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0db_status.ps1" %*
exit /b %ERRORLEVEL%
