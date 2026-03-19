# XTTS-v2 TTS Server - Windows service installer
# Run this script as Administrator

# Auto-elevate if not running as Administrator
if (!([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "Restarting with Administrator privileges..." -ForegroundColor Yellow
    Start-Process powershell "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

$ErrorActionPreference = "Stop"

Write-Host "=== XTTS-v2 TTS Server Service Installer ===" -ForegroundColor Cyan

$SCRIPT_DIR = Split-Path -Parent $PSCommandPath
$PROJECT_ROOT = (Resolve-Path (Join-Path $SCRIPT_DIR "..")).Path
$SERVICE_NAME = "XTTS-TTS"
$PYTHON_EXE = "C:\Program Files\Python311\python.exe"
$SERVER_ENTRYPOINT = Join-Path $PROJECT_ROOT "tts\__main__.py"
$SERVER_ARGS = "-m tts"
$LOG_DIR = Join-Path $PROJECT_ROOT "logs"

# Ensure logs directory exists
New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null

# Resolve global NSSM from PATH
$NSSM_COMMAND = Get-Command nssm.exe -ErrorAction SilentlyContinue
if (-not $NSSM_COMMAND) {
    $NSSM_COMMAND = Get-Command nssm -ErrorAction SilentlyContinue
}
if (-not $NSSM_COMMAND) {
    Write-Host "NSSM is not available in PATH." -ForegroundColor Red
    Write-Host "Install it globally and rerun this script:" -ForegroundColor Yellow
    Write-Host "  winget install --id NSSM.NSSM -e"
    Write-Host "  choco install nssm -y"
    exit 1
}
$NSSM_EXE = $NSSM_COMMAND.Source
Write-Host "Using NSSM: $NSSM_EXE" -ForegroundColor DarkGray

# Validate dependencies
if (!(Test-Path $PYTHON_EXE)) {
    Write-Host "Python not found at $PYTHON_EXE" -ForegroundColor Red
    exit 1
}
if (!(Test-Path $SERVER_ENTRYPOINT)) {
    Write-Host "Server entrypoint not found at $SERVER_ENTRYPOINT" -ForegroundColor Red
    exit 1
}

# Install service
Write-Host "Installing service '$SERVICE_NAME'..." -ForegroundColor Yellow
& $NSSM_EXE install $SERVICE_NAME $PYTHON_EXE $SERVER_ARGS

# Configure service
& $NSSM_EXE set $SERVICE_NAME AppDirectory $PROJECT_ROOT
& $NSSM_EXE set $SERVICE_NAME Start SERVICE_AUTO_START
& $NSSM_EXE set $SERVICE_NAME AppStdout "$LOG_DIR\tts_server.log"
& $NSSM_EXE set $SERVICE_NAME AppStderr "$LOG_DIR\tts_server_error.log"
& $NSSM_EXE set $SERVICE_NAME AppRotateFiles 1
& $NSSM_EXE set $SERVICE_NAME AppRotateBytes 1048576

# Open firewall port
Write-Host "Opening firewall port 5000..." -ForegroundColor Yellow
netsh advfirewall firewall add rule name="XTTS TTS Server" dir=in action=allow protocol=TCP localport=5000 | Out-Null

# Start service
Write-Host "Starting service..." -ForegroundColor Yellow
net start $SERVICE_NAME

Write-Host "`n=== Installation complete! ===" -ForegroundColor Green
Write-Host "Service: $SERVICE_NAME"
Write-Host "URL: http://localhost:5000"
Write-Host "Logs: $LOG_DIR"
Write-Host "`nCommands:"
Write-Host "  net stop $SERVICE_NAME    - Stop service"
Write-Host "  net start $SERVICE_NAME   - Start service"
Write-Host "  sc delete $SERVICE_NAME   - Remove service"
