#!/usr/bin/env python3
"""
Pre-E2E Checklist — 4 validaciones críticas antes del E2E mañana
Duración: ~2 minutos
"""
import pandas as pd
import os
from datetime import datetime
from pathlib import Path

print("=" * 70)
print("PRE-E2E CHECKLIST — USA_HYBRID_CLEAN_V1")
print("=" * 70)
print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# === CHECK 1: asof_date en trade_plan ===
print("[CHECK 1] trade_plan asof_date = 2026-01-14")
try:
    tp = pd.read_csv("val/trade_plan_from_wrapper.csv")
    
    # Verificar columna date
    if 'date' in tp.columns:
        dates = pd.to_datetime(tp['date']).dt.date.unique()
        print(f"  ✓ Fechas en trade_plan: {dates}")
        if len(dates) == 1 and str(dates[0]) == '2026-01-14':
            print(f"  ✅ PASS: Todas las señales son de 2026-01-14")
        else:
            print(f"  ⚠️  WARN: Múltiples fechas o fecha incorrecta")
    else:
        print(f"  ⚠️  WARN: Columna 'date' no encontrada")
        
    # Verificar generated_at
    if 'generated_at' in tp.columns:
        gen_at = pd.to_datetime(tp['generated_at'].iloc[0])
        print(f"  ✓ generated_at: {gen_at}")
except Exception as e:
    print(f"  ❌ ERROR: {e}")

print()

# === CHECK 2: signals_with_gates solo T-1 ===
print("[CHECK 2] signals_with_gates solo T-1 (2026-01-14)")
try:
    sig = pd.read_parquet("data/daily/signals_with_gates.parquet")
    sig['date'] = pd.to_datetime(sig['date']).dt.date
    dates = sig['date'].unique()
    
    print(f"  ✓ Fechas únicas en signals: {dates}")
    if len(dates) == 1 and str(dates[0]) == '2026-01-14':
        print(f"  ✅ PASS: Solo T-1 (2026-01-14), {len(sig)} rows")
    else:
        print(f"  ⚠️  WARN: Múltiples fechas detectadas")
        for d in dates:
            count = (sig['date'] == d).sum()
            print(f"     {d}: {count} rows")
except Exception as e:
    print(f"  ❌ ERROR: {e}")

print()

# === CHECK 3: BUY vs SELL count + política ===
print("[CHECK 3] Conteo BUY vs SELL + política")
try:
    tp = pd.read_csv("val/trade_plan_from_wrapper.csv")
    
    if 'side' in tp.columns:
        counts = tp['side'].value_counts()
        print(f"  ✓ BUY:  {counts.get('BUY', 0)} trades")
        print(f"  ✓ SELL: {counts.get('SELL', 0)} trades")
        
        if counts.get('SELL', 0) > 0:
            print(f"  ⚠️  WARN: Hay SELL — verificar si es SHORT permitido o DESCARTE")
        else:
            print(f"  ✅ PASS: Long-only (sin SELL)")
    else:
        print(f"  ❌ ERROR: Columna 'side' no encontrada")
        
except Exception as e:
    print(f"  ❌ ERROR: {e}")

print()

# === CHECK 4: Versiones runtime + checksum modelos ===
print("[CHECK 4] Versiones runtime + modelos")
try:
    import sklearn, joblib, numpy, pandas, xgboost, catboost
    print(f"  ✓ scikit-learn: {sklearn.__version__}")
    print(f"  ✓ joblib:       {joblib.__version__}")
    print(f"  ✓ numpy:        {numpy.__version__}")
    print(f"  ✓ pandas:       {pandas.__version__}")
    print(f"  ✓ xgboost:      {xgboost.__version__}")
    print(f"  ✓ catboost:     {catboost.__version__}")
    
    # Checksum de modelos (mtime)
    model_dir = Path("models/direction/")
    models = ["rf.joblib", "xgb.joblib", "cat.joblib", "meta.joblib"]
    
    print(f"\n  Modelos (mtime):")
    for model_file in models:
        path = model_dir / model_file
        if path.exists():
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            size_mb = os.path.getsize(path) / (1024 * 1024)
            print(f"    {model_file:12s} {mtime.strftime('%Y-%m-%d %H:%M')} ({size_mb:.2f}MB)")
        else:
            print(f"    {model_file:12s} ❌ NOT FOUND")
    
    # Warning de versión
    if sklearn.__version__ != "1.7.2":
        print(f"\n  ⚠️  Modelos entrenados con sklearn 1.7.2")
        print(f"  ⚠️  Runtime actual: sklearn {sklearn.__version__}")
        print(f"  → Funciona hoy, pero es deuda técnica")
        print(f"  → SOLUCIÓN: pip install scikit-learn==1.7.2")
    else:
        print(f"\n  ✅ MATCH: sklearn {sklearn.__version__} == modelos 1.7.2")
    
except Exception as e:
    print(f"  ❌ ERROR: {e}")

print()

# === CHECK 5: pip check (inmutabilidad del lock) ===
print("[CHECK 5] pip check — Detectar conflictos de dependencias")
try:
    import subprocess
    result = subprocess.run(["pip", "check"], capture_output=True, text=True, timeout=10)
    
    if result.returncode == 0:
        print(f"  ✅ PASS: No conflicts found")
    else:
        print(f"  ⚠️  WARN: Conflicts detected:")
        print(f"  {result.stdout}")
        
except Exception as e:
    print(f"  ⚠️  SKIP: {e}")

print()
print("=" * 70)
print("CHECKLIST COMPLETADO")
print("=" * 70)
print()
print("PRÓXIMO: E2E_TEST_PROCEDURE.md mañana 14:30 CDMX")
print()
