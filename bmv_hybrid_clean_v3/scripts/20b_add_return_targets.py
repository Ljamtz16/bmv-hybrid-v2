# scripts/20b_add_return_targets.py
import argparse
import pandas as pd
import numpy as np

def parse_horizons(vals):
    """
    Permite:
      --horizons 3 5 10
    o
      --horizons "3,5,10"
    Retorna lista ordenada y única de enteros > 0.
    """
    if isinstance(vals, str):
        vals = [vals]
    if len(vals) == 1 and "," in vals[0]:
        vals = vals[0].split(",")
    hs = sorted({int(v) for v in vals if str(v).strip()})
    if any(h <= 0 for h in hs):
        raise ValueError("Todos los horizontes deben ser enteros > 0")
    return hs

def main():
    p = argparse.ArgumentParser(
        description="Añade targets de retorno futuro para múltiples horizontes (H) y su versión normalizada por volatilidad."
    )
    p.add_argument("--data", default="reports/forecast/training_dataset.csv",
                   help="CSV de entrada (debe incluir al menos: ticker, date, close).")
    p.add_argument("--out",  default="reports/forecast/training_dataset_w_returns.csv",
                   help="CSV de salida con targets añadidos.")
    p.add_argument("--horizons", nargs="+", default=["5"],
                   help="Horizontes H en días hábiles. Ej.: --horizons 3 5 10  o  --horizons \"3,5,10\"")
    p.add_argument("--volwin", type=int, default=20,
                   help="Ventana para volatilidad rolling (default=20).")
    p.add_argument("--ticker-col", default="ticker")
    p.add_argument("--date-col",   default="date")
    p.add_argument("--price-col",  default="close")
    p.add_argument("--keep-na", action="store_true",
                   help="No descarta filas con NaN en TODOS los targets (útil si entrenas por H aparte).")
    args = p.parse_args()

    horizons = parse_horizons(args.horizons)
    print(f"• Horizontes: {horizons}")

    df = pd.read_csv(args.data, parse_dates=[args.date_col])
    req = {args.ticker_col, args.date_col, args.price_col}
    missing = req - set(df.columns)
    if missing:
        raise SystemExit(f"❌ Faltan columnas requeridas en {args.data}: {sorted(missing)}")

    # Orden estable por ticker/fecha
    df = df.sort_values([args.ticker_col, args.date_col]).reset_index(drop=True)

    # Volatilidad rolling para normalización (std de rendimientos diarios por ticker)
    def _roll_std(s: pd.Series, win: int) -> pd.Series:
        return s.pct_change().rolling(win, min_periods=max(5, win // 2)).std()
    
    

    vol_col = f"ret_{args.volwin}d_vol"
    if vol_col not in df.columns:
        df[vol_col] = (
            df.groupby(args.ticker_col)[args.price_col]
              .transform(lambda s: _roll_std(s, args.volwin))
        )

    added = []
    for H in horizons:
        # Futuro a H días: shift negativo
        fut = df.groupby(args.ticker_col)[args.price_col].shift(-H)
        raw = (fut / df[args.price_col] - 1.0).astype(float)
        tgt_raw = f"target_return_{H}d"
        tgt_norm = f"{tgt_raw}_volnorm"

        df[tgt_raw]  = raw
        df[tgt_norm] = raw / df[vol_col].replace([0, np.inf, -np.inf], np.nan).clip(lower=1e-8)
        added += [tgt_raw, tgt_norm]

    # Limpieza (opcional): elimina filas que tengan NaN en TODOS los targets agregados
    if added and not args.keep_na:
        mask_all_nan = df[added].isna().all(axis=1)
        if mask_all_nan.any():
            df = df[~mask_all_nan].copy()

    # === Añadir columnas clave para la regresión de retorno ===
    # Mapea 'entry_date' y 'entry_price' a nombres genéricos que 20b puede leer por flags:
    df["entry_date"] = pd.to_datetime(df.get("entry_date", pd.NaT))
    df["entry_price"] = pd.to_numeric(df.get("entry_price", np.nan), errors="coerce")

    # Recorta columnas para dejar solo las necesarias
    cols = [args.ticker_col, args.date_col, args.price_col, vol_col] + added
    df = df[cols]
    

    df.to_csv(args.out, index=False)
    print(f"✅ Guardado: {args.out}")
    for H in horizons:
        raw, norm = f"target_return_{H}d", f"target_return_{H}d_volnorm"
        print(f"  • H={H}d → {raw} (non-NaN={(~df[raw].isna()).sum():,}), {norm} (non-NaN={(~df[norm].isna()).sum():,})")
    print(f"ℹ️ Se usó columna de volatilidad: {vol_col}")

if __name__ == "__main__":
    main()
# scripts/20b_add_return_targets.py