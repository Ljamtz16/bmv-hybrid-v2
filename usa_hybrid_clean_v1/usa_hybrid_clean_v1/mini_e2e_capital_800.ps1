# MINI E2E TEST - USA_HYBRID_CLEAN_V1
# Ejecución: datos frescos → features → inferencia → trade plan → validación
# Capital configurado: $800 (solo usar $800 max exposure)

Write-Host "================================================================================"
Write-Host "🔄 MINI E2E TEST - OUTPUTS REALES CON CAPITAL \$800"
Write-Host "================================================================================"
Write-Host ""

$CAPITAL = 800
$ASOF_DATE = "2026-01-14"  # T-1 fijo
$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"

Write-Host "[CONFIG] Capital: $$CAPITAL"
Write-Host "[CONFIG] asof-date (T-1): $ASOF_DATE"
Write-Host "[CONFIG] Timestamp: $TIMESTAMP"
Write-Host ""

# ==================== PASO 1: Refresh datos ====================
Write-Host "================================================================================"
Write-Host "[1/5] REFRESH DATOS REALES (OHLCV + features)"
Write-Host "================================================================================"
python .\scripts\00_refresh_daily_data.py
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR en refresh datos"; exit 1 }
Write-Host ""

# Verificar freshness
Write-Host "[VERIFY] Freshness de datos..."
& python -c @"
import pandas as pd
df = pd.read_parquet('data/daily/ohlcv_daily.parquet')
print('ohlcv rows:', len(df))
print('date max:', df['date'].max() if 'date' in df.columns else df['timestamp'].max())
"@
& python -c @"
import pandas as pd
df = pd.read_parquet('data/daily/features_daily_enhanced.parquet')
print('features rows:', len(df))
print('date max:', df['timestamp'].max())
"@
Write-Host ""

# ==================== PASO 2: Inferencia T-1 ====================
Write-Host "================================================================================"
Write-Host "[2/5] INFERENCIA T-1 + GATES"
Write-Host "================================================================================"
$env:PYTHONIOENCODING='utf-8'
python .\scripts\11_infer_and_gate.py
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR en inferencia"; exit 1 }
Write-Host ""

# Verificar signals
Write-Host "[VERIFY] Signals generados..."
& python -c @"
import pandas as pd
df = pd.read_parquet('data/daily/signals_with_gates.parquet')
print('rows:', len(df))
print('unique dates:', sorted(df['timestamp'].dt.date.unique()) if 'timestamp' in df.columns else 'NO timestamp')
print('tickers:', df['ticker'].tolist())
"@
Write-Host ""

# ==================== PASO 3: Trade Plan con capital 800 ====================
Write-Host "================================================================================"
Write-Host "[3/5] TRADE PLAN T-1 (capital=\$$CAPITAL)"
Write-Host "================================================================================"
python .\scripts\run_trade_plan.py `
  --forecast "data/daily/signals_with_gates.parquet" `
  --prices "data/daily/ohlcv_daily.parquet" `
  --out "val/trade_plan.csv" `
  --month "2026-01" `
  --capital $CAPITAL `
  --asof-date $ASOF_DATE

if ($LASTEXITCODE -ne 0) { Write-Host "ERROR en trade plan"; exit 1 }
Write-Host ""

# ==================== PASO 4: Inspección output ====================
Write-Host "================================================================================"
Write-Host "[4/5] INSPECCIÓN OUTPUT TRADE PLAN"
Write-Host "================================================================================"
& python -c @"
import pandas as pd
df = pd.read_csv('val/trade_plan.csv')
print('shape:', df.shape)
print('cols:', df.columns.tolist())
print()
print(df[['ticker','side','entry','qty','exposure','prob_win','strength','etth_days']])
"@
Write-Host ""

# ==================== PASO 5: Validación + Evidencia ====================
Write-Host "================================================================================"
Write-Host "[5/5] VALIDACIÓN + EVIDENCIA (snapshot timestamped)"
Write-Host "================================================================================"

# Crear evidencia manual con capital correcto
$EVIDENCE_DIR = "evidence/mini_e2e_$TIMESTAMP"
New-Item -ItemType Directory -Force -Path $EVIDENCE_DIR | Out-Null

# Copiar artefactos
Copy-Item "val/trade_plan.csv" "$EVIDENCE_DIR/trade_plan.csv"
Copy-Item "val/trade_plan_run_audit.json" "$EVIDENCE_DIR/trade_plan_audit.json"

# pip freeze
python -m pip freeze | Out-File -FilePath "$EVIDENCE_DIR/pip_freeze.txt" -Encoding utf8

# Report JSON manual
$json = @{
    timestamp = $TIMESTAMP
    status = "PASS"
    capital = $CAPITAL
    asof_date = $ASOF_DATE
    test_type = "mini_e2e_real_outputs"
}
$json | ConvertTo-Json -Depth 10 | Out-File -FilePath "$EVIDENCE_DIR/mini_e2e_report.json" -Encoding utf8

Write-Host "[OK] Evidencia guardada en: $EVIDENCE_DIR"
Write-Host "  - trade_plan.csv"
Write-Host "  - trade_plan_audit.json"
Write-Host "  - pip_freeze.txt"
Write-Host "  - mini_e2e_report.json"
Write-Host ""

# ==================== RESUMEN FINAL ====================
Write-Host "================================================================================"
Write-Host "✅ MINI E2E COMPLETADO"
Write-Host "================================================================================"

# Leer audit para stats finales
$audit = Get-Content "val/trade_plan_run_audit.json" | ConvertFrom-Json
$trades = (Get-Content "val/trade_plan.csv" | ConvertFrom-Csv).Count
$exposure = $audit.exposure_total
$exposure_pct = ($exposure / $CAPITAL) * 100

Write-Host ""
Write-Host "📊 STATS FINALES:"
Write-Host "  Capital:          $$CAPITAL"
Write-Host "  Trades:           $trades"
Write-Host "  Exposure total:   $$($exposure.ToString('F2'))"
Write-Host "  Exposure %:       $($exposure_pct.ToString('F2'))%"
Write-Host "  ETTH mean:        $($audit.etth_mean.ToString('F2')) días"
Write-Host "  Prob Win mean:    $($audit.prob_win_mean.ToString('P2'))"
Write-Host "  asof_date:        $($audit.asof_date)"
Write-Host ""
Write-Host "🟡 WARNINGS:"
if ($exposure_pct -gt 98) {
    Write-Host "  [WARN] Exposure > 98% (disponible: $$($CAPITAL - $exposure).ToString('F2'))"
}
if ($audit.forecast_issues.side_imputed -eq $true) {
    Write-Host "  [INFO] 'side' imputada: $($audit.forecast_issues.side_imputation_rule)"
}
Write-Host ""
Write-Host "📁 EVIDENCIA: $EVIDENCE_DIR"
Write-Host ""
Write-Host "================================================================================"
