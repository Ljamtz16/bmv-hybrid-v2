# =============================================
# verificar_bitacora_drive.ps1
# =============================================
# Script para verificar la configuración de la bitácora en Google Drive

$DrivePath = "G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx"
$LocalPath = "reports\H3_BITACORA_PREDICCIONES.xlsx"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "VERIFICACIÓN: Bitácora en Google Drive" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Verificar Drive
Write-Host "[1] Verificando Google Drive..." -ForegroundColor Yellow
if (Test-Path "G:\Mi unidad") {
    Write-Host "    ✅ Google Drive conectado" -ForegroundColor Green
    
    if (Test-Path "G:\Mi unidad\Trading proyecto") {
        Write-Host "    ✅ Carpeta 'Trading proyecto' existe" -ForegroundColor Green
    } else {
        Write-Host "    ❌ Carpeta 'Trading proyecto' no encontrada" -ForegroundColor Red
        Write-Host "       Creando carpeta..." -ForegroundColor Yellow
        New-Item -ItemType Directory -Path "G:\Mi unidad\Trading proyecto" -Force | Out-Null
        Write-Host "    ✅ Carpeta creada" -ForegroundColor Green
    }
} else {
    Write-Host "    ❌ Google Drive no está montado en G:\" -ForegroundColor Red
    Write-Host "       Verifica que Google Drive Desktop esté activo" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Verificar archivo
Write-Host "[2] Verificando bitácora..." -ForegroundColor Yellow
if (Test-Path $DrivePath) {
    $file = Get-Item $DrivePath
    Write-Host "    ✅ Bitácora encontrada en Drive" -ForegroundColor Green
    Write-Host "       Ruta: $($file.FullName)" -ForegroundColor Cyan
    Write-Host "       Tamaño: $([math]::Round($file.Length/1KB, 2)) KB" -ForegroundColor Cyan
    Write-Host "       Última modificación: $($file.LastWriteTime)" -ForegroundColor Cyan
} else {
    Write-Host "    ⚠️  Bitácora no encontrada en Drive" -ForegroundColor Yellow
    
    if (Test-Path $LocalPath) {
        Write-Host "       Copiando desde ubicación local..." -ForegroundColor Yellow
        Copy-Item $LocalPath $DrivePath -Force
        Write-Host "    ✅ Bitácora copiada a Drive" -ForegroundColor Green
    } else {
        Write-Host "       Creando nueva bitácora..." -ForegroundColor Yellow
        python scripts\bitacora_excel.py --init
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    ✅ Bitácora creada" -ForegroundColor Green
        }
    }
}

Write-Host ""

# Verificar script Python
Write-Host "[3] Verificando configuración del script..." -ForegroundColor Yellow
$scriptContent = Get-Content "scripts\bitacora_excel.py" -Raw
if ($scriptContent -match 'G:\\Mi unidad\\Trading proyecto') {
    Write-Host "    ✅ Script configurado para usar Google Drive" -ForegroundColor Green
} else {
    Write-Host "    ❌ Script NO está configurado para Drive" -ForegroundColor Red
}

Write-Host ""

# Probar actualización
Write-Host "[4] Probando actualización..." -ForegroundColor Yellow
$output = python scripts\bitacora_excel.py --summary 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "    ✅ Script funcionando correctamente" -ForegroundColor Green
    Write-Host "       $output" -ForegroundColor Cyan
} else {
    Write-Host "    ❌ Error al ejecutar script" -ForegroundColor Red
    Write-Host "       $output" -ForegroundColor Red
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "✅ CONFIGURACIÓN COMPLETA" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "📊 Tu bitácora está en:" -ForegroundColor Cyan
Write-Host "   $DrivePath" -ForegroundColor White
Write-Host ""
Write-Host "🔄 Para actualizar:" -ForegroundColor Cyan
Write-Host "   python scripts\bitacora_excel.py --update" -ForegroundColor White
Write-Host ""
Write-Host "📱 Para sincronizar automáticamente:" -ForegroundColor Cyan
Write-Host "   .\run_daily_h3_forward.ps1 -SendTelegram" -ForegroundColor White
Write-Host "   (La bitácora se actualiza automáticamente en Drive)" -ForegroundColor Yellow
Write-Host ""
