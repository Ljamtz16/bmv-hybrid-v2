@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================
rem Configuracion por defecto
rem ============================
set "PY=python"

rem Mes objetivo (AAAA-MM). Si no se pasa, toma el actual via PowerShell.
if "%~1"=="" (
  for /f %%I in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyy-MM')"') do set "MONTH=%%I"
) else (
  set "MONTH=%~1"
)

rem Horizonte (3 o 5)
if "%~2"=="" (
  set "H=3"
) else (
  set "H=%~2"
)

rem Umbral abs(y_hat)
if "%~3"=="" (
  set "MIN_ABS_Y=0.06"
) else (
  set "MIN_ABS_Y=%~3"
)

rem TP y SL por defecto
set "TP=0.08"
set "SL=0.02"

rem Rutas clave
set "FEATURES_CSV=reports\forecast\latest_forecast_features.csv"
set "PRICES_CSV=data\daily\ohlcv_daily.csv"
set "LABELED_CSV=reports\forecast\%MONTH%\features_labeled.csv"
set "FORECAST_CSV=reports\forecast\%MONTH%\forecast_%MONTH%_with_gate.csv"
set "MODEL_H3=models\return_model_H3.joblib"
set "MODEL_H5=models\return_model_H5.joblib"

set "PROB_MODEL="
if exist "models\prob_win_clean.joblib" set "PROB_MODEL=models\prob_win_clean.joblib"
if not defined PROB_MODEL if exist "models\prob_win_calibrated.joblib" set "PROB_MODEL=models\prob_win_calibrated.joblib"

echo ============================================================
echo Ejecutando pipeline mensual para %MONTH%
echo Parametros: H=%H%  abs_y_min=%MIN_ABS_Y%
echo ============================================================

rem Crear carpetas
if not exist "reports\forecast\%MONTH%" mkdir "reports\forecast\%MONTH%"
if not exist "data\daily" mkdir "data\daily"

rem ============================
rem Paso 1: Descargar OHLCV
rem ============================
echo.
echo === Paso 1/4 - Descargando OHLCV diarios con yfinance ===
if not exist "scripts\download_daily_prices.py" (
  echo [ERROR] No se encuentra scripts\download_daily_prices.py
  goto :ERR
)
"%PY%" "scripts\download_daily_prices.py" --features-csv "%FEATURES_CSV%" --out-csv "%PRICES_CSV%"
if errorlevel 1 (
  echo [ERROR] download_daily_prices.py fallo.
  goto :ERR
) else (
  echo OK: OHLCV guardado en %PRICES_CSV%
)

rem ============================
rem Paso 1.5: ret_20d_vol (opcional)
rem ============================
echo.
echo === Paso 1.5/4 - Anadiendo ret_20d_vol a features (si existe el script) ===
if exist "scripts\make_ret20d_vol.py" (
  "%PY%" "scripts\make_ret20d_vol.py"
  if errorlevel 1 (
    echo [WARN] make_ret20d_vol.py devolvio error; continuo.
  ) else (
    echo OK: ret_20d_vol agregado a %FEATURES_CSV%
  )
) else (
  echo Nota: no existe scripts\make_ret20d_vol.py; se omite.
)

rem ============================
rem Paso 2: Targets y evaluacion
rem ============================
echo.
echo === Paso 2/4 - Construyendo targets y evaluando modelos ===
if not exist "scripts\make_targets_and_eval.py" (
  echo [ERROR] No se encuentra scripts\make_targets_and_eval.py
  goto :ERR
)
"%PY%" "scripts\make_targets_and_eval.py" --features-csv "%FEATURES_CSV%" --prices-csv "%PRICES_CSV%" --out-labeled "%LABELED_CSV%" --model-h3 "%MODEL_H3%" --model-h5 "%MODEL_H5%"
if errorlevel 1 (
  echo [ERROR] make_targets_and_eval.py fallo.
  goto :ERR
) else (
  echo OK: Labeled listo en %LABELED_CSV%
)

rem ============================
rem Paso 3: Inferencia + Gate
rem ============================
echo.
echo === Paso 3/4 - Inferencia y gate ===
if not exist "scripts\infer_and_gate.py" (
  echo [ERROR] No se encuentra scripts\infer_and_gate.py
  goto :ERR
)

set "PROB_OPT="
if defined PROB_MODEL set "PROB_OPT=--prob-model %PROB_MODEL%"

if defined PROB_MODEL (
  "%PY%" "scripts\infer_and_gate.py" --features-csv "%LABELED_CSV%" --out-csv "%FORECAST_CSV%" --model "%MODEL_H3%" --min-abs-y %MIN_ABS_Y% %PROB_OPT%
) else (
  "%PY%" "scripts\infer_and_gate.py" --features-csv "%LABELED_CSV%" --out-csv "%FORECAST_CSV%" --model "%MODEL_H3%" --min-abs-y %MIN_ABS_Y%
)

if errorlevel 1 (
  echo [ERROR] infer_and_gate.py fallo.
  goto :ERR
) else (
  echo OK: Senales guardadas en %FORECAST_CSV%
)

rem ============================
rem Paso 4: Simulacion
rem ============================
echo.
echo === Paso 4/4 - Simulacion de trading ===
if exist "scripts\simulate_trading.py" (
  "%PY%" "scripts\simulate_trading.py" --month %MONTH% --signals-csv "%FORECAST_CSV%" --capital-initial 10000 --fixed-cash 2000 --tp-pct %TP% --sl-pct %SL% --horizon-days %H%
  if errorlevel 1 (
    echo [WARN] simulate_trading devolvio error; pipeline continua.
  )
) else (
  echo Nota: no existe scripts\simulate_trading.py; se omite simulacion.
)

rem ============================
rem Resumen
rem ============================
echo.
echo ============================================================
echo PIPELINE TERMINADO
echo ------------------------------------------------------------
echo Mes:        %MONTH%
echo Modelo:     H3  (%MODEL_H3%)
if defined PROB_MODEL echo ProbModel:  %PROB_MODEL%
echo H:          %H%
echo abs_y_min:  %MIN_ABS_Y%
echo ------------------------------------------------------------
echo OHLCV:      %PRICES_CSV%
echo Labeled:    %LABELED_CSV%
echo Senales:    %FORECAST_CSV%
echo ============================================================
goto :EOF

:ERR
echo.
echo ============================================================
echo PIPELINE ABORTADO
echo Revisa el error indicado en el paso correspondiente.
echo ============================================================
exit /b 1
