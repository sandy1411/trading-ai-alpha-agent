param(
    [int]$Port = 8000,
    [int]$IntervalSeconds = 300
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Starting Docker services..."
docker compose up -d postgres redis | Out-Host

Write-Host "Ensuring database schema exists..."
.\.venv\Scripts\python.exe scripts\init_db.py create-all | Out-Host

Write-Host "Stopping existing local API/shadow-loop processes..."
function Stop-SandyProcesses {
    $pythonPathPattern = "*dalalwall-ai-alpha-agent*\.venv\Scripts\python.exe*"
    $targets = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -like $pythonPathPattern -and (
            $_.CommandLine -like "*uvicorn app.main:app*" -or
            $_.CommandLine -like "*run_shadow_training.py*loop*"
        )
    }
    foreach ($target in $targets) {
        Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped process $($target.ProcessId)"
    }
}

Stop-SandyProcesses
Start-Sleep -Seconds 2
Stop-SandyProcesses

$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    $ownerProcessId = $listener.OwningProcess
    if ($ownerProcessId -and $ownerProcessId -ne 0) {
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerProcessId" -ErrorAction SilentlyContinue
        if ($owner -and $owner.CommandLine -like "*uvicorn app.main:app*") {
            Stop-Process -Id $ownerProcessId -Force
            Write-Host "Stopped existing listener on port ${Port}: $ownerProcessId"
        }
    }
}

Write-Host "Starting FastAPI dashboard..."
$api = Start-Process `
    -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -PassThru

$healthy = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        if ($response.status -eq "ok") {
            $healthy = $true
            break
        }
    } catch {
        if ($api.HasExited) {
            throw "FastAPI process exited before health check passed."
        }
    }
}
if (-not $healthy) {
    throw "FastAPI dashboard did not become healthy on port $Port."
}

Write-Host "Starting shadow training loop..."
$loop = Start-Process `
    -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList @("scripts\run_shadow_training.py", "loop", "--interval-seconds", "$IntervalSeconds") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -PassThru

Write-Host ""
Write-Host "Sandy-Trading-AI shadow stack is running."
Write-Host "API PID: $($api.Id)"
Write-Host "Shadow loop PID: $($loop.Id)"
Write-Host "Dashboard: http://127.0.0.1:$Port/dashboard"
Write-Host "Log: $Root\.runtime\shadow_training.log"
