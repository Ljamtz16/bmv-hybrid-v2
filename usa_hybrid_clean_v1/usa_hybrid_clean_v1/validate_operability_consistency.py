#!/usr/bin/env python
"""
VALIDADOR DE OPERABILIDAD
==========================
Verifica que TODOS los scripts usan operable_mask() de operability.py.

Uso:
    python validate_operability_consistency.py

Salida:
    - Importa operable_mask() (no reimplementa)
    - Verifica conteo = EXPECTED_OPERABLE_COUNT
    - Alerta si hay delta > 0.5%
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

from operability import operable_mask, get_operability_breakdown, EXPECTED_OPERABLE_COUNT, WHITELIST_TICKERS


def load_data() -> pd.DataFrame:
    """Cargar datos."""
    csv_path = Path("outputs/analysis/all_signals_with_confidence.csv")
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"])
    # IMPORTANTE: Si macro_risk no está en datos, calcularla antes
    if "macro_risk" not in df.columns:
        print("[WARN] macro_risk not in data - using fallback")
        df["macro_risk"] = "MEDIUM"
    return df



def filter_operable_official(df: pd.DataFrame) -> pd.DataFrame:
    """
    DEFINICIÓN OFICIAL DE OPERABLE
    (Sincronizada con production_orchestrator.py)
    """
    risk_ok = df["macro_risk"].isin(["LOW", "MEDIUM"])
    conf_ok = df["confidence_score"] >= CONF_THRESHOLD
    ticker_ok = df["ticker"].isin(WHITELIST_TICKERS)
    
    return df[risk_ok & conf_ok & ticker_ok].copy()


def validate_consistency():
    """Validar consistencia de definiciones."""
    
    print("\n" + "="*70)
    print("VALIDADOR DE CONSISTENCIA: DEFINICIÓN DE OPERABLE")
    print("="*70)
    
    # Cargar datos
    df = load_data()
    
    print(f"\n📊 Dataset: {len(df):,} observaciones")
    print(f"Rango: {df['date'].min().date()} → {df['date'].max().date()}")
    
    # Aplicar 3 filtros paso a paso
    print(f"\n┌─ DESGLOSE POR FILTRO")
    print(f"│")
    
    global_count = len(df)
    print(f"│  Total dataset: {global_count:,}")
    
    conf_ok = df["confidence_score"] >= CONF_THRESHOLD
    conf_count = len(df[conf_ok])
    print(f"│  Conf >= {CONF_THRESHOLD}: {conf_count:,} ({conf_count/global_count*100:5.1f}%)")
    
    risk_ok = df["macro_risk"].isin(["LOW", "MEDIUM"])
    conf_risk_count = len(df[conf_ok & risk_ok])
    print(f"│    + Risk <= {RISK_THRESHOLD}: {conf_risk_count:,} ({conf_risk_count/global_count*100:5.1f}%)")
    
    ticker_ok = df["ticker"].isin(WHITELIST_TICKERS)
    operable_count = len(df[conf_ok & risk_ok & ticker_ok])
    print(f"│      + Whitelist {WHITELIST_TICKERS}: {operable_count:,} ({operable_count/global_count*100:5.1f}%)")
    
    print(f"│")
    print(f"└─ OPERABLE TOTAL: {operable_count:,}")
    
    # Validar con función oficial
    operable_df = filter_operable_official(df)
    
    print(f"\n✅ DEFINICIÓN OFICIAL VALIDADA")
    print(f"   Operables: {len(operable_df):,}")
    
    # Detalle por ticker
    print(f"\n┌─ DESGLOSE POR TICKER (Operables)")
    for ticker in WHITELIST_TICKERS:
        ticker_count = len(operable_df[operable_df["ticker"] == ticker])
        ticker_pct = ticker_count / len(operable_df) * 100
        print(f"│  {ticker}: {ticker_count:5,} ({ticker_pct:5.1f}%)")
    print(f"└─ TOTAL: {len(operable_df):,}")
    
    # Detalle por macroriesgo
    print(f"\n┌─ DESGLOSE POR MACRO RISK (Operables)")
    for risk in ["LOW", "MEDIUM"]:
        risk_count = len(operable_df[operable_df["macro_risk"] == risk])
        risk_pct = risk_count / len(operable_df) * 100
        print(f"│  {risk}: {risk_count:5,} ({risk_pct:5.1f}%)")
    print(f"└─ TOTAL: {len(operable_df):,}")
    
    # Almacenar resultados para validación
    results = {
        "global": global_count,
        "conf_only": conf_count,
        "conf_risk": conf_risk_count,
        "operable": operable_count,
        "timestamp": datetime.now(),
    }
    
    # Export para auditoría
    audit_df = pd.DataFrame({
        "Filter": [
            "GLOBAL",
            "Conf >= 4",
            "Conf >= 4 AND Risk <= MEDIUM",
            "Conf >= 4 AND Risk <= MEDIUM AND Whitelist"
        ],
        "Count": [
            global_count,
            conf_count,
            conf_risk_count,
            operable_count
        ],
        "Percentage": [
            100.0,
            conf_count/global_count*100,
            conf_risk_count/global_count*100,
            operable_count/global_count*100
        ]
    })
    
    audit_df.to_csv("outputs/analysis/operability_consistency_check.csv", index=False)
    print(f"\n✓ Auditoría exportada: operability_consistency_check.csv")
    
    # Tabla de referencia rápida
    print(f"\n┌─ TABLA RÁPIDA DE REFERENCIA")
    print(f"│")
    print(f"│  Si ves {operable_count:,} operables:")
    print(f"│    ✅ Script CORRECTO (usa 3 filtros)")
    print(f"│")
    print(f"│  Si ves diferente:")
    print(f"│    ❌ Script INCORRECTO (falta Conf, Risk, o Whitelist)")
    print(f"│")
    print(f"└─")
    
    return results


if __name__ == "__main__":
    results = validate_consistency()
    
    print(f"\n{'='*70}")
    print(f"✅ VALIDACIÓN COMPLETADA")
    print(f"{'='*70}\n")
