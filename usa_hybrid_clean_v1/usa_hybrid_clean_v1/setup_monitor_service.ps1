# =============================================
# setup_monitor_service.ps1
# =============================================
# Configurar monitor de bitácora como servicio de Windows
# Requiere permisos de administrador

param(
    [ValidateSet('Install', 'Uninstall', 'Start', 'Stop', 'Status')]
    [string]$Action = 'Install',
    [int]$IntervalMinutes = 5
)

$ServiceName = "H3_BitacoraMonitor"
$ServiceDisplayName = "H3 Bitácora Monitor"
$ServiceDescription = "Monitor continuo de predicciones H3 - actualiza bitácora cada $IntervalMinutes minutos"
$ScriptPath = $PSScriptRoot
$MonitorScript = Join-Path $ScriptPath "monitor_bitacora.ps1"
$PythonScript = Join-Path $ScriptPath "monitor_bitacora.py"

# Verificar admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin -and ($Action -eq 'Install' -or $Action -eq 'Uninstall')) {
    Write-Host "❌ Este script requiere permisos de administrador para instalar/desinstalar servicios" -ForegroundColor Red
    Write-Host ""
    Write-Host "Opciones:" -ForegroundColor Yellow
    Write-Host "  1. Ejecutar PowerShell como Administrador y volver a correr este script"
    Write-Host "  2. Usar el monitor sin servicio (mantener ventana abierta):"
    Write-Host "     .\monitor_bitacora.ps1"
    exit 1
}

switch ($Action) {
    'Install' {
        Write-Host "📦 Instalando servicio de monitor..." -ForegroundColor Cyan
        
        # Verificar si ya existe
        $existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($existingService) {
            Write-Host "⚠️  El servicio ya existe. Desinstalando versión anterior..." -ForegroundColor Yellow
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            sc.exe delete $ServiceName
            Start-Sleep -Seconds 2
        }
        
        # Crear script wrapper para NSSM o usar PowerShell directamente
        # Opción 1: Usar NSSM (recomendado)
        $nssmPath = "C:\Program Files\NSSM\nssm.exe"
        
        if (Test-Path $nssmPath) {
            Write-Host "✅ Usando NSSM para crear servicio..." -ForegroundColor Green
            
            # Instalar con NSSM
            & $nssmPath install $ServiceName "powershell.exe" "-NoProfile -ExecutionPolicy Bypass -File `"$MonitorScript`" -Continuous -Silent"
            & $nssmPath set $ServiceName AppDirectory $ScriptPath
            & $nssmPath set $ServiceName DisplayName $ServiceDisplayName
            & $nssmPath set $ServiceName Description $ServiceDescription
            & $nssmPath set $ServiceName Start SERVICE_AUTO_START
            
            Write-Host "✅ Servicio instalado con NSSM" -ForegroundColor Green
        }
        else {
            Write-Host "⚠️  NSSM no encontrado. Instalando con método alternativo..." -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Recomendación: Descargar NSSM desde https://nssm.cc/" -ForegroundColor Yellow
            Write-Host "O usar Task Scheduler en su lugar (más confiable)" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Configurando con Task Scheduler en su lugar..." -ForegroundColor Cyan
            
            # Crear tarea programada en su lugar
            $trigger = New-ScheduledTaskTrigger -AtStartup
            $action = New-ScheduledTaskAction -Execute "powershell.exe" `
                -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$MonitorScript`" -Continuous -Silent"
            $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
            $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
            
            Register-ScheduledTask -TaskName $ServiceName `
                -Trigger $trigger `
                -Action $action `
                -Principal $principal `
                -Settings $settings `
                -Description $ServiceDescription `
                -Force
            
            Write-Host "✅ Servicio instalado como Tarea Programada" -ForegroundColor Green
        }
        
        Write-Host ""
        Write-Host "📋 Próximos pasos:" -ForegroundColor Cyan
        Write-Host "  .\setup_monitor_service.ps1 -Action Start     # Iniciar servicio"
        Write-Host "  .\setup_monitor_service.ps1 -Action Status    # Ver estado"
        Write-Host "  .\setup_monitor_service.ps1 -Action Stop      # Detener servicio"
        Write-Host ""
    }
    
    'Uninstall' {
        Write-Host "🗑️  Desinstalando servicio de monitor..." -ForegroundColor Cyan
        
        # Intentar NSSM primero
        $nssmPath = "C:\Program Files\NSSM\nssm.exe"
        if (Test-Path $nssmPath) {
            & $nssmPath stop $ServiceName
            & $nssmPath remove $ServiceName confirm
        }
        else {
            # Intentar servicio tradicional
            $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
            if ($service) {
                Stop-Service -Name $ServiceName -Force
                sc.exe delete $ServiceName
            }
            
            # Intentar tarea programada
            $task = Get-ScheduledTask -TaskName $ServiceName -ErrorAction SilentlyContinue
            if ($task) {
                Unregister-ScheduledTask -TaskName $ServiceName -Confirm:$false
            }
        }
        
        Write-Host "✅ Servicio desinstalado" -ForegroundColor Green
    }
    
    'Start' {
        Write-Host "▶️  Iniciando servicio de monitor..." -ForegroundColor Cyan
        
        # Intentar como servicio
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service) {
            Start-Service -Name $ServiceName
            Write-Host "✅ Servicio iniciado" -ForegroundColor Green
        }
        else {
            # Intentar como tarea programada
            $task = Get-ScheduledTask -TaskName $ServiceName -ErrorAction SilentlyContinue
            if ($task) {
                Start-ScheduledTask -TaskName $ServiceName
                Write-Host "✅ Tarea iniciada" -ForegroundColor Green
            }
            else {
                Write-Host "❌ Servicio no encontrado. Instálalo primero con:" -ForegroundColor Red
                Write-Host "   .\setup_monitor_service.ps1 -Action Install" -ForegroundColor Yellow
            }
        }
    }
    
    'Stop' {
        Write-Host "⏹️  Deteniendo servicio de monitor..." -ForegroundColor Cyan
        
        # Intentar como servicio
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service) {
            Stop-Service -Name $ServiceName -Force
            Write-Host "✅ Servicio detenido" -ForegroundColor Green
        }
        else {
            # Intentar como tarea programada
            $task = Get-ScheduledTask -TaskName $ServiceName -ErrorAction SilentlyContinue
            if ($task) {
                Stop-ScheduledTask -TaskName $ServiceName
                Write-Host "✅ Tarea detenida" -ForegroundColor Green
            }
            else {
                Write-Host "❌ Servicio no encontrado" -ForegroundColor Red
            }
        }
    }
    
    'Status' {
        Write-Host ""
        Write-Host "============================================" -ForegroundColor Cyan
        Write-Host "  ESTADO DEL MONITOR" -ForegroundColor Cyan
        Write-Host "============================================" -ForegroundColor Cyan
        Write-Host ""
        
        # Verificar servicio
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service) {
            Write-Host "Tipo: Servicio de Windows" -ForegroundColor White
            Write-Host "Estado: $($service.Status)" -ForegroundColor $(if ($service.Status -eq 'Running') { 'Green' } else { 'Yellow' })
            Write-Host "Inicio: $($service.StartType)" -ForegroundColor White
        }
        else {
            # Verificar tarea programada
            $task = Get-ScheduledTask -TaskName $ServiceName -ErrorAction SilentlyContinue
            if ($task) {
                Write-Host "Tipo: Tarea Programada" -ForegroundColor White
                Write-Host "Estado: $($task.State)" -ForegroundColor $(if ($task.State -eq 'Running') { 'Green' } else { 'Yellow' })
                
                $taskInfo = Get-ScheduledTaskInfo -TaskName $ServiceName
                Write-Host "Ultima ejecucion: $($taskInfo.LastRunTime)" -ForegroundColor White
                Write-Host "Proxima ejecucion: $($taskInfo.NextRunTime)" -ForegroundColor White
            }
            else {
                Write-Host "Estado: No instalado" -ForegroundColor Red
                Write-Host ""
                Write-Host "Para instalar:" -ForegroundColor Yellow
                Write-Host "  .\setup_monitor_service.ps1 -Action Install" -ForegroundColor White
            }
        }
        
        Write-Host ""
        Write-Host "============================================" -ForegroundColor Cyan
        Write-Host ""
    }
}
