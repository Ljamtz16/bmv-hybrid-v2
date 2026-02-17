@echo off
REM Script para ejecutar el flujo completo de esta semana
REM 1. Generar planes (STANDARD + PROBWIN_55)
REM 2. Monitorizar con dashboard

setlocal enabledelayedexpansion

echo ================================================================================
echo PLAN DE ACCION SEMANAL - FLUJO COMPLETO
echo ================================================================================

for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set mydate=%%c-%%a-%%b)
for /f "tokens=1-2 delims=/:" %%a in ('time /t') do (set mytime=%%a:%%b)
echo.
echo Fecha: !mydate! !mytime!

REM [1] Generar planes
echo.
echo [1] GENERANDO PLANES
echo --------------------------------------------------------------------------------
echo Ejecutando: python generate_weekly_plans.py
echo.

.\.venv\Scripts\python.exe generate_weekly_plans.py
if errorlevel 1 (
    echo.
    echo ERROR: No se pudieron generar los planes
    exit /b 1
)

echo.
echo ^✓ Planes generados exitosamente

REM [2] Esperar
timeout /t 2 /nobreak > nul

REM [3] Iniciar dashboard
echo.
echo [2] INICIANDO DASHBOARD
echo --------------------------------------------------------------------------------
echo Ejecutando: python dashboard_compare_plans.py
echo.
echo Dashboard disponible en: http://localhost:7777
echo.
echo Presione Ctrl+C para detener el servidor
echo.

.\.venv\Scripts\python.exe dashboard_compare_plans.py

endlocal
