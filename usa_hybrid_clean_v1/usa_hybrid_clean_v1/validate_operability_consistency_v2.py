#!/usr/bin/env python
"""
VALIDADOR DE OPERABILIDAD v2.0
===============================
Verifica que los datos cumplen con definición centralizada de "operable".

IMPORTANTE: Importa operable_mask() de operability.py - NO reimplementa.

EXIT CODES:
    0: Validación exitosa (delta dentro de tolerancia)
    1: Delta excede tolerancia (requires investigation)

Uso:
    python validate_operability_consistency_v2.py

Salida:
    - Breakdown paso a paso
    - Validación contra EXPECTED_OPERABLE_COUNT
    - Alerta si delta > tolerancia
    - Exit code != 0 si falla
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import sys

from operability import operable_mask, get_operability_breakdown, EXPECTED_OPERABLE_COUNT, WHITELIST_TICKERS, prepare_operability_columns
from operability_config import delta_tolerance, data_source


def load_data() -> pd.DataFrame:
    """Cargar datos desde CSV Authority."""
    csv_path = data_source.CSV_AUTHORITY
    
    if not csv_path.exists():
        raise FileNotFoundError(f"[FAIL] CSV Authority no encontrado: {csv_path}")
    
    print(f"[DATA] CSV Authority: {csv_path}")
    print(f"[DATA] File size: {csv_path.stat().st_size:,} bytes")
    
    df = pd.read_csv(csv_path)
    df = prepare_operability_columns(df, warn_on_fallback=False)
    return df


def validate():
    """Ejecutar validación centralizada."""
    
    print("\n" + "="*70)
    print("VALIDADOR DE CONSISTENCIA - operable_mask() CENTRALIZADO")
    print("="*70)
    
    # Cargar datos
    df = load_data()
    
    print(f"\n[INFO] Dataset: {len(df):,} observaciones")
    print(f"       Rango: {df['date'].min().date()} → {df['date'].max().date()}")
    
    # Usar función centralizada (NO reimplementar)
    print(f"\n[INFO] Ejecutando get_operability_breakdown()...")
    breakdown = get_operability_breakdown(df)
    
    # Mostrar breakdown
    print(f"\n┌─ BREAKDOWN (paso a paso)")
    print(f"│  Global:                {breakdown['global']:,}")
    print(f"│  Conf >= 4:             {breakdown['conf_only']:,} ({breakdown['percentages']['conf_only']:.2f}%)")
    print(f"│  + Risk <= MEDIUM:      {breakdown['conf_risk']:,} ({breakdown['percentages']['conf_risk']:.2f}%)")
    print(f"│  + Whitelist tickers:   {breakdown['operable']:,} ({breakdown['percentages']['operable']:.2f}%)")
    print(f"└─")
    
    # Validación contra referencia
    actual = breakdown['operable']
    expected = EXPECTED_OPERABLE_COUNT
    delta = actual - expected
    delta_pct = abs(delta) / expected * 100 if expected > 0 else 0
    
    print(f"\n┌─ VALIDACION VS REFERENCIA")
    print(f"│  Expected: {expected:,}")
    print(f"│  Actual:   {actual:,}")
    print(f"│  Delta:    {delta:+,} ({delta_pct:+.2f}%)")
    
    # Determinar status usando tolerancia de config
    tolerance_pct = delta_tolerance.DELTA_TOLERANCE_PCT
    tolerance_abs = delta_tolerance.DELTA_TOLERANCE_ABSOLUTE
    
    if delta == 0:
        status = "[OK] CONSISTENCIA PERFECTA"
        exit_code = 0
    elif abs(delta) <= tolerance_abs:
        status = f"[OK] Margen normal (±{tolerance_abs} fila)"
        exit_code = 0
    elif delta_pct <= tolerance_pct:
        status = f"[WARN] Delta aceptable (<{tolerance_pct}%)"
        exit_code = 0
    else:
        status = f"[FAIL] Mismatch significativo - ejecutar diff_operables.py"
        exit_code = 1
    
    print(f"│  Status:   {status}")
    print(f"└─")
    
    # Validar que operable_mask funciona
    mask = operable_mask(df)
    operables = df[mask]
    
    print(f"\n┌─ VERIFICACION operable_mask()")
    print(f"│  Rows that pass mask: {len(operables):,}")
    if len(operables) == actual:
        print(f"│  Status: [OK] Consistente con breakdown")
    else:
        print(f"│  Status: [WARN] Diferencia: {len(operables) - actual} filas")
    print(f"└─")
    
    # Resumen final
    print(f"\n{'='*70}")
    if exit_code == 0:
        if delta == 0:
            print(f"[OK] VALIDACION EXITOSA - Sistema consistente")
        else:
            print(f"[OK] VALIDACION EXITOSA - Delta dentro de tolerancia")
    else:
        print(f"[FAIL] VALIDACION FALLIDA - Delta excede tolerancia")
        print(f"       Acción: Ejecutar python diff_operables.py --test=<CSV>")
    print(f"{'='*70}\n")
    
    return {
        "breakdown": breakdown,
        "delta": delta,
        "delta_pct": delta_pct,
        "status": status,
        "exit_code": exit_code,
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    results = validate()
    sys.exit(results["exit_code"])

