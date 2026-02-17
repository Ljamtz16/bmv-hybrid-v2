# Monitor simple de progreso
Write-Host "`n=== PROGRESO ENTRENAMIENTO ===" -ForegroundColor Cyan

# Descarga
Write-Host "`n[1] Datos descargados:" -ForegroundColor Yellow
$data = Get-ChildItem data\intraday -Recurse -Filter *.parquet -ErrorAction SilentlyContinue
if ($data) {
    $count = ($data | Measure-Object).Count
    $sizeMB = [math]::Round(($data | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
    Write-Host "  $count archivos - $sizeMB MB" -ForegroundColor Green
} else {
    Write-Host "  Pendiente" -ForegroundColor Gray
}

# Features
Write-Host "`n[2] Features calculadas:" -ForegroundColor Yellow
$features = Get-ChildItem features\intraday -Filter *.parquet -ErrorAction SilentlyContinue
if ($features) {
    $count = ($features | Measure-Object).Count
    Write-Host "  $count dias procesados" -ForegroundColor Green
} else {
    Write-Host "  Pendiente" -ForegroundColor Gray
}

# Modelos
Write-Host "`n[3] Modelos:" -ForegroundColor Yellow
$models = Get-ChildItem models -*intraday*.joblib -ErrorAction SilentlyContinue
if ($models) {
    foreach ($m in $models) {
        Write-Host "  [OK] $($m.Name)" -ForegroundColor Green
    }
} else {
    Write-Host "  Pendiente" -ForegroundColor Gray
}

Write-Host ""
