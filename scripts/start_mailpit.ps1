$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

docker compose up -d mailpit | Out-Host
Write-Host "Mailpit local SMTP preview is available at http://127.0.0.1:8025"
Write-Host "SMTP endpoint: localhost:1025"
