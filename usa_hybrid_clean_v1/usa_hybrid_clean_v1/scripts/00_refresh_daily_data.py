"""
Script: 00_refresh_daily_data.py
Actualiza precios diarios y regenera features para obtener predicciones forward-looking.

Flujo:
1. Descarga precios actualizados (último cierre disponible)
2. Convierte a formato parquet wide
3. Genera features técnicos
4. Añade context features
5. Genera targets adaptativos
6. Prepara datos para inference

Uso:
    python scripts/00_refresh_daily_data.py [--tickers-file data/us/tickers_master.csv]
"""
import subprocess
import sys
from pathlib import Path
import argparse
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo


def enable_utf8_output():
    """Force stdout/stderr to UTF-8 to avoid Windows cp1252 crashes with emojis."""
    try:
        # Python 3.7+
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        try:
            import io as _io
            sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

def run_step(cmd, description):
    """Ejecuta un paso del pipeline con manejo de errores."""
    print(f"\n{'='*80}")
    print(f"[{description}]")
    print(f"{'='*80}")
    result = subprocess.run(cmd, shell=True, capture_output=False)
    if result.returncode != 0:
        print(f"[ERROR] Falló: {description}")
        return False
    print(f"[OK] {description} completado")
    return True

def main():
    enable_utf8_output()
    ap = argparse.ArgumentParser(description="Actualiza datos diarios y genera features")
    ap.add_argument("--tickers-file", default="data/us/tickers_master.csv", 
                    help="CSV con columna 'ticker'")
    ap.add_argument("--start-date", default="2020-01-01",
                    help="Fecha de inicio para descarga histórica")
    ap.add_argument("--allow-stale", action="store_true",
                    help="Permite datos de 1-2 días atrás (útil fines de semana)")
    args = ap.parse_args()
    
    # Python executable
    py = sys.executable
    
    steps = [
        # 1. Descargar precios actualizados (CSV autoridad)
        (f'{py} scripts/download_us_prices.py --universe file --tickers-file {args.tickers_file} --start {args.start_date}',
         "Descargar precios diarios actualizados"),
        
        # 2. Reconstruir parquet desde CSV autoridad (long)
        (f'{py} scripts/00_download_daily_build_parquet.py',
         "Reconstruir parquet diario desde CSV autoridad"),
        
        # 3. Generar features diarios
        (f'{py} scripts/09_make_features_daily.py',
         "Generar features técnicos diarios"),
        
        # 4. Añadir context features
        (f'{py} scripts/09c_add_context_features.py',
         "Añadir features de contexto"),
        
        # 5. Generar targets adaptativos
        (f'{py} scripts/08_make_targets_adaptive.py',
         "Generar targets adaptativos por ATR/régimen"),
    ]
    
    print("\n" + "="*80)
    print("🔄 ACTUALIZACIÓN DE DATOS DIARIOS")
    print("="*80)
    print(f"Tickers: {args.tickers_file}")
    print(f"Desde: {args.start_date}")
    print("="*80 + "\n")
    
    for cmd, desc in steps:
        if not run_step(cmd, desc):
            print(f"\n❌ Pipeline detenido en: {desc}")
            return 1
    
    # Validaciones defensivas: asegurar frescura y que las features no incluyen datos de T (igualdad con T-1)
    try:
        ny = ZoneInfo("America/New_York")
        today_ny = datetime.now(ny).date()
        # Último día hábil (T-1) en NY
        # Usamos pandas para business day handling
        t_minus_1 = pd.bdate_range(end=pd.Timestamp(today_ny), periods=2, tz=ny).date[-2]
        
        # 1) CSV autoridad debe estar exactamente en T-1 (o permitir 1-2 días stale con --allow-stale)
        csv_path = Path("data/us/ohlcv_us_daily.csv")
        if csv_path.exists():
            df_csv = pd.read_csv(csv_path)
            max_csv_date = pd.to_datetime(df_csv["date"], utc=True, errors="coerce").dt.tz_convert("America/New_York").dt.date.max()
            days_behind = (t_minus_1 - max_csv_date).days
            
            if days_behind > 0:
                if args.allow_stale and days_behind <= 2:
                    print(f"[WARN] CSV stale: max(date_NY)={max_csv_date} vs T-1={t_minus_1} ({days_behind} days behind)")
                    print(f"[WARN] Continuando con --allow-stale (datos pueden estar desactualizados)")
                else:
                    print(f"[ERROR] CSV stale: max(date_NY)={max_csv_date} != T-1={t_minus_1}")
                    if not args.allow_stale:
                        print(f"[HINT] Usa --allow-stale para permitir datos de 1-2 días atrás (útil fines de semana)")
                    return 2
            else:
                print(f"[VALID] CSV freshness ok: max(date_NY)={max_csv_date} == T-1={t_minus_1}")
        else:
            print("[ERROR] Falta data/us/ohlcv_us_daily.csv")
            return 2
        
        # Validar features frescas usadas para inference
        feat_path = Path("data/daily/features_daily_enhanced.parquet")
        if feat_path.exists():
            df_feat = pd.read_parquet(feat_path)
            max_date_ny = pd.to_datetime(df_feat["timestamp"], utc=True, errors="coerce").dt.tz_convert("America/New_York").dt.date.max()
            feat_days_behind = (t_minus_1 - max_date_ny).days
            
            if feat_days_behind > 0:
                if args.allow_stale and feat_days_behind <= 2:
                    print(f"[WARN] Features stale: max(timestamp_NY)={max_date_ny} vs T-1={t_minus_1} ({feat_days_behind} days behind)")
                    print(f"[WARN] Continuando con --allow-stale")
                else:
                    print(f"[ERROR] Features stale/leak: max(timestamp_NY)={max_date_ny} != T-1={t_minus_1}")
                    return 3
            else:
                print(f"[VALID] No-leakage ok: max(timestamp_NY)={max_date_ny} == T-1={t_minus_1}")
        else:
            print("[WARN] No se encontró features_daily_enhanced.parquet para validación de leakage")
    except Exception as e:
        print(f"[WARN] No se pudo validar no-leakage: {e}")

    print("\n" + "="*80)
    print("✅ DATOS ACTUALIZADOS Y FEATURES GENERADOS")
    print("="*80)
    print("Archivo listo para inference:")
    print("  → data/daily/features_enhanced_binary_targets.parquet")
    print("\nPróximo paso:")
    print("  → run_daily_pipeline.ps1 (inference → trade plan)")
    print("="*80 + "\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
