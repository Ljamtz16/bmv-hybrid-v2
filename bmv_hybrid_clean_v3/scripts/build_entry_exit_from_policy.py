import argparse
import re
from pathlib import Path
import pandas as pd
import json

def infer_horizon_from_filename(csv_path: Path, default_h=2):
    m = re.search(r"_H(\d+)\.csv$", csv_path.name)
    if m:
        return int(m.group(1))
    return default_h

def read_kpi_neighbor(folder: Path):
    # Busca un kpi_* en el mismo folder
    cands = list(folder.glob("kpi*.json")) + list(folder.glob("*kpi*.json"))
    if not cands:
        return {}
    latest = max(cands, key=lambda p: p.stat().st_mtime)
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return {}

def side_to_sign(side_val):
    """
    Convierte 'side' a +1 (long/BUY) o -1 (short/SELL).
    Acepta textos y numéricos.
    """
    if pd.isna(side_val):
        return 1
    s = str(side_val).strip().lower()
    if s in ("buy","long","1","l","b","true","t"):
        return +1
    if s in ("sell","short","-1","s","sh","false","f"):
        return -1
    # por defecto, asumimos long
    return +1

def first_hit_day(row, H, price_cols):
    """
    Devuelve el primer día (1..H) en que toca TP o SL según el 'side'.
    price_cols: lista ['price_d1','price_d2',...]
    Requiere columnas: side, tp_price, sl_price
    """
    sign = side_to_sign(row.get("side", None))
    tp = row.get("tp_price", None)
    sl = row.get("sl_price", None)

    # Si faltan precios objetivo, no podemos detectar antes del horizonte
    if pd.isna(tp) or pd.isna(sl):
        return None, None

    for k in range(1, H+1):
        col = f"price_d{k}"
        if col not in price_cols:
            break
        p = row.get(col, None)
        if pd.isna(p):
            continue

        if sign == +1:  # long
            if p >= tp:
                return k, "tp"
            if p <= sl:
                return k, "sl"
        else:  # short
            if p <= tp:
                return k, "tp"
            if p >= sl:
                return k, "sl"
    return None, None

def main():
    ap = argparse.ArgumentParser(description="Construye entry_time/exit_time para CSV policy_* (sin columna exit).")
    ap.add_argument("--csv", required=True, help="Ruta al CSV policy_*")
    ap.add_argument("--out", default="", help="Ruta de salida; por defecto agrega sufijo .with_times.csv en el mismo folder")
    ap.add_argument("--h", type=int, default=0, help="Horizonte (días). Si 0, intenta inferir de filename o KPI JSON.")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"No existe: {csv_path}")

    df = pd.read_csv(csv_path)

    # Detectar columnas de precios d1..dH
    price_cols = [c for c in df.columns if re.fullmatch(r"price_d\d+", c)]
    price_cols_sorted = sorted(price_cols, key=lambda x: int(x.split("_d")[-1]))
    H_from_prices = int(price_cols_sorted[-1].split("_d")[-1]) if price_cols_sorted else 0

    # Horizonte: CLI > filename > KPI JSON > H_from_prices > 2
    H = args.h if args.h > 0 else 0
    if H == 0:
        H = infer_horizon_from_filename(csv_path, default_h=0)
    if H == 0:
        kpi = read_kpi_neighbor(csv_path.parent)
        H = int(kpi.get("horizon_days", 0)) if kpi else 0
    if H == 0:
        H = H_from_prices
    if H == 0:
        H = 2  # fallback seguro

    # Asegurar entry_time
    # Preferimos 'entry' si existe; luego 'entry_date'
    entry_col = "entry" if "entry" in df.columns else ("entry_date" if "entry_date" in df.columns else None)
    if entry_col is None:
        raise SystemExit("No encontré columna de entrada ('entry' o 'entry_date').")

    df["entry_time"] = pd.to_datetime(df[entry_col], errors="coerce")

    # Reconstruir exit_time fila por fila
    exits = []
    reasons = []
    for _, row in df.iterrows():
        k, reason = first_hit_day(row, H, set(price_cols_sorted))
        if pd.isna(row["entry_time"]):
            exits.append(pd.NaT)
            reasons.append(reason if reason else row.get("exit_reason", None))
            continue

        if k is None:
            # No tocó TP/SL -> horizonte
            exit_t = row["entry_time"] + pd.Timedelta(days=H)
            reason_out = reason if reason else (row.get("exit_reason", None) or "horizon")
        else:
            exit_t = row["entry_time"] + pd.Timedelta(days=int(k))
            reason_out = reason  # "tp" o "sl"
        exits.append(exit_t)
        reasons.append(reason_out)

    df["exit_time"] = exits
    # Guardamos la razón reconstruida solo si no había
    if "exit_reason" not in df.columns:
        df["exit_reason"] = reasons
    else:
        # donde exit_reason esté vacío, rellenamos
        df["exit_reason"] = df["exit_reason"].fillna(pd.Series(reasons))

    # Orden sugerido de columnas nuevas al frente
    front_cols = ["entry_time", "exit_time", "exit_reason"]
    other_cols = [c for c in df.columns if c not in front_cols]
    df = df[front_cols + other_cols]

    # Salida
    out_path = Path(args.out) if args.out else csv_path.with_suffix(".with_times.csv")
    df.to_csv(out_path, index=False)
    print(f"✅ Generado: {out_path}")
    print(f"   Horizonte usado (H): {H}")
    print(f"   Columnas de precios detectadas: {', '.join(price_cols_sorted) if price_cols_sorted else '(ninguna)'}")

if __name__ == "__main__":
    main()
