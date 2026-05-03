param(
  [int]$Port = 8000,
  [string]$Python = "C:\Users\Sandeep.Pathak\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Python)) {
  $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
  if (-not $pythonCmd) {
    throw "Python was not found. Install Python 3.11+ or pass -Python <path>."
  }
  $Python = $pythonCmd.Source
}

& $Python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload
