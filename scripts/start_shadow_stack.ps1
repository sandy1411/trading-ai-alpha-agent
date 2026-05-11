param(
    [int]$Port = 8002,
    [int]$IntervalSeconds = 60,
    [int]$DockerWaitSeconds = 180
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

function Test-DockerReady {
    docker info *> $null
    return $LASTEXITCODE -eq 0
}

function Ensure-DockerReady {
    if (Test-DockerReady) {
        return
    }

    $dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path -LiteralPath $dockerDesktop) {
        Write-Host "Starting Docker Desktop..."
        Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
    }

    $deadline = (Get-Date).AddSeconds($DockerWaitSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        if (Test-DockerReady) {
            return
        }
    }
    throw "Docker Desktop did not become ready within $DockerWaitSeconds seconds."
}

function Wait-PostgresReady {
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        docker compose exec -T postgres pg_isready -U dalalwall -d dalalwall_ai_alpha *> $null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "PostgreSQL did not become healthy within 90 seconds."
}

Ensure-DockerReady

Write-Host "Starting Docker services..."
Invoke-Checked -FilePath "docker" -ArgumentList @("compose", "up", "-d", "postgres", "redis", "mailpit")
Wait-PostgresReady

Write-Host "Ensuring database schema exists..."
Invoke-Checked -FilePath ".\.venv\Scripts\python.exe" -ArgumentList @("scripts\init_db.py", "create-all")

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

function Get-PortOwner {
    param([int]$CandidatePort)

    $listener = Get-NetTCPConnection -LocalPort $CandidatePort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) {
        return $null
    }
    return Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
}

function Test-SandyProcess {
    param($Process)
    return $Process -and $Process.CommandLine -like "*dalalwall-ai-alpha-agent*" -and $Process.CommandLine -like "*uvicorn app.main:app*"
}

$requestedPort = $Port
while ($true) {
    $owner = Get-PortOwner -CandidatePort $Port
    if (-not $owner) {
        break
    }
    if (Test-SandyProcess -Process $owner) {
        Stop-Process -Id $owner.ProcessId -Force
        Write-Host "Stopped existing Sandy-Trading-AI listener on port ${Port}: $($owner.ProcessId)"
        Start-Sleep -Seconds 1
        continue
    }
    Write-Host "Port $Port is occupied by another process: $($owner.CommandLine)"
    $Port += 1
    Write-Host "Trying dashboard port $Port instead."
}

if ($Port -ne $requestedPort) {
    Write-Host "Using fallback dashboard port $Port because requested port $requestedPort is busy."
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
