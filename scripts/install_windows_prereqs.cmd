@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows_prereqs.ps1" %*
exit /b %ERRORLEVEL%
