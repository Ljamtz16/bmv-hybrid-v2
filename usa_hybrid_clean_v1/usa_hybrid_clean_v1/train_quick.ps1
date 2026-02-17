# Entrenamiento rápido de modelos intraday
param(
    [string]$StartDate = "2025-10-20",
    [string]$EndDate = "2025-10-31",
    [int]$MaxTickers = 10
)

Write-Host "`n=== ENTRENAMIENTO MODELOS INTRADAY ===" -ForegroundColor Cyan
Write-Host "Periodo: $StartDate -> $EndDate" -ForegroundColor Yellow
Write-Host "Max tickers: $MaxTickers`n" -ForegroundColor Yellow

# Leer tickers
$tickersFile = "data\us\tickers_master.csv"
if (Test-Path $tickersFile) {
    $tickersList = (Import-Csv $tickersFile | Select-Object -First $MaxTickers).ticker -join ","
    Write-Host "[INFO] Usando $($tickersList.Split(',').Count) tickers`n" -ForegroundColor Cyan
} else {
    Write-Host "[ERROR] No se encuentra $tickersFile" -ForegroundColor Red
    exit 1
}

# FASE 1: Descargar datos
Write-Host "`n[1/5] Descargando datos historicos..." -ForegroundColor Green
Write-Host "Esto puede tomar 10-20 minutos...`n" -ForegroundColor Yellow

$start = [datetime]::ParseExact($StartDate, "yyyy-MM-dd", $null)
$end = [datetime]::ParseExact($EndDate, "yyyy-MM-dd", $null)
$current = $start

while ($current -le $end) {
    if ($current.DayOfWeek -ne [System.DayOfWeek]::Saturday -and 
        $current.DayOfWeek -ne [System.DayOfWeek]::Sunday) {
        
        $dateStr = $current.ToString("yyyy-MM-dd")
        Write-Host "  $dateStr..." -NoNewline
        
        python scripts\00_download_intraday.py --date $dateStr --interval 15m --tickers $tickersList --lookback-days 5 2>&1 | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host " OK" -ForegroundColor Green
        } else {
            Write-Host " SKIP" -ForegroundColor Yellow
        }
    }
    $current = $current.AddDays(1)
}

# FASE 2: Features
Write-Host "`n[2/5] Calculando features..." -ForegroundColor Green
python scripts\09_make_targets_intraday.py --start $StartDate --end $EndDate --interval 15m

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Features fallo" -ForegroundColor Red
    exit 1
}

# FASE 3: Entrenar clasificador
Write-Host "`n[3/5] Entrenando clasificador..." -ForegroundColor Green
python scripts\10_train_intraday.py --start $StartDate --end $EndDate --model-type rf

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Clasificador fallo" -ForegroundColor Red
    exit 1
}

# Verificar modelo
if (Test-Path "models\clf_intraday.joblib") {
    Write-Host "[OK] Modelo guardado" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Modelo no guardado" -ForegroundColor Red
    exit 1
}

# FASE 4: Entrenar TTH
Write-Host "`n[4/5] Entrenando TTH..." -ForegroundColor Green
python scripts\38_train_tth_intraday.py --start $StartDate --end $EndDate

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] TTH entrenado" -ForegroundColor Green
} else {
    Write-Host "[WARN] TTH fallo, continuando..." -ForegroundColor Yellow
}

# FASE 5: Calibracion
Write-Host "`n[5/5] Creando calibracion..." -ForegroundColor Green

$calibFile = "data\trading\tth_calibration_intraday.json"
if (-not (Test-Path $calibFile)) {
    '{"scale_tp": 1.0, "scale_sl": 1.0}' | Out-File -FilePath $calibFile -Encoding UTF8
    Write-Host "[OK] Calibracion creada" -ForegroundColor Green
} else {
    Write-Host "[INFO] Calibracion ya existe" -ForegroundColor Gray
}

# Resumen
Write-Host "`n=== COMPLETADO ===" -ForegroundColor Cyan
Write-Host "`nModelos:" -ForegroundColor Yellow
Get-ChildItem models\*intraday*.joblib | ForEach-Object {
    $sizeMB = [math]::Round($_.Length / 1MB, 1)
    Write-Host "  $($_.Name) - $sizeMB MB" -ForegroundColor Gray
}

Write-Host "`nProbar con:" -ForegroundColor Yellow
Write-Host "  .\run_intraday.ps1 -Date 2025-10-31 -Tickers AMD,NVDA,TSLA`n" -ForegroundColor Gray
