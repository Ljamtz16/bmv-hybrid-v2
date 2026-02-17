# Monitor de progreso del entrenamiento
Write-Host "`n=== MONITOR ENTRENAMIENTO INTRADAY ===" -ForegroundColor Cyan

# Fase 1: Descarga
Write-Host "`n[1] DESCARGA DE DATOS:" -ForegroundColor Yellow
$dataFiles = Get-ChildItem data\intraday -Recurse -Filter *.parquet -ErrorAction SilentlyContinue
if ($dataFiles) {
    $totalFiles = ($dataFiles | Measure-Object).Count
    $totalSizeMB = [math]::Round(($dataFiles | Measure-Object -Property Length -Sum).Sum / 1MB, 2)
    Write-Host "  Archivos: $totalFiles" -ForegroundColor Green
    Write-Host "  Tamaño: $totalSizeMB MB" -ForegroundColor Green
    
    # Últimos 5 archivos
    Write-Host "`n  Últimos descargados:" -ForegroundColor Cyan
    $dataFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 5 | ForEach-Object {
        $time = $_.LastWriteTime.ToString("HH:mm:ss")
        Write-Host "    [$time] $($_.Directory.Name)\$($_.Name)" -ForegroundColor Gray
    }
} else {
    Write-Host "  Sin datos aún" -ForegroundColor Gray
}

# Fase 2: Features
Write-Host "`n[2] FEATURES CALCULADAS:" -ForegroundColor Yellow
$featureFiles = Get-ChildItem features\intraday -Filter *.parquet -ErrorAction SilentlyContinue
if ($featureFiles) {
    $totalFeatures = ($featureFiles | Measure-Object).Count
    Write-Host "  Archivos: $totalFeatures días procesados" -ForegroundColor Green
    
    # Último archivo
    $lastFeature = $featureFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($lastFeature) {
        Write-Host "  Último: $($lastFeature.Name) - $($lastFeature.LastWriteTime.ToString('HH:mm:ss'))" -ForegroundColor Gray
    }
} else {
    Write-Host "  Pendiente" -ForegroundColor Gray
}

# Fase 3: Modelos
Write-Host "`n[3] MODELOS ENTRENADOS:" -ForegroundColor Yellow
$models = Get-ChildItem models -Filter *intraday*.joblib -ErrorAction SilentlyContinue
if ($models) {
    foreach ($model in $models) {
        $sizeMB = [math]::Round($model.Length / 1MB, 2)
        $time = $model.LastWriteTime.ToString("HH:mm:ss")
        Write-Host "  [OK] $($model.Name) - $sizeMB MB ($time)" -ForegroundColor Green
    }
} else {
    Write-Host "  Pendiente" -ForegroundColor Gray
}

# Fase 4: Calibración
Write-Host "`n[4] CALIBRACIÓN:" -ForegroundColor Yellow
$calibFile = "data\trading\tth_calibration_intraday.json"
if (Test-Path $calibFile) {
    $calib = Get-Content $calibFile | ConvertFrom-Json
    Write-Host "  [OK] scale_tp: $($calib.scale_tp), scale_sl: $($calib.scale_sl)" -ForegroundColor Green
} else {
    Write-Host "  Pendiente" -ForegroundColor Gray
}

# Resumen
Write-Host "`n=== RESUMEN ===" -ForegroundColor Cyan
$hasData = $dataFiles -ne $null
$hasFeatures = $featureFiles -ne $null
$hasModel = Test-Path "models\clf_intraday.joblib"
$hasTTH = Test-Path "models\tth_hazard_intraday.joblib"

Write-Host "  Descarga: $(if ($hasData) { 'En progreso/Completa' } else { 'Pendiente' })" -ForegroundColor $(if ($hasData) { 'Green' } else { 'Yellow' })
Write-Host "  Features: $(if ($hasFeatures) { 'En progreso/Completa' } else { 'Pendiente' })" -ForegroundColor $(if ($hasFeatures) { 'Green' } else { 'Yellow' })
Write-Host "  Clasificador: $(if ($hasModel) { 'Listo' } else { 'Pendiente' })" -ForegroundColor $(if ($hasModel) { 'Green' } else { 'Yellow' })
Write-Host "  TTH: $(if ($hasTTH) { 'Listo' } else { 'Pendiente' })" -ForegroundColor $(if ($hasTTH) { 'Green' } else { 'Yellow' })

if ($hasModel) {
    Write-Host "`n[SUCCESS] Entrenamiento completado! Puedes ejecutar:" -ForegroundColor Green
    Write-Host "  .\run_intraday.ps1 -Date 2025-10-31 -Tickers AMD,NVDA,TSLA" -ForegroundColor Gray
} else {
    Write-Host "`n[INFO] Entrenamiento en progreso... Ejecuta este script de nuevo para actualizar." -ForegroundColor Cyan
}
Write-Host ""
