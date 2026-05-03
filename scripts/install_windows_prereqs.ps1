param(
  [switch]$NoPause
)

# Run this script from an Administrator PowerShell, or run it normally and approve the UAC prompt.
$ErrorActionPreference = "Stop"
$logPath = Join-Path $PSScriptRoot "install_windows_prereqs.log"

function Test-Admin {
  $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
  )
  return $isAdmin
}

if (-not (Test-Admin)) {
  Write-Host "Administrator rights are required. Launching an elevated PowerShell..."
  Start-Process -FilePath powershell.exe -Verb RunAs -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "`"$PSCommandPath`""
  )
  Write-Host "Approve the Windows UAC prompt. If nothing appears, right-click PowerShell and choose 'Run as administrator', then run this script again."
  exit 0
}

Start-Transcript -Path $logPath -Append | Out-Null

Write-Host "Enabling Windows optional features required for WSL 2..."
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

Write-Host "Installing or updating Microsoft WSL package..."
winget install --id Microsoft.WSL --exact --accept-package-agreements --accept-source-agreements

Write-Host "Checking Docker Desktop ProgramData ownership..."
$dockerDesktopData = "C:\ProgramData\DockerDesktop"
if (Test-Path -LiteralPath $dockerDesktopData) {
  $owner = (Get-Acl -LiteralPath $dockerDesktopData).Owner
  Write-Host "Current owner for ${dockerDesktopData}: $owner"
  if ($owner -notmatch "Administrators") {
    Write-Host "Fixing ownership for Docker Desktop data folder..."
    takeown.exe /F $dockerDesktopData /R /D Y
    icacls.exe $dockerDesktopData /setowner "*S-1-5-32-544" /T /C
    icacls.exe $dockerDesktopData /grant "*S-1-5-32-544:(OI)(CI)F" /T /C
  }
}

Write-Host "Installing Docker Desktop..."
winget install --id Docker.DockerDesktop --exact --accept-package-agreements --accept-source-agreements

Write-Host "Adding current user to docker-users group if Docker created it..."
$dockerGroup = Get-LocalGroup -Name "docker-users" -ErrorAction SilentlyContinue
if ($dockerGroup) {
  Add-LocalGroupMember -Group "docker-users" -Member $env:USERNAME -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Install commands completed."
Write-Host "A reboot is usually required after enabling WSL/VirtualMachinePlatform or installing Docker Desktop."
Write-Host "After reboot, open Docker Desktop once, wait until it is running, then run:"
Write-Host '  cd "C:\Users\Sandeep.Pathak\Documents\New project\dalalwall-ai-alpha-agent"'
Write-Host '  .\scripts\docker_up.ps1'
Write-Host '  .\scripts\db_status.ps1'

Stop-Transcript | Out-Null

if (-not $NoPause) {
  Read-Host "Press Enter to close"
}
