@echo off
REM ============================================================
REM  run_month_pipeline.bat
REM  Pipeline mensual para BMV Hybrid Clean:
REM   1) Descarga históricos diarios (yfinance)
REM   2) Construye targets y_H3 / y_H5 y evalúa modelos
REM   3) Aplica inferencia (y_hat) + gate (por y_hat / prob_win)
REM   4) (Opcional) Simulación si existe simulate_trading.py
REM ------------------------------------------------------------
REM  Uso:
REM     run_month_pipeline.bat 2025-10 H3 0.06 0.60
REM  Donde:
REM     %1 = Mes (AAAA-MM)
REM     %2 = Modelo (H3 o H5)
REM     %3 = MinAbsY (por defecto 0.06)
REM     %4 = MinProb (opcional, ej. 0.60)
REM ============================================================

setlocal enabledelayedexpansion

REM --- Parámetros ---
set "MONTH=%~1"
if "%MONTH%"=="" set "MONTH=2025-10"

set "MODELH=%~2"
if "%MODELH%"=="" set "MODELH=H3"

set "MINABSY=%~3"
if "%MINABSY%"=="" set "MINABSY=0.06"

set "MINPROB=%~4"

set "PYTHON=python"

echo ============================================================
echo 📅  Ejecutando pipeline mensual para %MONTH% (modelo %MODELH%)
echo ============================================================

REM --- Rutas base ---
set "FEATURES_CSV=reports\forecast\latest_forecast_features.csv"
set "FORECAST_BASE=reports\forecast\%MONTH%\forecast_%MONTH%_base.csv"
if exist "%FORECAST_BASE%" set "FEATURES_CSV=%FORECAST_BASE%"

set "DATA_DAILY=data\daily\ohlcv_daily.csv"
set "LABELED=reports\forecast\%MONTH%\features_labeled.csv"
set "SIGNALS=reports\forecast\%MONTH%\forecast_%MONTH%_with_gate.csv"

if "%MODELH%"=="H5" (
  set "MODEL_PATH=models\return_model_H5.joblib"
) else (
  set "MODEL_PATH=models\return_model_H3.joblib"
)
set "PROB_MODEL=models\prob_win_calibrated.joblib"

REM Crear carpetas necesarias
if not exist "data\daily" mkdir "data\daily"
if not exist "reports\forecast\%MONTH%" mkdir "reports\forecast\%MONTH%"

REM ------------------------------------------------------------
echo.
echo === Paso 1/3 · Descargando OHLCV diarios con yfinance ===
REM ------------------------------------------------------------
%PYTHON% scripts\download_daily_prices.py --features-csv "%FEATURES_CSV%" --out-csv "%DATA_DAILY%"
if errorlevel 1 (
  echo ❌ Error en descarga de precios. Abortando.
  exit /b 1
)

REM ------------------------------------------------------------
echo.
echo === Paso 2/3 · Construyendo targets y evaluando modelos ===
REM ------------------------------------------------------------
%PYTHON% scripts\make_targets_and_eval.py ^
  --features-csv "%FEATURES_CSV%" ^
  --prices-csv "%DATA_DAILY%" ^
  --out-labeled "%LABELED%" ^
  --model-h3 models\return_model_H3.joblib ^
  --model-h5 models\return_model_H5.joblib
if errorlevel 1 (
  echo ❌ Error en make_targets_and_eval.py. Abortando.
  exit /b 1
)

REM ------------------------------------------------------------
echo.
echo === Paso 3/3 · Inferencia (y_hat) + gate ===
REM ------------------------------------------------------------
if not "%MINPROB%"=="" (
  %PYTHON% scripts\infer_and_gate.py ^
    --features-csv "%LABELED%" ^
    --out-csv "%SIGNALS%" ^
    --model "%MODEL_PATH%" ^
    --prob-model "%PROB_MODEL%" ^
    --min-abs-y %MINABSY% ^
    --min-prob %MINPROB%
) else (
  %PYTHON% scripts\infer_and_gate.py ^
    --features-csv "%LABELED%" ^
    --out-csv "%SIGNALS%" ^
    --model "%MODEL_PATH%" ^
    --prob-model "%PROB_MODEL%" ^
    --min-abs-y %MINABSY%
)
if errorlevel 1 (
  echo ❌ Error en infer_and_gate.py. Abortando.
  exit /b 1
)

REM ------------------------------------------------------------
echo.
echo === Paso 4 (opcional) · Simulación ===
REM ------------------------------------------------------------
if exist "scripts\simulate_trading.py" (
  set "HORIZON_DAYS=%MODELH:H=%"
  %PYTHON% scripts\simulate_trading.py ^
    --month %MONTH% ^
    --signals-csv "%SIGNALS%" ^
    --capital-initial 10000 ^
    --fixed-cash 2000 ^
    --tp-pct 0.08 ^
    --sl-pct 0.001 ^
    --horizon-days %HORIZON_DAYS%
) else (
  echo ℹ️  No se encontró scripts\simulate_trading.py — simulación omitida.
)

REM ------------------------------------------------------------
echo.
echo ============================================================
echo ✅ PIPELINE TERMINADO
echo ------------------------------------------------------------
echo Mes:        %MONTH%
echo Modelo:     %MODELH%  (%MODEL_PATH%)
echo MinAbsY:    %MINABSY%
if not "%MINPROB%"=="" echo MinProb:    %MINPROB%
echo ------------------------------------------------------------
echo OHLCV:      %DATA_DAILY%
echo Labeled:    %LABELED%
echo Señales:    %SIGNALS%
echo ============================================================
echo.

pause
endlocal
exit /b 0
