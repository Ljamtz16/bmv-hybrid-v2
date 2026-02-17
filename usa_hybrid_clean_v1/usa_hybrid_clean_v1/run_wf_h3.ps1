# ==============================================================================
# WALK-FORWARD H3 - PIPELINE AUTOMATIZADO
# ==============================================================================
# Ejecuta validación walk-forward completa para Sep-Nov 2025
# Genera n≥50 trades out-of-sample con parámetros congelados
# ==============================================================================

param(
    [string[]]$Months = @("2025-09","2025-10","2025-11"),
    [string]$Policy = "policies\Policy_H3_WF.json",
    [string]$OutputReport = "reports\H3_WALKFORWARD_VALIDATION.json"
)

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "WALK-FORWARD H3 - VALIDACIÓN OUT-OF-SAMPLE" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Meses: $($Months -join ', ')" -ForegroundColor Yellow
Write-Host "Política: $Policy" -ForegroundColor Yellow
Write-Host "Output: $OutputReport" -ForegroundColor Yellow
Write-Host ""

# Verificar que existe la política
if (-not (Test-Path $Policy)) {
    Write-Host "❌ ERROR: Política no encontrada: $Policy" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Política verificada" -ForegroundColor Green
Write-Host ""

# ==============================================================================
# PASO 1: INFERENCIA + GATING POR MES
# ==============================================================================
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "PASO 1: INFERENCIA + GATING" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""

foreach ($month in $Months) {
    Write-Host "📊 Procesando $month..." -ForegroundColor Yellow
    
    # Inferencia y gating
    python scripts\infer_and_gate.py --month $month
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ ERROR en inferencia $month" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✅ Inferencia $month completada" -ForegroundColor Green
    Write-Host ""
}

# ==============================================================================
# PASO 2: SIMULACIÓN H3 (PRIMER TOQUE + EXPIRY)
# ==============================================================================
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "PASO 2: SIMULACIÓN H3" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "⚠️  Nota: Usando backtest existente (simulate_trading.py)" -ForegroundColor Yellow
Write-Host "   Verifica que incluya regla primer toque y expiry D+4" -ForegroundColor Yellow
Write-Host ""

# El backtest ya está ejecutado en el pipeline normal
# Solo verificamos que existan los archivos

foreach ($month in $Months) {
    $tradesFile = "reports\forecast\$month\trades_detailed.csv"
    
    if (Test-Path $tradesFile) {
        Write-Host "✅ Trades $month encontrados: $tradesFile" -ForegroundColor Green
    } else {
        Write-Host "❌ ERROR: No se encontraron trades para $month" -ForegroundColor Red
        Write-Host "   Ejecuta primero el pipeline completo para $month" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ""

# ==============================================================================
# PASO 3: VALIDACIÓN EXTENDIDA (KPIs + WILSON + CURVAS)
# ==============================================================================
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "PASO 3: VALIDACIÓN EXTENDIDA" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "📈 Generando reporte walk-forward..." -ForegroundColor Yellow

# Crear script Python inline para ejecutar validación
$pythonScript = @"
from scripts.validate_h3_extended import generate_walkforward_report
import json

months = ['$($Months -join "','")']
results = generate_walkforward_report(months)

# Guardar también en formato legible
with open('reports/H3_WF_SUMMARY.txt', 'w') as f:
    f.write('=' * 80 + '\n')
    f.write('WALK-FORWARD H3 VALIDATION SUMMARY\n')
    f.write('=' * 80 + '\n\n')
    
    if results:
        # Agregado
        total_trades = sum(r['sample_size'] for r in results)
        total_tp = sum(r['outcomes']['TP_HIT'] for r in results)
        total_pnl = sum(r['risk']['total_pnl'] for r in results)
        
        f.write(f'Total trades: {total_trades}\n')
        f.write(f'Win rate: {total_tp/total_trades:.1%}\n')
        f.write(f'PnL total: USD {total_pnl:.2f}\n')
        f.write(f'Return: {(total_pnl/1100)*100:.1f}%\n\n')
        
        # Por mes
        for r in results:
            f.write(f'\n{r["month"]}:\n')
            f.write(f'  Trades: {r["sample_size"]}\n')
            f.write(f'  Win rate: {r["win_rate"]["point_estimate"]:.1%}\n')
            f.write(f'  EV net: {r["expectancy"]["ev_net_pct"]:.2%}\n')
            f.write(f'  ETTH: {r["duration"]["etth_median_days"]:.1f}d\n')
            f.write(f'  MDD: {r["risk"]["mdd_pct"]:.2%}\n')
            f.write(f'  Status: {"✅ PASS" if r["all_criteria_passed"] else "❌ FAIL"}\n')

print('\n✅ Reporte generado: reports/H3_WF_SUMMARY.txt')
"@

$pythonScript | python

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ ERROR en validación extendida" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✅ Validación completada" -ForegroundColor Green
Write-Host ""

# ==============================================================================
# PASO 4: MOSTRAR RESULTADOS
# ==============================================================================
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "RESULTADOS WALK-FORWARD" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path "reports\H3_WF_SUMMARY.txt") {
    Get-Content "reports\H3_WF_SUMMARY.txt"
} else {
    Write-Host "⚠️  No se generó resumen legible" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "ARCHIVOS GENERADOS" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "✅ reports\H3_WALKFORWARD_VALIDATION.json (datos estructurados)" -ForegroundColor Green
Write-Host "✅ reports\H3_WF_SUMMARY.txt (resumen legible)" -ForegroundColor Green
Write-Host ""

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "PRÓXIMOS PASOS" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Revisar resultados en H3_WF_SUMMARY.txt" -ForegroundColor Yellow
Write-Host "2. Verificar criterios de aceptacion:" -ForegroundColor Yellow
Write-Host "   - n_trades >= 50" -ForegroundColor White
Write-Host "   - p_win >= 62%" -ForegroundColor White
Write-Host "   - EV_net >= 3.5%" -ForegroundColor White
Write-Host "   - ETTH <= 4d" -ForegroundColor White
Write-Host "   - MDD menor que 6%" -ForegroundColor White
Write-Host ""
Write-Host "3. Consultar semaforo de decision:" -ForegroundColor Yellow
Write-Host "   [VERDE] Todos pasan -> operar H3 en vivo" -ForegroundColor White
Write-Host "   [AMARILLO] 1 falla leve -> piloto 1-2 slots" -ForegroundColor White
Write-Host "   [ROJO] 2+ fallan -> revisar y repetir WF" -ForegroundColor White
Write-Host ""

Write-Host "================================================================================" -ForegroundColor Green
Write-Host "WALK-FORWARD COMPLETADO ✅" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Green
