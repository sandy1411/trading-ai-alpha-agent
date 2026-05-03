param(
  [switch]$WithRedis
)

$ErrorActionPreference = "Stop"

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$docker = if ($dockerCommand) { $dockerCommand.Source } else { "C:\Program Files\Docker\Docker\resources\bin\docker.exe" }
if (-not (Test-Path -LiteralPath $docker)) {
  throw "Docker is not installed or not on PATH. Install Docker Desktop for Windows with the WSL 2 backend, then reopen PowerShell."
}

if ($WithRedis) {
  & $docker compose up -d postgres redis
} else {
  & $docker compose up -d postgres
}
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
& $docker compose ps
