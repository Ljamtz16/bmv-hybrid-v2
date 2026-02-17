# scripts/kpi_validation_summary_mxn.py
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
import numpy as np

MXN_HINTS = {"pnl_mxn","pnl_real_mxn","pnl_mx","pnl_total_mxn"}   # tratados como MXN directos
PNL_ANY   = ["pnl_mxn","pnl_real_mxn","pnl_mx","pnl_total_mxn","PnL","pnl","pnl_real"]

def load_df(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    for c in ["side","ticker"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.upper().str.strip()
    # Normaliza fechas si existen
    for c in ["entry_date","exit_date","date"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df

def choose_pnl_series(df: pd.DataFrame) -> tuple[pd.Series|None, bool]:
    """
    Devuelve (serie_pnl, is_mxn)
      - is_mxn=True si la serie parece estar ya en MXN por trade
      - is_mxn=False si la serie son "puntos de precio" por acción
    """
    cols = set(df.columns.str.lower())
    # Busca columnas de PnL conocidas (case insensitive)
    for name in PNL_ANY:
        if name in cols:
            s = pd.to_numeric(df[name], errors="coerce")
            return s, (name in MXN_HINTS)
    # Búsqueda por coincidencia laxa (por si el CSV viene con capitalizaciones distintas)
    lower_map = {c.lower(): c for c in df.columns}
    for name in PNL_ANY:
        if name in lower_map:
            s = pd.to_numeric(df[lower_map[name]], errors="coerce")
            return s, (name in MXN_HINTS)
    return None, False

def compute_pnl_per_share_from_prices(df: pd.DataFrame) -> pd.Series:
    if not {"entry_price","exit_price","side"}.issubset(df.columns):
        missing = {"entry_price","exit_price","side"} - set(df.columns)
        raise ValueError(f"Faltan columnas para reconstruir PnL por acción: {sorted(missing)}")
    ep = pd.to_numeric(df["entry_price"], errors="coerce")
    xp = pd.to_numeric(df["exit_price"], errors="coerce")
    side = df["side"].astype(str).str.upper().str.strip()
    return np.where(side == "SELL", ep - xp, xp - ep)

def maybe_merge_prices(df: pd.DataFrame, join_path: str|None) -> pd.DataFrame:
    """
    Si faltan entry_price/exit_price, intenta merge con validation_join_auto.csv (o fallback)
    usando la llave (ticker, side, entry_date, tp, sl).
    """
    need = {"entry_price","exit_price"}
    if need.issubset(df.columns):
        return df
    if not join_path:
        return df
    jpath = Path(join_path)
    if not jpath.exists():
        print(f"⚠️ Fallback join no encontrado: {jpath}")
        return df

    jf = load_df(str(jpath))
    key = ["ticker","side","entry_date","tp","sl"]
    for k in key:
        if k not in df.columns or k not in jf.columns:
            print(f"⚠️ No se puede mergear: falta clave {k} en uno de los archivos.")
            return df

    cols_bring = [c for c in ["entry_price","exit_price","pnl_real","PnL","pnl"] if c in jf.columns]
    merged = pd.merge(df, jf[key + cols_bring], on=key, how="left", suffixes=("","_j"))
    # Completa precios si estaban ausentes
    for c in ["entry_price","exit_price"]:
        if c not in df.columns and c in merged.columns:
            pass
        elif c in merged.columns and f"{c}_j" in merged.columns:
            merged[c] = merged[c].fillna(merged[f"{c}_j"])
    return merged

def shares_from_sizing(df: pd.DataFrame, sizing: str,
                       fixed_shares: int, fixed_cash: float,
                       risk_pct: float) -> pd.Series:
    sizing = sizing.lower()
    if sizing == "fixed_shares":
        return pd.Series(int(fixed_shares), index=df.index)

    if sizing == "fixed_cash":
        if "entry_price" not in df.columns:
            raise SystemExit("❌ Para fixed_cash necesitas 'entry_price'. Usa --fallback-join para traerla si falta.")
        ep = pd.to_numeric(df["entry_price"], errors="coerce")
        sh = np.floor(fixed_cash / ep).astype("Int64")
        return sh.fillna(0).clip(lower=0)

    if sizing == "percent_risk":
        # usa sl como distancia en precio, o sl_price si existe
        if "entry_price" not in df.columns:
            raise SystemExit("❌ Para percent_risk necesitas 'entry_price'. Usa --fallback-join para traerla si falta.")
        risk_per_share = None
        if "sl" in df.columns:
            r = pd.to_numeric(df["sl"], errors="coerce")
            risk_per_share = r.where(r > 0)
        if (risk_per_share is None or risk_per_share.isna().all()) and {"sl_price","entry_price"}.issubset(df.columns):
            slp = pd.to_numeric(df["sl_price"], errors="coerce")
            ep = pd.to_numeric(df["entry_price"], errors="coerce")
            r = (ep - slp).abs()
            risk_per_share = r.where(r > 0)
        if risk_per_share is None or risk_per_share.isna().all():
            raise SystemExit("❌ percent_risk requiere 'sl' (distancia) o 'sl_price' para calcular riesgo por acción.")
        capital_total = fixed_cash if fixed_cash > 0 else 100000.0
        budget = capital_total * risk_pct
        sh = np.floor(budget / risk_per_share).astype("Int64")
        return sh.fillna(0).clip(lower=0)

    raise SystemExit("❌ sizing no reconocido. Usa: fixed_shares | fixed_cash | percent_risk")

def kpis_from_mxn(pnl_mxn: pd.Series) -> dict:
    pnl = pd.to_numeric(pnl_mxn, errors="coerce").fillna(0).values
    trades = int(np.isfinite(pnl).sum())
    winners = int((pnl > 0).sum())
    losers  = int((pnl < 0).sum())
    wr = (winners / trades * 100.0) if trades > 0 else 0.0
    total = float(np.sum(pnl))
    avg   = float(np.mean(pnl)) if trades > 0 else 0.0
    best  = float(np.max(pnl)) if trades > 0 else 0.0
    worst = float(np.min(pnl)) if trades > 0 else 0.0
    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(eq) if len(eq) else np.array([])
    dd = peak - eq if len(eq) else np.array([0.0])
    mdd = float(dd.max()) if len(dd) else 0.0
    std = float(np.std(pnl, ddof=1)) if trades > 1 else 0.0
    sharpe = (avg / std) if std > 0 else np.nan
    return {
        "trades_validos": trades,
        "ganadores": winners,
        "perdedores": losers,
        "winrate_pct": round(wr, 2),
        "ganancia_total_mxn": round(total, 2),
        "ganancia_promedio_por_trade_mxn": round(avg, 2),
        "mejor_trade_mxn": round(best, 2),
        "peor_trade_mxn": round(worst, 2),
        "mdd_mxn": round(mdd, 2),
        "sharpe_aprox": None if np.isnan(sharpe) else round(float(sharpe), 2),
    }

def main():
    ap = argparse.ArgumentParser(description="KPIs en MXN desde validation_trades_auto.csv con fallbacks")
    ap.add_argument("--csv", default="reports/forecast/2025-05/validation/validation_trades_auto.csv")
    ap.add_argument("--fallback-join", default="reports/forecast/2025-05/validation/validation_join_auto.csv",
                    help="CSV con precios si faltan (entry_price/exit_price).")
    ap.add_argument("--sizing", choices=["fixed_shares","fixed_cash","percent_risk"], default="fixed_cash")
    ap.add_argument("--fixed-shares", type=int, default=100)
    ap.add_argument("--fixed-cash", type=float, default=10000.0,
                    help="Efectivo por trade si sizing=fixed_cash; capital_total si sizing=percent_risk")
    ap.add_argument("--risk-pct", type=float, default=0.01)
    ap.add_argument("--commission", type=float, default=0.0, help="Comisión MXN por trade")
    ap.add_argument("--out-json", default="")
    args = ap.parse_args()

    df = load_df(args.csv)

    # 1) ¿Traemos PnL por trade directo?
    pnl_series, is_mxn = choose_pnl_series(df)

    # 2) Si no hay PnL directo o no es MXN, intentamos reconstruir
    if pnl_series is None or not is_mxn:
        # Asegura precios con fallback merge si faltan
        if not {"entry_price","exit_price"}.issubset(df.columns):
            df = maybe_merge_prices(df, args.fallback_join)

        if pnl_series is None:
            # intenta con precios
            try:
                pnl_per_share = compute_pnl_per_share_from_prices(df)
            except Exception as e:
                # si tenemos una columna de pnl (no mxn), úsala como puntos
                if pnl_series is not None:
                    pnl_per_share = pnl_series
                else:
                    # mensaje claro con columnas disponibles
                    print("Columnas disponibles:", list(df.columns))
                    raise SystemExit(f"❌ No hay forma de calcular PnL: {e}")
        else:
            # tenemos pnl_series pero no sabemos si es MXN; lo tomamos como puntos por acción
            pnl_per_share = pnl_series

        # Dimensionamiento → acciones y conversión a MXN
        shares = shares_from_sizing(df, args.sizing, args.fixed_shares, args.fixed_cash, args.risk_pct)
        pnl_mxn = shares * pnl_per_share
    else:
        # Ya viene en MXN por trade
        pnl_mxn = pnl_series

    # Descuenta comisión fija por trade (si aplica)
    if args.commission > 0:
        pnl_mxn = pnl_mxn - float(args.commission)

    k = kpis_from_mxn(pnl_mxn)

    print(f"Total trades válidos: {k['trades_validos']}")
    print(f"Trades ganadores: {k['ganadores']}")
    print(f"Trades perdedores: {k['perdedores']}")
    print(f"Porcentaje de aciertos: {k['winrate_pct']}%")
    print(f"Ganancia total (MXN): {k['ganancia_total_mxn']}")
    print(f"Ganancia promedio por trade (MXN): {k['ganancia_promedio_por_trade_mxn']}")
    print(f"Mejor trade (MXN): {k['mejor_trade_mxn']}")
    print(f"Peor  trade (MXN): {k['peor_trade_mxn']}")
    print(f"MDD (MXN): {k['mdd_mxn']}")
    print(f"Sharpe aprox: {k['sharpe_aprox']}")

    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(k, f, indent=2, ensure_ascii=False)
        print(f"💾 KPIs guardados en {out}")

if __name__ == "__main__":
    main()
