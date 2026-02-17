# Walk-Forward H3 - Pipeline Automatizado
# Ejecuta validacion walk-forward Sep-Nov 2025

param(
    [string[]]$Months = @("2025-09","2025-10","2025-11")
)

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "WALK-FORWARD H3 - VALIDACION OUT-OF-SAMPLE" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Meses: $($Months -join ', ')" -ForegroundColor Yellow
Write-Host ""

# PASO 1: Verificar que existen los datos
Write-Host "PASO 1: Verificando datos..." -ForegroundColor Yellow
foreach ($month in $Months) {
    $tradesFile = "reports\forecast\$month\trades_detailed.csv"
    
    if (Test-Path $tradesFile) {
        Write-Host "[OK] $month - trades encontrados" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] $month - ejecuta pipeline primero" -ForegroundColor Red
        Write-Host "Comando: python scripts\infer_and_gate.py --month $month" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ""

# PASO 2: Ejecutar validacion extendida
Write-Host "PASO 2: Ejecutando validacion extendida..." -ForegroundColor Yellow
Write-Host ""

python -c @"
from scripts.validate_h3_extended import generate_walkforward_report
results = generate_walkforward_report(['$($Months -join "','")'])
"@

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Validacion fallida" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[OK] Validacion completada" -ForegroundColor Green
Write-Host ""

# PASO 3: Mostrar resultados
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "RESULTADOS" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path "reports\H3_WALKFORWARD_VALIDATION.json") {
    Write-Host "[OK] Reporte JSON generado" -ForegroundColor Green
    Write-Host ""
    
    # Mostrar resumen rapido con Python
    python -c @"
import json
with open('reports/H3_WALKFORWARD_VALIDATION.json', 'r') as f:
    data = json.load(f)
    
if data:
    total_trades = sum(r['sample_size'] for r in data)
    total_tp = sum(r['outcomes']['TP_HIT'] for r in data)
    
    print(f'Total trades: {total_trades}')
    print(f'Win rate: {total_tp/total_trades:.1%}')
    print(f'')
    
    for r in data:
        status = 'PASS' if r['all_criteria_passed'] else 'FAIL'
        print(f'{r["month"]}: {r["sample_size"]} trades, win {r["win_rate"]["point_estimate"]:.1%} - {status}')
"@
}

Write-Host ""
Write-Host "====================================================================" -ForegroundColor Green
Write-Host "WALK-FORWARD COMPLETADO" -ForegroundColor Green
Write-Host "====================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Ver detalles en: reports\H3_WALKFORWARD_VALIDATION.json" -ForegroundColor Yellow
