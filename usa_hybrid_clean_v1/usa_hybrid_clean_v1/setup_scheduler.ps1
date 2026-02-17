# =============================================
# setup_scheduler.ps1
# =============================================
# Configurar tarea programada para H3 daily pipeline
# IMPORTANTE: Ejecutar este script como Administrador

param(
    [string]$Time = "22:30",  # 10:30 PM por defecto
    [switch]$Remove
)

$TaskName = "H3_Daily_Forward_Trading"
$ScriptPath = Join-Path $PSScriptRoot "run_daily_h3_forward.ps1"

if ($Remove) {
    Write-Host "🗑️  Eliminando tarea programada '$TaskName'..." -ForegroundColor Yellow
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "✅ Tarea eliminada correctamente" -ForegroundColor Green
    } catch {
        Write-Host "❌ Error: $_" -ForegroundColor Red
        Write-Host "💡 Intenta ejecutar como Administrador" -ForegroundColor Yellow
    }
    exit 0
}

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "🔧 CONFIGURANDO TAREA PROGRAMADA H3" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Tarea: $TaskName" -ForegroundColor White
Write-Host "Script: $ScriptPath" -ForegroundColor White
Write-Host "Horario: Diario a las $Time" -ForegroundColor White
Write-Host ""

# Verificar que el script existe
if (-not (Test-Path $ScriptPath)) {
    Write-Host "❌ Error: No se encuentra run_daily_h3_forward.ps1" -ForegroundColor Red
    Write-Host "   Ruta esperada: $ScriptPath" -ForegroundColor Yellow
    exit 1
}

# Crear acción
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`" -SendTelegram"

# Crear trigger (diario)
$trigger = New-ScheduledTaskTrigger -Daily -At $Time

# Crear principal (usuario actual, nivel más alto)
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

# Configuración adicional
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# Registrar tarea
try {
    Write-Host "📝 Registrando tarea..." -ForegroundColor Yellow
    
    $task = Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "Pipeline H3 forward-looking diario con notificaciones Telegram. Ejecuta después del cierre del mercado." `
        -Force `
        -ErrorAction Stop
    
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "✅ TAREA PROGRAMADA CONFIGURADA" -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "📅 Próxima ejecución: $($trigger.StartBoundary)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "💡 Comandos útiles:" -ForegroundColor Yellow
    Write-Host "  Ver tarea:      Get-ScheduledTask -TaskName '$TaskName' | fl" -ForegroundColor White
    Write-Host "  Ejecutar ahora: Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host "  Eliminar:       .\setup_scheduler.ps1 -Remove" -ForegroundColor White
    Write-Host "  Ver historial:  Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo" -ForegroundColor White
    Write-Host ""
    
} catch {
    Write-Host ""
    Write-Host "❌ ERROR al registrar tarea" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "💡 Soluciones:" -ForegroundColor Yellow
    Write-Host "  1. Ejecuta PowerShell como Administrador:" -ForegroundColor White
    Write-Host "     Click derecho en PowerShell → 'Ejecutar como administrador'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  2. O ejecuta este comando con privilegios:" -ForegroundColor White
    Write-Host "     Start-Process powershell -Verb RunAs -ArgumentList `"-File .\setup_scheduler.ps1`"" -ForegroundColor Gray
    Write-Host ""
    exit 1
}
