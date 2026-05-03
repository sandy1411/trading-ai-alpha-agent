param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Starting Sandy-Trading-AI API if needed..."
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $listener) {
    Start-Process `
        -FilePath ".\.venv\Scripts\python.exe" `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port") `
        -WorkingDirectory $Root `
        -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 3
}

Write-Host "Opening Zerodha Kite login. Complete broker login in the browser."
Write-Host "The local callback will exchange and store the access token automatically."
.\.venv\Scripts\python.exe scripts\zerodha_login_url.py --open-browser | Out-Host
