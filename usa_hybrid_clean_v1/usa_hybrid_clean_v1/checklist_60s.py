#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Checklist ULTRA-CORTO (60 segundos) - Pre-E2E
Ejecutar ANTES del E2E manana 14:30 CDMX
"""
import subprocess
import sys
import os
from pathlib import Path

# Force UTF-8 encoding for subprocess output
os.environ['PYTHONIOENCODING'] = 'utf-8'

print("=" * 60)
print("CHECKLIST 60s — PRE-E2E")
print("=" * 60)
print()

# === 1. Verify Versions (20s) ===
print("[1/3] Verificando versiones (verify_versions.py)...")
try:
    result = subprocess.run(
        ["python", "verify_versions.py"],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=20
    )
    print(result.stdout)
    if "MATCH" in result.stdout:
        print("  ✅ Versiones alineadas\n")
    elif "MISMATCH" in result.stdout:
        print("  ⚠️  Mismatch detectado — revisar TECHNICAL_DEBT.md\n")
except Exception as e:
    print(f"  ❌ ERROR: {e}\n")
    sys.exit(1)

# === 2. Pre-E2E Checklist (30s) ===
print("[2/3] Ejecutando checklist completo (pre_e2e_checklist.py)...")
try:
    result = subprocess.run(
        ["python", "pre_e2e_checklist.py"],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=30
    )
    
    # Mostrar output completo (sin truncar)
    print(result.stdout)
    
    if "⚠️" in result.stdout or "WARN" in result.stdout:
        print("  ⚠️  Checklist tiene warnings (ver arriba)\n")
    elif result.returncode == 0:
        print("  ✅ Checklist completo PASS\n")
    else:
        print(f"  ❌ Checklist falló (returncode={result.returncode})\n")
        
except Exception as e:
    print(f"  ❌ ERROR: {e}\n")
    sys.exit(1)

# === 3. Wrapper Test (10s) ===
print("[3/3] Test wrapper (generación trade plan)...")

# Verificar que existen los archivos de entrada
forecast_path = Path("data/daily/signals_with_gates.parquet")
prices_path = Path("data/daily/ohlcv_daily.parquet")

if not forecast_path.exists():
    print(f"  ⚠️  SKIP: {forecast_path} no existe")
elif not prices_path.exists():
    print(f"  ⚠️  SKIP: {prices_path} no existe")
else:
    try:
        # Ejecutar wrapper en modo rápido
        result = subprocess.run([
            "python", "scripts/run_trade_plan.py",
            "--forecast", str(forecast_path),
            "--prices", str(prices_path),
            "--out", "val/trade_plan_60s_test.csv",
            "--month", "2026-01",
            "--capital", "100000",
            "--asof-date", "2026-01-14",
            "--audit-file", "val/trade_plan_60s_audit.json"
        ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)
        
        if result.returncode == 0:
            print("  OK Wrapper ejecuto correctamente")
            
            # Verificar output
            import pandas as pd
            import json
            
            tp = pd.read_csv("val/trade_plan_60s_test.csv")
            with open("val/trade_plan_60s_audit.json") as f:
                audit = json.load(f)
            
            sell_count = (tp['side'] == 'SELL').sum() if 'side' in tp.columns else 0
            
            print(f"    Trades: {len(tp)}")
            print(f"    BUY: {len(tp) - sell_count} | SELL: {sell_count}")
            print(f"    asof_date: {audit.get('asof_date', 'N/A')}")
            print(f"    sklearn: {audit.get('versions', {}).get('scikit-learn', 'N/A')}")
            
            # ETTH validation (post-proceso)
            if "etth_days" not in tp.columns:
                print("    WARN ETTH: etth_days no presente (post-proceso fallo o no habilitado)")
            else:
                nunq = tp["etth_days"].nunique(dropna=True)
                nan_pct = tp["etth_days"].isna().mean() * 100
                etth_mean = tp["etth_days"].mean()
                degraded = tp.get("etth_degraded", pd.Series([False]*len(tp))).sum()
                
                print(f"    ETTH: mean={etth_mean:.2f}d, unique={nunq}, NaN%={nan_pct:.1f}%, degraded={degraded}")
                
                # Warnings
                if nunq <= 1:
                    print("    WARN ETTH poco informativo (unique<=1). No usar para decisiones.")
                if nan_pct > 50:
                    print("    WARN ETTH degradado (>50% NaN).")
                if audit.get("etth_global_warning"):
                    print(f"    WARN {audit['etth_global_warning']}")
            
            if sell_count == 0 and audit.get('asof_date') == '2026-01-14':
                print("\n  OK Long-only + T-1 correcto")
            else:
                print(f"\n  WARN Revisar: SELL={sell_count}, asof={audit.get('asof_date')}")
                
        else:
            print(f"  ERROR Wrapper fallo (returncode={result.returncode})")
            print(f"\n[STDOUT]\n{result.stdout}")
            print(f"\n[STDERR]\n{result.stderr}")
            
    except Exception as e:
        import traceback
        print(f"  ❌ ERROR: {e}")
        print(f"\n[TRACEBACK]\n{traceback.format_exc()}")

print()
print("=" * 60)
print("CHECKLIST 60s COMPLETADO")
print("=" * 60)
print()
print("Si todos son ✅ → E2E mañana es PROCEDIMENTAL")
print()
