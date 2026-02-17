<#
force_port_5001.ps1

Objetivo:
  - Verifica si el puerto 5001 está ocupado.
  - Identifica el PID que lo usa y lo mata (opcional confirmación).
  - Establece variables de entorno API_PORT=5001 y STRICT_PORT=1.
  - Lanza dashboard_api.py en modo estricto, generando un log con timestamp.

Uso rápido:
  powershell -ExecutionPolicy Bypass -File .\force_port_5001.ps1

Parámetros:
  -Force        : Omite confirmación antes de matar el proceso que ocupa 5001.
  -Background   : Lanza el servidor en background (Start-Process). Si no se especifica, corre en foreground con Tee.
  -PythonExe    : Ruta o nombre del ejecutable Python (default 'python').
  -WorkingDir   : Directorio de trabajo (default = carpeta del script). Debe contener dashboard_api.py.
  -LogDir       : Carpeta para logs (default 'logs'). Se crea si no existe.

Ejemplos:
  .\force_port_5001.ps1 -Force
  .\force_port_5001.ps1 -PythonExe "C:\Python311\python.exe" -Background
  .\force_port_5001.ps1 -WorkingDir "C:\repo\usa_hybrid_clean_v1" -Force -Background

Notas:
  - Requiere permisos suficientes para matar procesos locales.
  - STRICT_PORT=1 hace que el backend aborte si el puerto está ocupado.
  - El log se guarda como logs\dashboard_api_YYYYMMDD_HHMMSS.log
#>
param(
    [switch]$Force,
    [switch]$Background,
    [string]$PythonExe = "python",
    [string]$WorkingDir = (Split-Path -Parent $PSCommandPath),
    [string]$LogDir = "logs"
)

$ErrorActionPreference = 'Stop'
$port = 5001

function Write-Info($msg){ Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warn($msg){ Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg){ Write-Host "[ERROR] $msg" -ForegroundColor Red }
function Write-Ok($msg){ Write-Host "[OK] $msg" -ForegroundColor Green }

Write-Info "Force bind al puerto $port (STRICT_PORT)."

# 1. Detectar si puerto está ocupado
Write-Info "Chequeando estado del puerto $port..."
$netstat = netstat -ano | Select-String ":$port"
$pidToKill = $null
if($netstat){
    # Buscar línea con LISTENING
    foreach($ln in $netstat){
        if($ln.Line -match ":$port\s+.*LISTENING\s+([0-9]+)$"){
            $pidToKill = [int]$Matches[1]
            break
        }
    }
}

if($pidToKill){
    Write-Warn "Puerto $port ocupado por PID $pidToKill."
    if(-not $Force){
        $resp = Read-Host "¿Matar PID $pidToKill para liberar puerto? (y/N)"
        if($resp -notin @('y','Y','s','S')){ Write-Err "Abortado por usuario."; exit 2 }
    }
    try {
        Write-Info "Matando proceso PID $pidToKill..."
        taskkill /PID $pidToKill /F | Out-Null
        Start-Sleep -Seconds 1
        Write-Ok "Proceso $pidToKill terminado."
    } catch {
        Write-Err "No se pudo matar PID ${pidToKill}: $($_.Exception.Message)"; exit 3
    }
} else {
    Write-Ok "Puerto $port libre."
}

# 2. Validar existencia de dashboard_api.py
$apiPath = Join-Path $WorkingDir "dashboard_api.py"
if(-not (Test-Path $apiPath)){
    Write-Err "No se encontró dashboard_api.py en $WorkingDir"; exit 4
}

# 3. Preparar entorno
Write-Info "Estableciendo variables de entorno API_PORT=5001, STRICT_PORT=1 (solo en esta sesión)."
$env:API_PORT = "5001"
$env:STRICT_PORT = "1"

# 4. Preparar logging
if(-not (Test-Path (Join-Path $WorkingDir $LogDir))){
    Write-Info "Creando carpeta de logs: $LogDir"
    New-Item -Path (Join-Path $WorkingDir $LogDir) -ItemType Directory | Out-Null
}
$ts = (Get-Date).ToString('yyyyMMdd_HHmmss')
$logFile = Join-Path $WorkingDir $LogDir "dashboard_api_$ts.log"
Write-Info "Log: $logFile"

# 5. Lanzar servidor
if($Background){
    Write-Info "Lanzando en background..."
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $PythonExe
    $startInfo.Arguments = "-u dashboard_api.py"
    $startInfo.WorkingDirectory = $WorkingDir
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.UseShellExecute = $false
    $process = [System.Diagnostics.Process]::Start($startInfo)
    Write-Ok "Proceso iniciado PID=$($process.Id). Capturando salida..."
    Start-Job -ScriptBlock {
        param($procId,$lf)
        $p = [System.Diagnostics.Process]::GetProcessById($procId)
        $sw = New-Object System.IO.StreamWriter($lf, $true)
        try {
            while(-not $p.HasExited){
                if($p.StandardOutput.Peek() -ge 0){ $line = $p.StandardOutput.ReadLine(); if($line){ $sw.WriteLine($line); $sw.Flush() } }
                if($p.StandardError.Peek() -ge 0){ $eline = $p.StandardError.ReadLine(); if($eline){ $sw.WriteLine($eline); $sw.Flush() } }
                Start-Sleep -Milliseconds 150
            }
        } finally { $sw.Flush(); $sw.Close() }
    } -ArgumentList $process.Id,$logFile | Out-Null
    Write-Info "Usa Get-Content -Wait '$logFile' para ver logs en tiempo real."
    Write-Ok "Listo."
} else {
    Write-Info "Lanzando en foreground (Ctrl+C para detener)..."
    Write-Info "Escribiendo salida en archivo y consola."
    & $PythonExe -u $apiPath 2>&1 | Tee-Object -FilePath $logFile
}
