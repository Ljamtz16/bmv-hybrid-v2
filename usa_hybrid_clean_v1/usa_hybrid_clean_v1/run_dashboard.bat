@echo off
REM run_dashboard.bat - Lanzar dashboard en background con auto-restart

setlocal enabledelayedexpansion

set DASHBOARD_DIR=C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\usa_hybrid_clean_v1\usa_hybrid_clean_v1
set PYTHON=C:\Python312\python.exe
set DASHBOARD_SCRIPT=dashboard_unified.py
set LOG_FILE=%DASHBOARD_DIR%\dashboard_service.log
set ENV_FILE=C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\bmv_hybrid_clean_v3\scripts\.env
set PS_SENDER=C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v1\send_dashboard_url.ps1
set FLAG_FILE=%DASHBOARD_DIR%\val\telegram_sent.flag

echo ============================================================
echo Dashboard Trading Service
echo ============================================================
echo.
echo Directorio: %DASHBOARD_DIR%
echo Script: %DASHBOARD_SCRIPT%
echo Log: %LOG_FILE%
echo.

REM Verificar que Python existe
if not exist "%PYTHON%" (
    echo ERROR: Python no encontrado en %PYTHON%
    echo Edita run_dashboard.bat y cambia la ruta de PYTHON
    pause
    exit /b 1
)

REM Verificar que el script existe
if not exist "%DASHBOARD_DIR%\%DASHBOARD_SCRIPT%" (
    echo ERROR: Dashboard script no encontrado
    echo Ruta esperada: %DASHBOARD_DIR%\%DASHBOARD_SCRIPT%
    pause
    exit /b 1
)

REM Lanzar en loop con auto-restart
echo Iniciando Dashboard...
echo.

REM Enviar URL por Telegram una sola vez (si hay credenciales en .env)
if not exist "%FLAG_FILE%" (
    echo Preparando envío de URL por Telegram...
    timeout /t 5 /nobreak >nul
    if exist "%PS_SENDER%" (
        powershell -ExecutionPolicy Bypass -File "%PS_SENDER%"
    )
    if not exist "%DASHBOARD_DIR%\val" mkdir "%DASHBOARD_DIR%\val" >nul 2>&1
    echo SENT>"%FLAG_FILE%"
)

:restart
echo [%date% %time%] Iniciando... >> "%LOG_FILE%"
echo Escuchando en 0.0.0.0:7777
echo Revisa el dashboard en: http://127.0.0.1:7777/?token=XXXXX (de la consola de abajo)
echo.

cd /d "%DASHBOARD_DIR%"
"%PYTHON%" "%DASHBOARD_SCRIPT%" >> "%LOG_FILE%" 2>&1

echo.
echo [%date% %time%] Dashboard se cerró (codigo: %ERRORLEVEL%) >> "%LOG_FILE%"
echo.
echo Dashboard se cerró. Reiniciando en 5 segundos...
echo Presiona Ctrl+C para detener

timeout /t 5 /nobreak

goto restart
