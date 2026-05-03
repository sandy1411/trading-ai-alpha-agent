$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$pythonPathPattern = "*dalalwall-ai-alpha-agent*\.venv\Scripts\python.exe*"
$targets = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like $pythonPathPattern -and (
        $_.CommandLine -like "*uvicorn app.main:app*" -or
        $_.CommandLine -like "*run_shadow_training.py*loop*"
    )
}

foreach ($target in $targets) {
    Stop-Process -Id $target.ProcessId -Force
    Write-Host "Stopped process $($target.ProcessId)"
}

if (-not $targets) {
    Write-Host "No Sandy-Trading-AI API or shadow-loop process found."
}
