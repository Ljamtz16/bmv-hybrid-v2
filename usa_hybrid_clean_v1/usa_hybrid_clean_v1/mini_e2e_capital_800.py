#!/usr/bin/env python3
"""
Mini E2E Test - USA_HYBRID_CLEAN_V1
Ejecuta pipeline completo: datos → features → inferencia → trade plan → validación
Capital configurado: $800
"""
import subprocess
import sys
import pandas as pd
import json
from pathlib import Path
from datetime import datetime

CAPITAL = 800
ASOF_DATE = "2026-01-14"  # T-1
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

print("=" * 80)
print("🔄 MINI E2E TEST - OUTPUTS REALES CON CAPITAL $800")
print("=" * 80)
print()
print(f"[CONFIG] Capital: ${CAPITAL}")
print(f"[CONFIG] asof-date (T-1): {ASOF_DATE}")
print(f"[CONFIG] Timestamp: {TIMESTAMP}")
print()

# ========== PASO 1: Refresh datos ==========
print("=" * 80)
print("[1/5] REFRESH DATOS REALES (OHLCV + features)")
print("=" * 80)
result = subprocess.run(["python", "scripts/00_refresh_daily_data.py"])
if result.returncode != 0:
    print("ERROR en refresh datos")
    sys.exit(1)
print()

# Verificar freshness
print("[VERIFY] Freshness de datos...")
ohlcv = pd.read_parquet("data/daily/ohlcv_daily.parquet")
print(f"  ohlcv rows: {len(ohlcv)}")
print(f"  date max: {ohlcv['date'].max() if 'date' in ohlcv.columns else ohlcv['timestamp'].max()}")

features = pd.read_parquet("data/daily/features_daily_enhanced.parquet")
print(f"  features rows: {len(features)}")
print(f"  date max: {features['timestamp'].max()}")
print()

# ========== PASO 2: Inferencia T-1 ==========
print("=" * 80)
print("[2/5] INFERENCIA T-1 + GATES")
print("=" * 80)
result = subprocess.run(
    ["python", "scripts/11_infer_and_gate.py"],
    env={**subprocess.os.environ, "PYTHONIOENCODING": "utf-8"}
)
if result.returncode != 0:
    print("ERROR en inferencia")
    sys.exit(1)
print()

# Verificar signals
print("[VERIFY] Signals generados...")
signals = pd.read_parquet("data/daily/signals_with_gates.parquet")
print(f"  rows: {len(signals)}")
print(f"  unique dates: {sorted(signals['timestamp'].dt.date.unique()) if 'timestamp' in signals.columns else 'NO timestamp'}")
print(f"  tickers: {signals['ticker'].tolist()}")
print()

# ========== PASO 3: Trade Plan ==========
print("=" * 80)
print(f"[3/5] TRADE PLAN T-1 (capital=${CAPITAL})")
print("=" * 80)
result = subprocess.run([
    "python", "scripts/run_trade_plan.py",
    "--forecast", "data/daily/signals_with_gates.parquet",
    "--prices", "data/daily/ohlcv_daily.parquet",
    "--out", "val/trade_plan.csv",
    "--month", "2026-01",
    "--capital", str(CAPITAL),
    "--asof-date", ASOF_DATE
])
if result.returncode != 0:
    print("ERROR en trade plan")
    sys.exit(1)
print()

# ========== PASO 4: Inspección ==========
print("=" * 80)
print("[4/5] INSPECCIÓN OUTPUT TRADE PLAN")
print("=" * 80)
tp = pd.read_csv("val/trade_plan.csv")
print(f"shape: {tp.shape}")
print(f"cols: {tp.columns.tolist()}")
print()
print(tp[['ticker', 'side', 'entry', 'qty', 'exposure', 'prob_win', 'strength', 'etth_days']])
print()

# ========== PASO 5: Evidencia ==========
print("=" * 80)
print("[5/5] VALIDACIÓN + EVIDENCIA (snapshot timestamped)")
print("=" * 80)

evidence_dir = Path(f"evidence/mini_e2e_{TIMESTAMP}")
evidence_dir.mkdir(parents=True, exist_ok=True)

# Copiar artefactos
import shutil
shutil.copy("val/trade_plan.csv", evidence_dir / "trade_plan.csv")
shutil.copy("val/trade_plan_run_audit.json", evidence_dir / "trade_plan_audit.json")

# pip freeze
pip_freeze = subprocess.run(
    ["python", "-m", "pip", "freeze"],
    capture_output=True,
    text=True
)
(evidence_dir / "pip_freeze.txt").write_text(pip_freeze.stdout, encoding='utf-8')

# Report JSON
report = {
    "timestamp": TIMESTAMP,
    "status": "PASS",
    "capital": CAPITAL,
    "asof_date": ASOF_DATE,
    "test_type": "mini_e2e_real_outputs"
}
with open(evidence_dir / "mini_e2e_report.json", 'w') as f:
    json.dump(report, f, indent=2)

print(f"[OK] Evidencia guardada en: {evidence_dir}")
print("  - trade_plan.csv")
print("  - trade_plan_audit.json")
print("  - pip_freeze.txt")
print("  - mini_e2e_report.json")
print()

# ========== RESUMEN FINAL ==========
print("=" * 80)
print("✅ MINI E2E COMPLETADO")
print("=" * 80)
print()

# Leer audit
with open("val/trade_plan_run_audit.json") as f:
    audit = json.load(f)

trades = len(tp)
exposure = audit.get("exposure_total", 0)
exposure_pct = (exposure / CAPITAL) * 100

print("📊 STATS FINALES:")
print(f"  Capital:          ${CAPITAL}")
print(f"  Trades:           {trades}")
print(f"  Exposure total:   ${exposure:.2f}")
print(f"  Exposure %:       {exposure_pct:.2f}%")
print(f"  ETTH mean:        {audit.get('etth_mean', 0):.2f} días")
print(f"  Prob Win mean:    {audit.get('prob_win_mean', 0):.2%}")
print(f"  asof_date:        {audit.get('asof_date')}")
print()

print("🟡 WARNINGS:")
if exposure_pct > 98:
    print(f"  [WARN] Exposure > 98% (disponible: ${CAPITAL - exposure:.2f})")
if audit.get("forecast_issues", {}).get("side_imputed"):
    print(f"  [INFO] 'side' imputada: {audit['forecast_issues']['side_imputation_rule']}")
print()
print(f"📁 EVIDENCIA: {evidence_dir}")
print()
print("=" * 80)
