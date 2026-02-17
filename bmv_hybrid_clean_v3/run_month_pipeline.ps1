<# =======================================================================
  run_month_pipeline.ps1
  Orquesta el pipeline mensual:
   1) Descarga OHLCV diarios (yfinance) según los tickers/fechas del mes
   2) Construye targets (y_H3/y_H5) + evalúa modelos H3/H5
   3) Aplica inferencia (y_hat) + gate (por y_hat y/o prob_win)
   4) (Opcional) Simulación si existe scripts/simulate_trading.py

  Requisitos:
   - Python y dependencias: yfinance pandas numpy scikit-learn matplotlib tabulate
   - Scripts:
       scripts/download_daily_prices.py
       scripts/make_targets_and_eval.py
       scripts/infer_and_gate.py
  Uso:
   .\run_month_pipeline.ps1 -Month "2025-10" -ModelH "H3" -MinAbsY 0.06 -MinProb 0.60
======================================================================= #>

param(
  [string]$Month = "2025-10",
  [ValidateSet("H3","H5")] [string]$ModelH = "H3",
  [double]$MinAbsY = 0.06,
  [Nullable[double]]$MinProb = $null,
  [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

# --- Utilidades
function Assert-File($Path, $MsgIfMissing) {
  if (-not (Test-Path $Path)) {
    throw "$MsgIfMissing (`"$Path`")"
  }
}

function Run-Step($Title, [scriptblock]$Block) {
  Write-Host ""
  Write-Host "=== $Title ===" -ForegroundColor Cyan
  & $Block
  if ($LASTEXITCODE -ne 0) { throw "Fallo en paso: $Title" }
}

# --- Rutas base
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# Scripts requeridos
$dlScript   = "scripts/download_daily_prices.py"
$makeScript = "scripts/make_targets_and_eval.py"
$infScript  = "scripts/infer_and_gate.py"

Assert-File $dlScript   "Falta scripts/download_daily_prices.py"
Assert-File $makeScript "Falta scripts/make_targets_and_eval.py"
Assert-File $infScript  "Falta scripts/infer_and_gate.py"

# Archivos de entrada (features)
$forecastBase = "reports/forecast/$Month/forecast_${Month}_base.csv"
$featuresCsv  = "reports/forecast/latest_forecast_features.csv"
if (Test-Path $forecastBase) { $featuresCsv = $forecastBase }

Assert-File $featuresCsv "No se encontró el CSV de features del mes. Crea forecast_${Month}_base.csv o latest_forecast_features.csv"

# Salidas / modelos
$dataDailyCsv = "data/daily/ohlcv_daily.csv"
$labeledCsv   = "reports/forecast/$Month/features_labeled.csv"
$modelPath    = if ($ModelH -eq "H5") { "models/return_model_H5.joblib" } else { "models/return_model_H3.joblib" }
$probModel    = "models/prob_win_calibrated.joblib"
$signalsCsv   = "reports/forecast/$Month/forecast_${Month}_with_gate.csv"

# Crear carpetas destino
New-Item -ItemType Directory -Force -Path (Split-Path $dataDailyCsv)        | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $labeledCsv)          | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $signalsCsv)          | Out-Null

# --- Paso 1: Descargar OHLCV diarios
Run-Step "Paso 1/3 · Descargar históricos OHLCV" {
  & $PythonExe $dlScript --features-csv $featuresCsv --out-csv $dataDailyCsv
}
Assert-File $dataDailyCsv "No se generó el OHLCV diario"

# --- Paso 2: Construir targets + Evaluar modelos
Run-Step "Paso 2/3 · Construir targets (y_H3/y_H5) y evaluar modelos" {
  & $PythonExe $makeScript `
    --features-csv $featuresCsv `
    --prices-csv  $dataDailyCsv `
    --out-labeled $labeledCsv `
    --model-h3 "models/return_model_H3.joblib" `
    --model-h5 "models/return_model_H5.joblib"
}
Assert-File $labeledCsv "No se generó el features_labeled.csv"

# --- Paso 3: Inferencia + Gate
Run-Step "Paso 3/3 · Inferencia (y_hat) + gate" {
  if ($null -ne $MinProb) {
    & $PythonExe $infScript `
      --features-csv $labeledCsv `
      --out-csv $signalsCsv `
      --model $modelPath `
      --prob-model $probModel `
      --min-abs-y $MinAbsY `
      --min-prob $MinProb
  } else {
    & $PythonExe $infScript `
      --features-csv $labeledCsv `
      --out-csv $signalsCsv `
      --model $modelPath `
      --prob-model $probModel `
      --min-abs-y $MinAbsY
  }
}
Assert-File $signalsCsv "No se generó el archivo de señales con gate"

# --- (Opcional) Paso 4: Simulación si existe el script
$simulateScript = "scripts/simulate_trading.py"
if (Test-Path $simulateScript) {
  Write-Host ""
  Write-Host "=== Paso 4 (opcional) · Simulación detectada ===" -ForegroundColor Cyan
  $horizonDays = [int]($ModelH -replace "H","")
  & $PythonExe $simulateScript `
    --month $Month `
    --signals-csv $signalsCsv `
    --capital-initial 10000 `
    --fixed-cash 2000 `
    --tp-pct 0.08 `
    --sl-pct 0.001 `
    --horizon-days $horizonDays
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "La simulación reportó un error. Revisa el script y los argumentos."
  }
} else {
  Write-Host ""
  Write-Host "ℹ️ Paso 4 omitido: no se encontró $simulateScript" -ForegroundColor Yellow
}

# --- Resumen final
Write-Host ""
Write-Host "✅ Pipeline terminado." -ForegroundColor Green
Write-Host "   Mes        : $Month"
Write-Host "   Modelo     : $ModelH  ($modelPath)"
Write-Host "   MinAbsY    : $MinAbsY"
if ($null -ne $MinProb) { Write-Host "   MinProb    : $MinProb" }
Write-Host "   OHLCV      : $dataDailyCsv"
Write-Host "   Labeled    : $labeledCsv"
Write-Host "   Señales    : $signalsCsv"
