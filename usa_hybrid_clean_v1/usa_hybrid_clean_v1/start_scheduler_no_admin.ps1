# =============================================
# start_scheduler_no_admin.ps1
# =============================================
# Alternativa simple sin permisos de administrador
# Usa un loop infinito para ejecutar el pipeline diariamente

param(
    [string]$Time = "22:30"  # Hora de ejecución diaria (formato 24h)
)

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "🔄 H3 SCHEDULER (Sin privilegios admin)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "⏰ Programado para ejecutarse diariamente a las $Time" -ForegroundColor Yellow
Write-Host "💡 Mantén esta ventana abierta (minimizada está OK)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Para detener: Presiona Ctrl+C" -ForegroundColor Gray
Write-Host ""

$ScriptPath = Join-Path $PSScriptRoot "run_daily_h3_forward.ps1"

if (-not (Test-Path $ScriptPath)) {
    Write-Host "❌ Error: No se encuentra run_daily_h3_forward.ps1" -ForegroundColor Red
    exit 1
}

$lastRunDate = $null

while ($true) {
    $now = Get-Date
    $targetTime = Get-Date $Time
    
    # Si ya pasó la hora hoy, programar para mañana
    if ($now -gt $targetTime) {
        $targetTime = $targetTime.AddDays(1)
    }
    
    $timeUntilRun = $targetTime - $now
    
    # Solo ejecutar una vez por día
    $today = $now.ToString("yyyy-MM-dd")
    if ($lastRunDate -ne $today -and $now.Hour -eq $targetTime.Hour -and $now.Minute -eq $targetTime.Minute) {
        Write-Host ""
        Write-Host "🚀 Ejecutando pipeline H3..." -ForegroundColor Green
        Write-Host "Hora: $($now.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor White
        Write-Host ""
        
        try {
            & $ScriptPath -SendTelegram
            $lastRunDate = $today
            Write-Host ""
            Write-Host "✅ Pipeline completado" -ForegroundColor Green
            Write-Host "📅 Próxima ejecución: $($targetTime.AddDays(1).ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Cyan
            Write-Host ""
        } catch {
            Write-Host ""
            Write-Host "❌ Error ejecutando pipeline: $_" -ForegroundColor Red
            Write-Host ""
        }
    }
    
    # Mostrar countdown cada 10 minutos
    if ($now.Minute % 10 -eq 0 -and $now.Second -eq 0) {
        $hoursLeft = [math]::Floor($timeUntilRun.TotalHours)
        $minutesLeft = $timeUntilRun.Minutes
        Write-Host "⏳ Tiempo hasta próxima ejecución: ${hoursLeft}h ${minutesLeft}m" -ForegroundColor Gray
    }
    
    Start-Sleep -Seconds 60  # Chequear cada minuto
}
