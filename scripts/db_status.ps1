$ErrorActionPreference = "Stop"

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$docker = if ($dockerCommand) { $dockerCommand.Source } else { "C:\Program Files\Docker\Docker\resources\bin\docker.exe" }
if (-not (Test-Path -LiteralPath $docker)) {
  throw "Docker is not installed or not on PATH."
}

& $docker compose ps
Write-Host ""
Write-Host "Postgres readiness:"
& $docker compose exec postgres pg_isready -U dalalwall -d dalalwall_ai_alpha

Write-Host ""
Write-Host "Redis readiness, if started:"
$redisId = (& $docker compose ps -q redis)
if ($redisId) {
  & $docker compose exec redis redis-cli ping
} else {
  Write-Host "Redis is not running. That is OK for the current phase."
}
