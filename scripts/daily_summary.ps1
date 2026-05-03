param(
    [switch]$SendEmail
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

.\.venv\Scripts\python.exe scripts\send_daily_summary.py draft | Out-Host

if ($SendEmail) {
    .\.venv\Scripts\python.exe scripts\send_daily_summary.py email | Out-Host
} else {
    Write-Host "Email not sent. Use -SendEmail only after SMTP is configured and you are ready to transmit the summary."
}
