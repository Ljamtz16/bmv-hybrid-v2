# serve_dashboard.ps1
# Servidor HTTP simple para servir el dashboard en http://localhost:8080

$Port = 8080
$WorkingDir = $PSScriptRoot

Write-Host "[INFO] Iniciando servidor HTTP en puerto $Port..." -ForegroundColor Cyan
Write-Host "[INFO] Dashboard disponible en: http://localhost:$Port/intraday_dashboard.html" -ForegroundColor Green
Write-Host "[INFO] Presiona Ctrl+C para detener el servidor." -ForegroundColor Yellow
Write-Host ""

# Iniciar servidor HTTP de Python
python -m http.server $Port --directory $WorkingDir
