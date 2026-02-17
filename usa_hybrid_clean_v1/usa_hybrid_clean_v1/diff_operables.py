#!/usr/bin/env python
"""
DIFF OPERABLES - Diagnóstico de Deltas
=======================================
Compara dos conjuntos de operables (referencia vs test) para diagnosticar
discrepancias en la aplicación del filtro operable_mask().

Uso:
    python diff_operables.py --ref outputs/analysis/signals_to_trade_2025-11-19.csv \
                            --test outputs/analysis/signals_to_trade_2025-11-19.csv

    python diff_operables.py --test outputs/analysis/signals_to_trade_2025-11-19.csv
    (genera referencia con operable_mask)
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import argparse
from typing import Dict, List, Tuple
import json
import hashlib

from operability import (
    operable_mask, 
    get_operability_breakdown, 
    EXPECTED_OPERABLE_COUNT, 
    WHITELIST_TICKERS,
    prepare_operability_columns
)


def get_dataset_metadata(df: pd.DataFrame, csv_path: Path) -> Dict:
    """
    Extraer metadata del dataset para evitar confusiones.
    
    Returns:
        Dict con file_path, date_range, n_rows, n_unique_dates, file_size
    """
    metadata = {
        "file_path": str(csv_path.absolute()),
        "file_exists": csv_path.exists(),
        "file_size_bytes": csv_path.stat().st_size if csv_path.exists() else 0,
        "n_rows": len(df),
        "n_unique_dates": df["date"].nunique() if "date" in df.columns else 0,
    }
    
    if "date" in df.columns and len(df) > 0:
        metadata["date_min"] = str(df["date"].min())
        metadata["date_max"] = str(df["date"].max())
        metadata["date_range_days"] = (df["date"].max() - df["date"].min()).days
    
    # Hash del archivo (opcional pero útil)
    if csv_path.exists():
        with open(csv_path, "rb") as f:
            metadata["file_hash_md5"] = hashlib.md5(f.read()).hexdigest()[:8]
    
    return metadata


def load_operables_from_script(csv_path: Path) -> pd.DataFrame:
    """Cargar CSV y extraer operables usando operable_mask."""
    try:
        df = pd.read_csv(csv_path)
        df = prepare_operability_columns(df, warn_on_fallback=False)
        
        # Aplicar máscara
        mask = operable_mask(df)
        operables = df[mask].copy()
        
        return operables
    except Exception as e:
        print(f"[FAIL] Error cargando {csv_path}: {e}")
        return pd.DataFrame()


def generate_reference_operables() -> pd.DataFrame:
    """Generar referencia desde datos principales."""
    csv_path = Path("outputs/analysis/all_signals_with_confidence.csv")
    if not csv_path.exists():
        print(f"[FAIL] No se encuentra {csv_path}")
        return pd.DataFrame()
    
    return load_operables_from_script(csv_path)


def diagnose_delta_cause(ref_metadata: Dict, test_metadata: Dict, missing_count: int, extra_count: int) -> str:
    """
    Diagnosticar causa automática del delta.
    
    Reglas:
    - Si test no cubre date range completo de ref → date_range_mismatch
    - Si date ranges coinciden pero hay missing rows → logic_mismatch
    - Si delta es 0 → consistent
    
    Returns:
        "date_range_mismatch" | "logic_mismatch" | "consistent" | "temporal_mismatch"
    """
    
    # Parsear fechas
    ref_min = pd.to_datetime(ref_metadata.get("date_min", "1900-01-01"))
    ref_max = pd.to_datetime(ref_metadata.get("date_max", "1900-01-01"))
    test_min = pd.to_datetime(test_metadata.get("date_min", "1900-01-01"))
    test_max = pd.to_datetime(test_metadata.get("date_max", "1900-01-01"))
    
    # Caso 1: Sin delta
    if missing_count == 0 and extra_count == 0:
        return "consistent"
    
    # Caso 2: Test no cubre rango completo de referencia
    if test_min > ref_min or test_max < ref_max:
        days_missing_start = (test_min - ref_min).days
        days_missing_end = (ref_max - test_max).days
        return f"date_range_mismatch (test missing {days_missing_start}d at start, {days_missing_end}d at end)"
    
    # Caso 3: Rangos coinciden pero hay filas faltantes
    if test_min <= ref_min and test_max >= ref_max:
        if missing_count > 0 or extra_count > 0:
            return "logic_mismatch (same date range, different row counts)"
    
    # Caso 4: Fechas no coinciden exactamente (temporal mismatch)
    if test_min != ref_min or test_max != ref_max:
        return "temporal_mismatch (different date boundaries)"
    
    return "unknown"


def diff_operables(df_ref: pd.DataFrame, df_test: pd.DataFrame, test_name: str = "test") -> Dict:
    """
    Comparar dos DataFrames de operables.
    
    Returns:
        Dict con keys: ref_count, test_count, delta, missing, extra, missing_count, extra_count, diagnostics
    """
    
    # Claves para matching (date + ticker)
    ref_keys = set(zip(df_ref["date"], df_ref["ticker"]))
    test_keys = set(zip(df_test["date"], df_test["ticker"]))
    
    missing_keys = ref_keys - test_keys
    extra_keys = test_keys - ref_keys
    
    # Extraer DataFrames
    missing = df_ref[
        df_ref.apply(lambda row: (row["date"], row["ticker"]) in missing_keys, axis=1)
    ].copy()
    extra = df_test[
        df_test.apply(lambda row: (row["date"], row["ticker"]) in extra_keys, axis=1)
    ].copy()
    
    # Agregar columna severity (HIGH si whitelist + operable, LOW si no)
    def calculate_severity(row):
        is_whitelist = row.get("ticker") in WHITELIST_TICKERS
        is_high_conf = row.get("confidence", 0) >= 4
        is_low_risk = row.get("macro_risk") in ["LOW", "MEDIUM"]
        
        if is_whitelist and is_high_conf and is_low_risk:
            return "HIGH"
        else:
            return "LOW"
    
    if len(missing) > 0:
        missing["severity"] = missing.apply(calculate_severity, axis=1)
    if len(extra) > 0:
        extra["severity"] = extra.apply(calculate_severity, axis=1)
    
    # Diagnósticos (causa probable)
    diagnostics = {
        "missing": [],
        "extra": []
    }
    
    for _, row in missing.iterrows():
        if pd.isna(row.get("confidence", 999)):
            cause = "NaN confidence"
        elif row.get("confidence", 999) < 4:
            cause = "confidence < 4"
        elif row.get("macro_risk") and row["macro_risk"] not in ["LOW", "MEDIUM"]:
            cause = "macro_risk > MEDIUM"
        elif row.get("ticker") not in WHITELIST_TICKERS:
            cause = "ticker not in WHITELIST"
        else:
            cause = "unknown (temporal mismatch?)"
        
        diagnostics["missing"].append({
            "date": str(row["date"]),
            "ticker": row.get("ticker", "?"),
            "confidence": row.get("confidence", "?"),
            "severity": row.get("severity", "LOW"),
            "cause": cause
        })
    
    return {
        "ref_count": len(df_ref),
        "test_count": len(df_test),
        "delta": len(df_test) - len(df_ref),
        "missing": missing,
        "extra": extra,
        "missing_count": len(missing),
        "extra_count": len(extra),
        "diagnostics": diagnostics
    }


def main():
    parser = argparse.ArgumentParser(description="Comparar operables (ref vs test)")
    parser.add_argument("--ref", type=str, default="generate", 
                       help="CSV referencia (default: generate from all_signals_with_confidence.csv)")
    parser.add_argument("--test", type=str, required=True,
                       help="CSV test a validar")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("DIFF OPERABLES - Diagnostico de Deltas")
    print("="*70)
    
    # Cargar referencia
    if args.ref == "generate":
        print("\n[INFO] Generando referencia (operable_mask)...")
        ref_path = Path("outputs/analysis/all_signals_with_confidence.csv")
        df_ref = generate_reference_operables()
    else:
        print(f"\n[INFO] Cargando referencia: {args.ref}")
        ref_path = Path(args.ref)
        df_ref = load_operables_from_script(ref_path)
    
    if df_ref.empty:
        print("[FAIL] No se pudo cargar referencia")
        return
    
    # Metadata de referencia
    ref_metadata = get_dataset_metadata(df_ref, ref_path)
    print(f"\n[META] Referencia Dataset:")
    print(f"   Path: {ref_metadata['file_path']}")
    print(f"   Rows: {ref_metadata['n_rows']:,}")
    print(f"   Dates: {ref_metadata.get('date_min', 'N/A')} -> {ref_metadata.get('date_max', 'N/A')}")
    print(f"   Unique dates: {ref_metadata['n_unique_dates']}")
    print(f"   File size: {ref_metadata['file_size_bytes']:,} bytes")
    print(f"   Hash: {ref_metadata.get('file_hash_md5', 'N/A')}")
    
    # Cargar test
    print(f"\n[INFO] Cargando test: {args.test}")
    test_path = Path(args.test)
    df_test = load_operables_from_script(test_path)
    
    if df_test.empty:
        print("[FAIL] No se pudo cargar test")
        return
    
    # Metadata de test
    test_metadata = get_dataset_metadata(df_test, test_path)
    print(f"\n[META] Test Dataset:")
    print(f"   Path: {test_metadata['file_path']}")
    print(f"   Rows: {test_metadata['n_rows']:,}")
    print(f"   Dates: {test_metadata.get('date_min', 'N/A')} -> {test_metadata.get('date_max', 'N/A')}")
    print(f"   Unique dates: {test_metadata['n_unique_dates']}")
    print(f"   File size: {test_metadata['file_size_bytes']:,} bytes")
    print(f"   Hash: {test_metadata.get('file_hash_md5', 'N/A')}")
    
    # Comparar
    print(f"\n[OK] Referencia: {len(df_ref)} operables")
    print(f"[OK] Test: {len(df_test)} operables")
    
    result = diff_operables(df_ref, df_test, Path(args.test).stem)
    
    # DIAGNOSTICO AUTOMÁTICO DE CAUSA
    cause_guess = diagnose_delta_cause(
        ref_metadata, 
        test_metadata, 
        result["missing_count"], 
        result["extra_count"]
    )
    
    print(f"\n[INFO] RESULTADOS:")
    print(f"   Referencia: {result['ref_count']}")
    print(f"   Test: {result['test_count']}")
    print(f"   Delta: {result['delta']:+d}")
    print(f"   Missing: {result['missing_count']}")
    print(f"   Extra: {result['extra_count']}")
    print(f"   Cause Guess: {cause_guess}")
    
    # RCA AUTOMÁTICO si logic_mismatch
    if "logic_mismatch" in cause_guess:
        print(f"\n[RCA] Detectado logic_mismatch - analizando duplicados...")
        
        # Detectar duplicados en ref
        ref_dups = df_ref.groupby(["date", "ticker"]).size()
        ref_dups = ref_dups[ref_dups > 1].sort_values(ascending=False)
        
        # Detectar duplicados en test
        test_dups = df_test.groupby(["date", "ticker"]).size()
        test_dups = test_dups[test_dups > 1].sort_values(ascending=False)
        
        print(f"   Ref duplicados: {len(ref_dups)} claves con duplicados")
        print(f"   Test duplicados: {len(test_dups)} claves con duplicados")
        
        if len(ref_dups) > 0:
            print(f"\n[RCA] Top 5 duplicados en REF:")
            for (date, ticker), count in ref_dups.head(5).items():
                print(f"   {date} {ticker}: {count} ocurrencias")
        
        if len(test_dups) > 0:
            print(f"\n[RCA] Top 5 duplicados en TEST:")
            for (date, ticker), count in test_dups.head(5).items():
                print(f"   {date} {ticker}: {count} ocurrencias")
    
    # Mostrar filas faltantes
    if len(result["missing"]) > 0:
        print(f"\n[FAIL] MISSING (en referencia, no en test):")
        cols_show = ["date", "ticker", "confidence", "macro_risk", "severity"]
        cols_show = [c for c in cols_show if c in result["missing"].columns]
        print(result["missing"][cols_show].to_string(index=False))
        
        # Fingerprint de las filas missing
        print(f"\n[RCA] Analizando qué FILTRO mata cada fila MISSING:")
        # Mostrar rangos para firmar diagnóstico temporal
        print(f"   REF range: {ref_metadata.get('date_min','N/A')} → {ref_metadata.get('date_max','N/A')}")
        print(f"   TEST range: {test_metadata.get('date_min','N/A')} → {test_metadata.get('date_max','N/A')}")
        for idx, row in result["missing"].head(10).iterrows():
            failed = []
            
            # Filtro 1: Confidence
            if pd.isna(row.get("confidence")):
                failed.append("confidence=NaN")
            elif row.get("confidence", 0) < 4:
                failed.append(f"conf={row.get('confidence')}<4")
            
            # Filtro 2: Risk
            if pd.isna(row.get("macro_risk")):
                failed.append("risk=NaN")
            elif row.get("macro_risk") not in ["LOW", "MEDIUM"]:
                failed.append(f"risk={row.get('macro_risk')}∉[LOW,MEDIUM]")
            
            # Filtro 3: Whitelist
            if row.get("ticker") not in WHITELIST_TICKERS:
                failed.append(f"ticker∉WHITELIST")
            
            # Filtro 4: NaN en columnas clave
            nan_cols = [c for c in row.index if pd.isna(row[c])]
            if nan_cols:
                failed.append(f"NaN:{','.join(nan_cols[:3])}")
            
            # Firmar si la fecha está dentro del rango de TEST
            tmin = pd.to_datetime(test_metadata.get('date_min')) if test_metadata.get('date_min') else None
            tmax = pd.to_datetime(test_metadata.get('date_max')) if test_metadata.get('date_max') else None
            in_test_range = False
            if tmin is not None and tmax is not None and not pd.isna(row['date']):
                in_test_range = (row['date'] >= tmin) and (row['date'] <= tmax)
            range_note = f"in_test_range={in_test_range}"
            result_str = " | ".join(failed) if failed else "✅ ALL FILTERS OK"
            date_str = row['date'].date() if hasattr(row['date'], 'date') else row['date']
            print(f"   {date_str} {row['ticker']}: {result_str} | {range_note}")
        
        # Contar severity
        if "severity" in result["missing"].columns:
            high_severity = (result["missing"]["severity"] == "HIGH").sum()
            low_severity = (result["missing"]["severity"] == "LOW").sum()
            print(f"\n[SEVERITY] HIGH: {high_severity} | LOW: {low_severity}")
            if high_severity > 0:
                print(f"[CRITICAL] {high_severity} filas son whitelist tickers con criteria operable!")
        
        if result["diagnostics"]["missing"]:
            print(f"\n[DIAG] Diagnostico:")
            for diag in result["diagnostics"]["missing"][:5]:
                print(f"   {diag['date']} {diag['ticker']}: {diag['cause']} (severity={diag['severity']})")
        
        # Exportar con metadata completa
        audit_path = Path("outputs/analysis/AUDIT_MISSING_OPERABLES.csv")
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Agregar metadata columns
        missing_audit = result["missing"].copy()
        missing_audit["ref_dataset"] = ref_metadata["file_path"]
        missing_audit["ref_date_range"] = f"{ref_metadata.get('date_min', 'N/A')} to {ref_metadata.get('date_max', 'N/A')}"
        missing_audit["test_dataset"] = test_metadata["file_path"]
        missing_audit["test_date_range"] = f"{test_metadata.get('date_min', 'N/A')} to {test_metadata.get('date_max', 'N/A')}"
        
        missing_audit.to_csv(audit_path, index=False)
        print(f"\n[AUDIT] Filas missing exportadas a: {audit_path}")
    
    # Mostrar filas extra
    if len(result["extra"]) > 0:
        print(f"\n[WARN] EXTRA (en test, no en referencia):")
        cols_show = ["date", "ticker", "confidence", "macro_risk", "severity"]
        cols_show = [c for c in cols_show if c in result["extra"].columns]
        extra_df = result["extra"][cols_show]
        print(extra_df.to_string(index=False))
        
        # Exportar extra también
        audit_extra_path = Path("outputs/analysis/AUDIT_EXTRA_OPERABLES.csv")
        result["extra"].to_csv(audit_extra_path, index=False)
        print(f"\n[AUDIT] Filas extra exportadas a: {audit_extra_path}")
        
        # Análisis por ticker y risk
        print(f"\n[ANALYSIS] Breakdown de las {len(result['extra'])} filas extra:")
        by_ticker = result["extra"]["ticker"].value_counts()
        by_risk = result["extra"]["macro_risk"].value_counts()
        print(f"   Por ticker: {dict(by_ticker)}")
        print(f"   Por risk: {dict(by_risk)}")
    
    # Veredicto
    print(f"\n{'='*70}")
    if result["delta"] == 0 and result["missing_count"] == 0:
        print(f"[OK] CONSISTENCIA TOTAL - No hay deltas")
    elif abs(result["delta"]) <= 1:
        print(f"[WARN] Delta minimo ({result['delta']:+d})")
    else:
        print(f"[FAIL] Delta significativo ({result['delta']:+d}): revisar filtros")
    
    # VALIDACIÓN: ¿HIGH realmente separa rendimiento? (con tamaño de muestra)
    if "macro_risk" in df_ref.columns:
        print(f"\n[VAL] Validando que HIGH realmente separa rendimiento:")
        
        # Tamaño de muestra por día (no por fila)
        n_days_high = df_ref[df_ref["macro_risk"] == "HIGH"]["date"].nunique()
        n_days_medium = df_ref[df_ref["macro_risk"] == "MEDIUM"]["date"].nunique()
        n_days_total = df_ref["date"].nunique()
        print(f"   Sample size (días) -> HIGH: {n_days_high}, MEDIUM: {n_days_medium}, TOTAL: {n_days_total}")
        
        if "direction_correct" in df_ref.columns:
            acc_medium = df_ref[df_ref["macro_risk"] == "MEDIUM"]["direction_correct"].mean()
            acc_high = df_ref[df_ref["macro_risk"] == "HIGH"]["direction_correct"].mean()
            
            separation = abs(acc_high - acc_medium)
            improvement = ((acc_medium - acc_high) / acc_high * 100) if acc_high and acc_high > 0 else 0
            
            print(f"   Accuracy MEDIUM: {acc_medium:.1%} ({n_days_medium} días)")
            print(f"   Accuracy HIGH: {acc_high:.1%} ({n_days_high} días)")
            print(f"   Separation: {separation:.1%} (improvement: {improvement:.1f}%)")
            
            if n_days_high < 10:
                print(f"   ⚠️  MUESTRA INSUFICIENTE: HIGH solo {n_days_high} días (<10) - separation puede ser ruido")
            elif separation < 0.05:
                print(f"   ⚠️  HIGH no separa (< 5% diff) - gate está tímido")
            else:
                print(f"   ✅ HIGH SEPARA - gate es efectivo")
        else:
            print(f"   ℹ️  No hay direction_correct - usando prevalencia por día")
            high_pct_days = 100 * n_days_high / n_days_total if n_days_total else 0
            print(f"   HIGH days: {n_days_high}/{n_days_total} ({high_pct_days:.2f}%)")
            if n_days_high < 10:
                print(f"   ⚠️  MUESTRA INSUFICIENTE: HIGH {n_days_high} días - no es confiable")
            elif high_pct_days < 1.0:
                print(f"   ⚠️  HIGH es muy raro (<1%) - gate está tímido")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
