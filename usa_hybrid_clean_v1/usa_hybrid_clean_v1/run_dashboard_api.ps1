Param(
    [int]$Port = 5001,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Write-Host "[run_dashboard_api] Starting API on port $Port..." -ForegroundColor Cyan

$env:API_PORT = $Port

$scriptPath = Join-Path $PSScriptRoot "dashboard_api.py"
if(!(Test-Path $scriptPath)){
    Write-Host "dashboard_api.py not found at $scriptPath" -ForegroundColor Red
    exit 1
}

# Create logs directory
$logDir = Join-Path $PSScriptRoot "logs"
if(!(Test-Path $logDir)){ New-Item -ItemType Directory -Path $logDir | Out-Null }
$logFile = Join-Path $logDir ("dashboard_api_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

Write-Host "Log file: $logFile" -ForegroundColor DarkGray

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $Python
$startInfo.Arguments = "`"$scriptPath`""
$startInfo.WorkingDirectory = $PSScriptRoot
$startInfo.UseShellExecute = $true
$startInfo.RedirectStandardOutput = $false
$startInfo.RedirectStandardError = $false

$proc = [System.Diagnostics.Process]::Start($startInfo)
if(!$proc){
    Write-Host "Failed to launch process" -ForegroundColor Red
    exit 1
}

Write-Host "API process started (PID=$($proc.Id)). Press Ctrl+C in its window to stop." -ForegroundColor Green

# Simple wait loop writing heartbeat to log file
Add-Content -Path $logFile -Value "Started PID=$($proc.Id) Port=$Port Time=$(Get-Date -Format o)"

while(!$proc.HasExited){
    Start-Sleep -Seconds 30
    try { Add-Content -Path $logFile -Value "Heartbeat $(Get-Date -Format o) PID=$($proc.Id)" } catch {}
}

Write-Host "Process exited." -ForegroundColor Yellow
