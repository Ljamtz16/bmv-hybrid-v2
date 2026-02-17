# =============================================
# setup_intraday_scheduler.ps1
# =============================================
<#
.SYNOPSIS
Registra tarea programada para evaluación intraday cada 15 minutos.

.DESCRIPTION
Crea una tarea en el Programador de Tareas de Windows que ejecuta
schedule_intraday.ps1 cada 15 minutos durante días laborables.

.PARAMETER TaskName
Nombre de la tarea (default: HybridClean_Intraday_Monitor_15m)

.PARAMETER WorkDir
Directorio de trabajo del proyecto

.PARAMETER WhatIf
Mostrar qué se haría sin ejecutar

.EXAMPLE
.\setup_intraday_scheduler.ps1
.\setup_intraday_scheduler.ps1 -WhatIf
.\setup_intraday_scheduler.ps1 -TaskName "MyCustomTask"
#>

param(
    [string]$TaskName = "HybridClean_Intraday_Monitor_15m",
    [string]$WorkDir = $PSScriptRoot,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

Write-Host "`n=============================================" -ForegroundColor Cyan
Write-Host "  Setup Intraday Scheduler" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# Verificar que estamos en el directorio correcto
if (-not (Test-Path (Join-Path $WorkDir "schedule_intraday.ps1"))) {
    Write-Host "[ERROR] No se encuentra schedule_intraday.ps1 en $WorkDir" -ForegroundColor Red
    exit 1
}

Write-Host "Directorio: $WorkDir"
Write-Host "Tarea: $TaskName`n"

# Comando a ejecutar
$scriptPath = Join-Path $WorkDir "schedule_intraday.ps1"
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`"" `
    -WorkingDirectory $WorkDir

# Trigger: cada 15 minutos, lunes-viernes, durante horario de mercado extendido (8:00-17:00)
# El script interno verificará el horario exacto (9:30-16:00)
$trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At "08:00AM" `
    -DaysInterval 1

# Repetir cada 15 minutos durante 10 horas (8:00-18:00)
$trigger.Repetition = $(New-ScheduledTaskTrigger -Once -At "08:00AM" -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Hours 10)).Repetition

# Settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew

# Principal (usuario actual)
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

# Crear/actualizar tarea
if ($WhatIf) {
    Write-Host "[WhatIf] Se crearía la siguiente tarea:" -ForegroundColor Yellow
    Write-Host "  Nombre: $TaskName"
    Write-Host "  Script: $scriptPath"
    Write-Host "  Trigger: Diario cada 15 min (8:00-18:00)"
    Write-Host "  Usuario: $env:USERNAME"
} else {
    # Verificar si ya existe
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    
    if ($existingTask) {
        Write-Host "[INFO] Tarea existente encontrada, actualizando..." -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    
    # Registrar
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Evaluación intraday cada 15 minutos para USA Hybrid Clean V1" | Out-Null
    
    Write-Host "`n[OK] Tarea registrada exitosamente: $TaskName" -ForegroundColor Green
    
    # Verificar
    $task = Get-ScheduledTask -TaskName $TaskName
    Write-Host "`nEstado de la tarea:" -ForegroundColor Cyan
    Write-Host "  Estado: $($task.State)"
    Write-Host "  Próxima ejecución: $(($task | Get-ScheduledTaskInfo).NextRunTime)"
    
    Write-Host "`nPara ver/editar la tarea, abre el Programador de Tareas:" -ForegroundColor Yellow
    Write-Host "  taskschd.msc"
    Write-Host "`nPara ejecutar manualmente:" -ForegroundColor Yellow
    Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
    Write-Host "`nPara desactivar:" -ForegroundColor Yellow
    Write-Host "  Disable-ScheduledTask -TaskName '$TaskName'"
    Write-Host "`nPara eliminar:" -ForegroundColor Yellow
    Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
}

Write-Host "`n"
