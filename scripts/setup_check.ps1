param(
  [string]$BundledPython = "C:\Users\Sandeep.Pathak\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)

$ErrorActionPreference = "Continue"

function Test-Command {
  param([string]$Name, [string]$Command, [string[]]$Args = @("--version"))
  $cmd = Get-Command $Command -ErrorAction SilentlyContinue
  if (-not $cmd) {
    [PSCustomObject]@{ Tool = $Name; Found = $false; Version = ""; Path = ""; Note = "Not on PATH" }
    return
  }
  $version = ""
  try {
    $version = (& $Command @Args 2>&1 | Select-Object -First 1) -join ""
  } catch {
    $version = $_.Exception.Message
  }
  [PSCustomObject]@{ Tool = $Name; Found = $true; Version = $version; Path = $cmd.Source; Note = "" }
}

$checks = @()
$checks += Test-Command "Git" "git"
$checks += Test-Command "Docker" "docker"
$checks += Test-Command "Docker Compose" "docker" @("compose", "version")
$checks += Test-Command "Python" "python"
$checks += Test-Command "PostgreSQL psql" "psql"
$checks += Test-Command "GitHub CLI" "gh"

if (Test-Path -LiteralPath $BundledPython) {
  $version = (& $BundledPython --version 2>&1 | Select-Object -First 1) -join ""
  $checks += [PSCustomObject]@{
    Tool = "Bundled Codex Python"
    Found = $true
    Version = $version
    Path = $BundledPython
    Note = "Usable fallback for local dev"
  }
} else {
  $checks += [PSCustomObject]@{
    Tool = "Bundled Codex Python"
    Found = $false
    Version = ""
    Path = $BundledPython
    Note = "Not found"
  }
}

$checks | Format-Table -AutoSize

Write-Host ""
Write-Host "Repo: $(Resolve-Path .)"
git status --short --branch 2>$null
