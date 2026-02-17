"""
NORMALIZE_TICKERS.PY - Higiene de Datos
========================================

Normaliza tickers en el dataset:
  - Uppercase
  - Strip espacios
  - Detecta y loggea typos/anomalías

Crea backup del CSV original y reemplaza con versión limpia.

Uso:
    python normalize_tickers.py
"""

import pandas as pd
from pathlib import Path
from collections import Counter

from operability import WHITELIST_TICKERS


def normalize_tickers_in_csv(csv_path: Path) -> tuple:
    """
    Normalizar tickers en CSV.
    
    Returns:
        (df_original, df_normalized, report)
    """
    
    print(f"\n📖 Cargando: {csv_path}")
    df = pd.read_csv(csv_path)
    
    if "ticker" not in df.columns:
        print("❌ No existe columna 'ticker'")
        return None, None, None
    
    original_tickers = df["ticker"].copy()
    
    # Normalizar
    df["ticker"] = df["ticker"].str.strip().str.upper()
    
    # Detectar cambios
    changed = (original_tickers != df["ticker"]).sum()
    
    # Estadísticas
    unique_orig = original_tickers.nunique()
    unique_norm = df["ticker"].nunique()
    
    # Tickers únicos
    ticker_counts = df["ticker"].value_counts()
    outside_whitelist = ticker_counts[~ticker_counts.index.isin(WHITELIST_TICKERS)]
    
    report = {
        "changed": changed,
        "unique_original": unique_orig,
        "unique_normalized": unique_norm,
        "outside_whitelist_count": len(outside_whitelist),
        "outside_whitelist": outside_whitelist.to_dict() if len(outside_whitelist) > 0 else {},
    }
    
    return original_tickers, df, report


def main():
    csv_path = Path("outputs/analysis/all_signals_with_confidence.csv")
    
    if not csv_path.exists():
        print(f"❌ No existe: {csv_path}")
        return
    
    print("\n" + "="*70)
    print("NORMALIZACIÓN DE TICKERS")
    print("="*70)
    
    # Procesar
    orig, normalized, report = normalize_tickers_in_csv(csv_path)
    
    if report is None:
        return
    
    # Mostrar reporte
    print(f"\n📊 REPORTE:")
    print(f"  Cambios: {report['changed']} filas")
    print(f"  Tickers únicos original: {report['unique_original']}")
    print(f"  Tickers únicos después: {report['unique_normalized']}")
    print(f"  Fuera de whitelist: {report['outside_whitelist_count']}")
    
    if report['outside_whitelist']:
        print(f"\n⚠️  Tickers FUERA de whitelist (serán filtrados):")
        for ticker, count in list(report['outside_whitelist'].items())[:10]:
            print(f"    {ticker}: {count} observaciones")
        
        if len(report['outside_whitelist']) > 10:
            print(f"    ... y {len(report['outside_whitelist'])-10} más")
    
    # Crear backup
    backup_path = csv_path.with_stem(csv_path.stem + "_backup")
    if not backup_path.exists():
        import shutil
        shutil.copy(csv_path, backup_path)
        print(f"\n✓ Backup creado: {backup_path.name}")
    else:
        print(f"\n✓ Backup ya existe: {backup_path.name}")
    
    # Guardar normalizado
    normalized.to_csv(csv_path, index=False)
    print(f"✓ CSV actualizado: {csv_path.name}")
    
    print("\n" + "="*70)
    print("✅ NORMALIZACIÓN COMPLETADA")
    print("="*70)


if __name__ == "__main__":
    main()
