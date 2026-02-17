# run_full_analysis.ps1
# Script para ejecutar análisis completo y abrir dashboard

Write-Host "" -ForegroundColor Green
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "ANÁLISIS PREDICCIÓN VS REALIDAD - USA HYBRID CLEAN V1" -ForegroundColor Yellow
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

$PythonExe = ".venv\Scripts\python.exe"

# Verificar que python existe
if (-not (Test-Path $PythonExe)) {
    Write-Host "❌ No encontrado: $PythonExe" -ForegroundColor Red
    Write-Host "Asegúrate de que el virtual environment está activado" -ForegroundColor Yellow
    exit 1
}

Write-Host "📊 Paso 1: Analizando predicción vs realidad..." -ForegroundColor Cyan
& $PythonExe analysis_pred_vs_real.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error en analysis_pred_vs_real.py" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "💰 Paso 2: Analizando resultados de trading..." -ForegroundColor Cyan
& $PythonExe analysis_trading_results.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error en analysis_trading_results.py" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "📋 Paso 3: Generando reporte ejecutivo..." -ForegroundColor Cyan
& $PythonExe generate_analysis_report.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error en generate_analysis_report.py" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Green
Write-Host "✅ ANÁLISIS COMPLETO" -ForegroundColor Green
Write-Host "=" * 80 -ForegroundColor Green
Write-Host ""

Write-Host "📊 Outputs disponibles:" -ForegroundColor Yellow
Write-Host "  • 24 gráficas PNG en: outputs\analysis\" -ForegroundColor White
Write-Host "  • Dashboard interactivo: analysis_dashboard.html" -ForegroundColor White
Write-Host "  • Reporte ejecutivo: outputs\ANALYSIS_REPORT.txt" -ForegroundColor White
Write-Host ""

Write-Host "🌐 Abriendo dashboard en navegador..." -ForegroundColor Cyan
Write-Host ""

& $PythonExe open_dashboard.py

Write-Host ""
Write-Host "✅ ¡Listo! Explora el dashboard con las 5 pestañas:" -ForegroundColor Green
Write-Host "  1. 📈 Resumen - KPIs principales" -ForegroundColor White
Write-Host "  2. 📉 Regresión - Gráficas de predicción" -ForegroundColor White
Write-Host "  3. 📊 Probabilidad - Curvas de calibración" -ForegroundColor White
Write-Host "  4. 💰 Trading - Resultados de equity curve" -ForegroundColor White
Write-Host "  5. 💡 Interpretación - Análisis y recomendaciones" -ForegroundColor White
Write-Host ""
