@echo off
setlocal enabledelayedexpansion

REM === Configuración específica para 2025-09 ===
set "MONTH=2025-09"

REM Grids y límites (ajústalos si quieres)
set "GRID_TP=0.06,0.08,0.10,0.12,0.18,0.20,0.22,0.25"
set "GRID_SL=0.001,0.002,0.003,0.004,0.005,0.008,0.010,0.012"
set "GRID_H=3,4,5"
set "MIN_ABS_Y=0.06"

set "PER_TRADE_CASH=2000"
set "MAX_OPEN=4"
set "BUDGET=10000"

REM Python del venv (la ruta es: repo\.venv\Scripts\python.exe)
set "PY=%~dp0..\ .venv\Scripts\python.exe"
set "PY=%PY: =%"  REM quita espacios accidentales

if not exist "%PY%" (
  echo [ERROR] No encontre el interprete del venv: "%PY%"
  echo         Activa el venv o ajusta la ruta %%PY%% al Python que quieras usar.
  exit /b 1
)

REM Carpetas base (desde la raiz del repo)
set "ROOT=%~dp0.."
set "RUNS=%ROOT%\runs"
set "REPORTS=%ROOT%\reports\forecast\%MONTH%"
set "VAL=%REPORTS%\validation"

if not exist "%RUNS%" mkdir "%RUNS%"

echo.
echo ============ %MONTH% ============

REM 0) Forecast+Validate si hace falta
if not exist "%VAL%\validation_join_auto.csv" (
  "%PY%" "%~dp0%12_forecast_and_validate.py" --month %MONTH%
  if errorlevel 1 goto :fail
)

REM 1) Open-limits
"%PY%" "%~dp0%27_filter_open_limits.py" ^
  --in "%VAL%\validation_join_auto.csv" ^
  --out "%RUNS%\%MONTH%_validation_join_auto_limited.csv" ^
  --decision-log "%RUNS%\open_decisions_%MONTH%.csv" ^
  --max-open %MAX_OPEN% ^
  --per-trade-cash %PER_TRADE_CASH% ^
  --budget %BUDGET%
if errorlevel 1 goto :fail

REM 2) Grid search
if not exist "%RUNS%\%MONTH%_grid" mkdir "%RUNS%\%MONTH%_grid"
"%PY%" "%~dp0%27_policy_gridsearch.py" ^
  --month %MONTH% ^
  --grid-tp %GRID_TP% ^
  --grid-sl %GRID_SL% ^
  --grid-h %GRID_H% ^
  --min-abs-y %MIN_ABS_Y% ^
  --per-trade-cash %PER_TRADE_CASH% ^
  --validation-dir "%VAL%" ^
  --csv-in "%RUNS%\%MONTH%_validation_join_auto_limited.csv" ^
  --out-dir "%RUNS%\%MONTH%_grid" ^
  --summary-out "%RUNS%\%MONTH%_grid\grid_summary.csv" ^
  --use-inline
if errorlevel 1 goto :fail

REM 3) Auditoria (recompute + vecindad + walk-forward inmediato a 2025-10 si existiera)
"%PY%" "%~dp0%audit_policy_month.py" ^
  --month %MONTH% ^
  --best-policy-json "%RUNS%\policy_best_%MONTH%.json" ^
  --limited-csv "%RUNS%\%MONTH%_validation_join_auto_limited.csv"
if errorlevel 1 goto :fail

REM 4) Promover a WF-box
"%PY%" "%~dp0%28_promote_policy_to_wfbox.py" ^
  --month %MONTH% ^
  --policy-json "%RUNS%\policy_best_%MONTH%.json" ^
  --wf-csv "%ROOT%\wf_box\reports\forecast\policy_selected_walkforward.csv"
if errorlevel 1 goto :fail

echo.
echo ================== LISTO ( %MONTH% ) ==================
echo Revisa: %ROOT%\wf_box\reports\forecast\policy_selected_walkforward.csv
echo Ranking: %RUNS%\%MONTH%_grid\grid_summary.csv
goto :eof

:fail
echo.
echo [FALLO] Se interrumpio en el mes actual. Revisa el mensaje arriba.
exit /b 1
