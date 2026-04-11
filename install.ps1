Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  DesktopAutomation Windows Quick Installer  " -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Ensure git is installed
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Git not found. Please install Git (https://git-scm.com/downloads) first!" -ForegroundColor Red
    exit
}

# 2. Ensure uv is installed
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing 'uv' package manager (astral.sh/uv)..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -OutFile "install_uv.ps1"
    & .\install_uv.ps1
    Remove-Item "install_uv.ps1"
    
    # Reload PATH in current session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

# 3. Clone repo
if (-not (Test-Path "DesktopAutomation")) {
    Write-Host "Cloning repository..." -ForegroundColor Yellow
    git clone https://github.com/medomostafa/DesktopAutomation.git
} else {
    Write-Host "Directory 'DesktopAutomation' already exists. Updating..." -ForegroundColor Yellow
    Set-Location DesktopAutomation
    git pull
    Set-Location ..
}

Set-Location DesktopAutomation

# 4. Create .env
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env file..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "`nIMPORTANT: I created a .env file for you." -ForegroundColor Magenta
    Write-Host "Please open DesktopAutomation/.env and add your GOOGLE_API_KEY." -ForegroundColor Magenta
    Write-Host "Press any key when you are ready to continue..." -ForegroundColor Magenta
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

# 5. Run
Write-Host "`nSyncing dependencies..." -ForegroundColor Yellow
uv sync

Write-Host "`nStarting Desktop Automation..." -ForegroundColor Green
uv run desktop-automation
