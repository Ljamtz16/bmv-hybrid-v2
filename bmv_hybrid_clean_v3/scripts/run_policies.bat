@echo off
setlocal enabledelayedexpansion

REM === Raíces (este .bat vive en scripts\) ===
set "ROOT=%~dp0.."
set "SCRIPTS=%~dp0"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "PYTHONPATH=%ROOT%"

REM === Configuración general ===
REM set "MONTHS= 2024-01 2024-02 2024-03 2024-04 2024-05 2024-06 2024-07 2024-08 2024-09 2024-10 2024-11 2024-12"
 set "MONTHS= 2025-01 2025-02 2025-03 2025-04 2025-05 2025-06 2025-07 2025-08 2025-09"

set "GRID_TP=0.06,0.08,0.10,0.12,0.18,0.20,0.22,0.25"
set "GRID_SL=0.001,0.002,0.003,0.004,0.005,0.008,0.010,0.012"
set "GRID_H=3,4,5"
set "MIN_ABS_Y=0.06"

set "PER_TRADE_CASH=2000"
set "MAX_OPEN=4"
set "BUDGET=10000"
set "COMMISSION_SIDE=5.0"
set "LONG_ONLY_FLAG=--long-only"

if not exist "%PY%" (
  echo [ERROR] No encontre el interprete del venv: "%PY%"
  echo         Activa el venv o ajusta la ruta %%PY%% al Python que quieras usar.
  exit /b 1
)

REM Carpetas de trabajo
if not exist "%ROOT%\runs" mkdir "%ROOT%\runs"

for %%M in (%MONTHS%) do (
  echo.
  echo ============ %%M ============

  REM 0) Forecast+Validate (solo si no existe el CSV de validacion)
  if not exist "%ROOT%\reports\forecast\%%M\validation\validation_join_auto.csv" (
    "%PY%" "%SCRIPTS%12_forecast_and_validate.py" --month %%M
    if errorlevel 1 goto :fail
  )

  REM 1) Open-limits (filtrado operativo)
  "%PY%" "%SCRIPTS%27_filter_open_limits.py" ^
    --in "%ROOT%\reports\forecast\%%M\validation\validation_join_auto.csv" ^
    --out "%ROOT%\runs\%%M_validation_join_auto_limited.csv" ^
    --decision-log "%ROOT%\runs\open_decisions_%%M.csv" ^
    --max-open %MAX_OPEN% ^
    --per-trade-cash %PER_TRADE_CASH% ^
    --budget %BUDGET%
  if errorlevel 1 goto :fail

  REM 2) Grid search
  if not exist "%ROOT%\runs\%%M_grid" mkdir "%ROOT%\runs\%%M_grid"
  "%PY%" "%SCRIPTS%27_policy_gridsearch.py" ^
    --month %%M ^
    --grid-tp %GRID_TP% ^
    --grid-sl %GRID_SL% ^
    --grid-h %GRID_H% ^
    --min-abs-y %MIN_ABS_Y% ^
    --per-trade-cash %PER_TRADE_CASH% ^
    --validation-dir "%ROOT%\reports\forecast\%%M\validation" ^
    --csv-in "%ROOT%\runs\%%M_validation_join_auto_limited.csv" ^
    --out-dir "%ROOT%\runs\%%M_grid" ^
    --summary-out "%ROOT%\runs\%%M_grid\grid_summary.csv" ^
    --use-inline
  if errorlevel 1 goto :fail

  REM 2b) Si NO existe el policy_best en runs\, crearlo desde el grid_summary
  set "BEST_JSON=%ROOT%\runs\policy_best_%%M.json"
  if not exist "!BEST_JSON!" (
    "%PY%" "%SCRIPTS%29_grid_pick_best.py" ^
      --grid-summary "%ROOT%\runs\%%M_grid\grid_summary.csv" ^
      --out-json "!BEST_JSON!" ^
      --min-abs-y %MIN_ABS_Y% ^
      --per-trade-cash %PER_TRADE_CASH% ^
      --commission-side %COMMISSION_SIDE% ^
      %LONG_ONLY_FLAG%
    if errorlevel 1 goto :fail
  )

  REM 3) Auditoría
  "%PY%" "%SCRIPTS%audit_policy_month.py" ^
    --month %%M ^
    --best-policy-json "%ROOT%\runs\policy_best_%%M.json" ^
    --limited-csv "%ROOT%\runs\%%M_validation_join_auto_limited.csv"
  if errorlevel 1 goto :fail

  REM 4) Promover a walk-forward box
  "%PY%" "%SCRIPTS%28_promote_policy_to_wfbox.py" ^
    --month %%M ^
    --policy-json "%ROOT%\runs\policy_best_%%M.json" ^
    --wf-csv "%ROOT%\wf_box\reports\forecast\policy_selected_walkforward.csv"
  if errorlevel 1 goto :fail
)

echo.
echo ================== LISTO ==================
echo Revisa: %ROOT%\wf_box\reports\forecast\policy_selected_walkforward.csv
echo y los resúmenes por mes en %ROOT%\runs\AAAA-MM_grid\grid_summary.csv
goto :eof

:fail
echo.
echo [FALLO] Se interrumpio en el mes actual. Revisa el mensaje arriba.
exit /b 1
