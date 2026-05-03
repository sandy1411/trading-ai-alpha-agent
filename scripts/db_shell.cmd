@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0db_shell.ps1" %*
exit /b %ERRORLEVEL%
