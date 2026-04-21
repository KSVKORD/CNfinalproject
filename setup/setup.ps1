# setup.ps1 — Run from Windows PowerShell as Administrator
# Enables WSL2, installs Ubuntu, then launches the Linux setup script.

# Require admin
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltinRole]::Administrator)) {
    Write-Error "Run this script as Administrator (right-click PowerShell → Run as administrator)."
    exit 1
}

# 1. Install WSL2 + Ubuntu in one command (handles features + kernel + distro)
$distros = wsl --list --quiet 2>$null
if ($distros -match "Ubuntu") {
    Write-Host "Ubuntu is already installed." -ForegroundColor Green
} else {
    Write-Host "Installing WSL2 + Ubuntu..." -ForegroundColor Cyan
    wsl --install -d Ubuntu
    Write-Host ""
    Write-Host "A restart may be required. After restarting, Ubuntu will finish setup automatically." -ForegroundColor Yellow
    Write-Host "Once Ubuntu opens and asks for a username/password, set those, then run:" -ForegroundColor Yellow
    Write-Host "  bash /mnt/c/Users/$env:USERNAME/Desktop/Projects/CN_Finalpj/setup.sh" -ForegroundColor White
    exit 0
}

# 2. Confirm WSL2 (not WSL1)
wsl --set-default-version 2
wsl --set-version Ubuntu 2 2>$null

# 3. Run the Linux setup script inside WSL2
$projectPath = $PSScriptRoot -replace '\\', '/'
$wslPath = "/mnt/" + $projectPath.Substring(0,1).ToLower() + $projectPath.Substring(2)
Write-Host "Launching Linux environment setup..." -ForegroundColor Cyan
wsl -d Ubuntu bash "$wslPath/setup.sh"
