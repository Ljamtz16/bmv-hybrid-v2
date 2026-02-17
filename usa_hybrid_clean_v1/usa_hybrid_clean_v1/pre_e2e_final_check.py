#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PRE_E2E_FINAL_CHECK.py
Checklist final antes del E2E mañana 14:30 CDMX
Ejecutar: python pre_e2e_final_check.py
"""
import subprocess
import sys
import pandas as pd
import json
import shutil
from pathlib import Path
from datetime import datetime

# Crear carpeta de evidencia con timestamp
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
evidence_dir = Path(f"evidence/pre_e2e_{timestamp}")
evidence_dir.mkdir(parents=True, exist_ok=True)

print("=" * 70)
print("CHECKLIST PRE-E2E FINAL - USA_HYBRID_CLEAN_V1")
print("=" * 70)
print(f"Timestamp: {timestamp}")
print(f"Evidencia: {evidence_dir}")
print()

# ========== PASO 1: Checklist 60s inicial ==========
print("[PASO 1/4] Checklist 60s inicial (validar estado base)...")
result = subprocess.run(
    ["python", "checklist_60s.py"],
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='replace',
    timeout=90
)

if "CHECKLIST 60s COMPLETADO" in result.stdout:
    print("  OK Checklist 60s inicial PASS\n")
else:
    print("  ERROR Checklist 60s falló")
    print(result.stdout)
    sys.exit(1)

# ========== PASO 2: Generar trade plan fresco ==========
print("[PASO 2/4] Generando trade plan fresco (T-1)...")

# Detectar T-1 dinámicamente
import pandas as pd
from datetime import datetime
try:
    ny_tz = pd.Timestamp.now(tz="America/New_York")
    t_minus_1 = pd.bdate_range(end=ny_tz.normalize(), periods=2, tz="America/New_York").date[-2]
    asof_date_str = str(t_minus_1)
    print(f"  Detectado T-1: {asof_date_str}")
except Exception as e:
    print(f"  WARN: No se pudo detectar T-1 automáticamente, usando 2026-01-14")
    asof_date_str = "2026-01-14"

result = subprocess.run([
    "python", "scripts/run_trade_plan.py",
    "--forecast", "data/daily/signals_with_gates.parquet",
    "--prices", "data/daily/ohlcv_daily.parquet",
    "--out", "val/trade_plan_pre_e2e.csv",
    "--month", "2026-01",
    "--capital", "100000",
    "--asof-date", asof_date_str
], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)

if result.returncode == 0 and "Trade plan generado" in result.stdout:
    print("  OK Trade plan generado")
    
    # Extraer stats clave del stdout
    for line in result.stdout.split('\n'):
        if 'ETTH (mean):' in line or 'BUY/SELL:' in line or 'Prob Win' in line:
            print(f"    {line.strip()}")
    print()
else:
    print("  ERROR Wrapper falló")
    print(result.stdout)
    print(result.stderr)
    sys.exit(1)

# ========== PASO 3: Validar output generado ==========
print("[PASO 3/4] Validando output generado...")

tp_path = Path("val/trade_plan_pre_e2e.csv")
audit_path = Path("val/trade_plan_run_audit.json")

if not tp_path.exists():
    print("  ERROR: trade_plan_pre_e2e.csv no existe")
    sys.exit(1)

if not audit_path.exists():
    print("  ERROR: trade_plan_run_audit.json no existe")
    sys.exit(1)

tp = pd.read_csv(tp_path)
with open(audit_path) as f:
    audit = json.load(f)

# Validaciones críticas
issues = []

# Check 1: Trades count
if len(tp) == 0:
    issues.append("Trade plan vacío (0 trades)")
elif len(tp) > 15:
    issues.append(f"Trades excede límite (max 15): {len(tp)}")

# Check 2: Long-only policy
if 'side' in tp.columns:
    sell_count = (tp['side'] == 'SELL').sum()
    if sell_count > 0:
        issues.append(f"SELL trades detectados (policy long-only): {sell_count}")

# Check 3: asof_date consistency
if audit.get('asof_date') != asof_date_str:
    issues.append(f"asof_date mismatch: audit={audit.get('asof_date')} vs expected={asof_date_str}")

# Check 4: ETTH confiabilidad (criterios estrictos)
etth_status = "OK"
etth_issues_detail = []

if 'etth_days' in tp.columns:
    etth_unique = tp['etth_days'].nunique(dropna=True)
    etth_nan_pct = tp['etth_days'].isna().mean() * 100
    etth_degraded = tp.get('etth_degraded', pd.Series([False]*len(tp))).sum()
    n_trades = len(tp)
    
    # Criterio 1: Sin NaN (o <= 5%)
    if etth_nan_pct > 5.0:
        etth_status = "DEGRADED"
        etth_issues_detail.append(f"NaN% alto ({etth_nan_pct:.1f}% > 5%)")
    
    # Criterio 2: Variabilidad suficiente
    min_unique = min(3, n_trades)
    if etth_unique < min_unique:
        etth_status = "DEGRADED"
        etth_issues_detail.append(f"Sin variabilidad (unique={etth_unique} < {min_unique})")
    
    # Criterio 3: Sin degraded flags (o <= 1 tolerado)
    if etth_degraded > 1:
        etth_status = "DEGRADED"
        etth_issues_detail.append(f"Degraded count alto ({etth_degraded} > 1)")
    
    # Criterio 4: Global warning del audit
    if audit.get('etth_global_warning'):
        etth_status = "DEGRADED"
        etth_issues_detail.append(f"Global warning: {audit['etth_global_warning']}")
    
    if etth_status == "DEGRADED":
        issues.append(f"ETTH {etth_status}: {', '.join(etth_issues_detail)}")
        issues.append("ACCION: Usar plan base sin ETTH para decisiones hoy")
else:
    etth_status = "MISSING"
    issues.append("ETTH no presente (post-proceso falló)")
    issues.append("ACCION: Revisar logs de run_trade_plan.py")

# Check 5: Exposure guardrail
if 'exposure_total' in audit:
    exposure = audit['exposure_total']
    capital = audit.get('capital', 100000)
    exposure_pct = (exposure / capital) * 100
    
    # Verificar negativos y NaNs en qty y entry
    has_qty_cols = 'qty' in tp.columns
    has_entry_cols = 'entry' in tp.columns
    qty_issues = []
    
    if has_qty_cols:
        if (tp['qty'] < 0).any():
            qty_issues.append("Qty negativas detectadas")
        if tp['qty'].isna().any():
            qty_issues.append("Qty con NaN detectadas")
    
    if has_entry_cols:
        if (tp['entry'] < 0).any():
            qty_issues.append("Entry prices negativas detectadas")
        if tp['entry'].isna().any():
            qty_issues.append("Entry prices con NaN detectadas")
    
    if qty_issues:
        issues.extend(qty_issues)
    
    if exposure_pct > 100.0:
        issues.append(f"EXPOSURE CRITICA: {exposure_pct:.2f}% > 100% (capital insuficiente)")
    elif exposure_pct > 98.0:
        print(f"[WARN] Exposure alta (guardrail): {exposure_pct:.2f}% > 98%")
        print(f"       Disponible: ${capital - exposure:.2f} ({100 - exposure_pct:.2f}%)")
        print(f"       Riesgo: cambios de redondeo pueden exceder 100%")
        print()

# Check 6: Versiones
sklearn_ver = audit.get('versions', {}).get('scikit-learn', 'N/A')
if sklearn_ver != '1.7.2':
    issues.append(f"sklearn version mismatch: {sklearn_ver} != 1.7.2")

if issues:
    print("  WARN Validaciones con issues:")
    for issue in issues:
        print(f"    - {issue}")
    print()
else:
    print("  OK Todas las validaciones PASS")
    print(f"    Trades: {len(tp)}")
    print(f"    BUY/SELL: {(tp['side']=='BUY').sum()} BUY, {(tp['side']=='SELL').sum()} SELL")
    if 'etth_days' in tp.columns:
        print(f"    ETTH: mean={tp['etth_days'].mean():.2f}d, unique={tp['etth_days'].nunique(dropna=True)}, status={etth_status}")
    print(f"    sklearn: {sklearn_ver}")
    print()

# ========== Guardar evidencia ==========
print("\n[EVIDENCIA] Guardando snapshot...")

try:
    # 1. Trade plan
    if tp_path.exists():
        shutil.copy(tp_path, evidence_dir / "trade_plan.csv")
    
    # 2. Audit log
    if audit_path.exists():
        shutil.copy(audit_path, evidence_dir / "trade_plan_audit.json")
    
    # 3. pip freeze
    pip_freeze = subprocess.run(
        ["python", "-m", "pip", "freeze"],
        capture_output=True,
        text=True
    )
    (evidence_dir / "pip_freeze.txt").write_text(pip_freeze.stdout, encoding='utf-8')
    
    # 4. Report JSON
    report = {
        "timestamp": timestamp,
        "status": "PASS" if not issues else "WARN",
        "issues": issues,
        "trade_plan": {
            "path": str(tp_path),
            "rows": len(tp),
            "buy_count": int((tp['side']=='BUY').sum()) if 'side' in tp.columns else 0,
            "sell_count": int((tp['side']=='SELL').sum()) if 'side' in tp.columns else 0,
            "asof_date": audit.get('asof_date'),
        },
        "etth": {
            "status": etth_status,
            "mean": float(tp['etth_days'].mean()) if 'etth_days' in tp.columns else None,
            "unique": int(tp['etth_days'].nunique(dropna=True)) if 'etth_days' in tp.columns else None,
            "nan_pct": float(tp['etth_days'].isna().mean() * 100) if 'etth_days' in tp.columns else None,
            "issues": etth_issues_detail if etth_status == "DEGRADED" else [],
        },
        "versions": audit.get('versions', {}),
    }
    
    with open(evidence_dir / "pre_e2e_report.json", 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"  OK Evidencia guardada en: {evidence_dir}")
    print(f"    - trade_plan.csv")
    print(f"    - trade_plan_audit.json")
    print(f"    - pip_freeze.txt")
    print(f"    - pre_e2e_report.json")
    print()
    
except Exception as e:
    print(f"  WARN Error guardando evidencia: {e}\n")

# ========== PASO 4: Checklist 60s final (confirmar consistencia) ==========
print("[PASO 4/4] Checklist 60s final (confirmar consistencia)...")
result = subprocess.run(
    ["python", "checklist_60s.py"],
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='replace',
    timeout=90
)

if "CHECKLIST 60s COMPLETADO" in result.stdout:
    print("  OK Checklist 60s final PASS\n")
else:
    print("  ERROR Checklist 60s final falló")
    print(result.stdout)
    sys.exit(1)

# ========== RESUMEN FINAL ==========
print("=" * 70)
print("RESUMEN PRE-E2E")
print("=" * 70)
print()
print("PASO 1: Checklist 60s inicial           OK")
print("PASO 2: Trade plan fresco (T-1)          OK")
print(f"PASO 3: Validaciones output              {'WARN' if issues else 'OK'}")
print("PASO 4: Checklist 60s final              OK")
print()

if issues:
    print("ISSUES DETECTADOS:")
    for issue in issues:
        print(f"  - {issue}")
    print()
    print("STATUS: REVISAR ANTES DE E2E")
    sys.exit(1)
else:
    print("STATUS: LISTO PARA E2E MANANA 14:30 CDMX")
    print()
    print("Próximo paso:")
    print("  python E2E_TEST_PROCEDURE.py  # Mañana 14:30")
    print()
