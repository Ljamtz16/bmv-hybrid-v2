# scripts/27_policy_gridsearch.py
from __future__ import annotations
import argparse, itertools, json
from pathlib import Path
import numpy as np
import pandas as pd

# ────────────────────────────────────────────────────────────────────────────────
# Opción A) Reusar lógica desde scripts/_reuse_26_policy.py (si existe)
# Opción B) Usar la copia inline (activar con --use-inline)
# ────────────────────────────────────────────────────────────────────────────────
try:
    from scripts._reuse_26_policy import apply_policy  # Recomendado si está disponible
except Exception:
    apply_policy = None


def apply_policy_inline(df: pd.DataFrame, pol: dict) -> pd.DataFrame:
    """
    Copia local de apply_policy (BUY/SELL, TP/SL/H, comisiones).
    Calcula pnl por operación y devuelve trades con columnas:
      tp_price, sl_price, exit_price_sim, exit_reason, gross_pnl, net_pnl, shares...
    """
    out = df.copy()

    def _norm_side(val):
        if pd.isna(val): return np.nan
        s = str(val).strip().upper()
        if s in {"1", "BUY", "LONG", "BULL"}:  return "BUY"
        if s in {"-1","SELL","SHORT","BEAR"}:   return "SELL"
        if s in {"0","FLAT","NONE","NAN"}:      return np.nan
        return s

    # Filtro por |y_pred| si existe
    if "y_pred" in out.columns:
        out = out.loc[out["y_pred"].abs() >= float(pol.get("min_abs_y", 0.0))].copy()

    # Normalizar side
    if "side" in out.columns:
        out["side"] = out["side"].apply(_norm_side)
    else:
        out["side"] = "BUY"

    # Parámetros de política
    tp_pct = float(pol["tp_pct"])
    sl_pct = float(pol["sl_pct"])
    H      = int(pol["horizon_days"])
    per_trade_cash   = float(pol.get("per_trade_cash", 1000.0))
    commission_side  = float(pol.get("commission_side", 5.0))

    # Precios de entrada
    if "entry_price" not in out.columns:
        # fallback típico: usar 'open' o 'close' si existieran; aquí forzamos error explícito
        raise ValueError("No existe columna 'entry_price' en el CSV de validación.")
    ep = pd.to_numeric(out["entry_price"], errors="coerce").astype(float)

    is_buy  = out["side"].eq("BUY")
    is_sell = out["side"].eq("SELL")

    # TP/SL por dirección
    out["tp_price"] = np.where(is_buy,  ep * (1.0 + tp_pct),
                               np.where(is_sell, ep * (1.0 - tp_pct), np.nan))
    out["sl_price"] = np.where(is_buy,  ep * (1.0 - sl_pct),
                               np.where(is_sell, ep * (1.0 + sl_pct), np.nan))

    # Determinar salida (con price_dX si existen; si no, horizon por retorno simulado)
    price_cols = [c for c in out.columns if c.startswith("price_d")]
    if not price_cols:
        ret_col = f"ret_{H}d"
        if ret_col in out.columns:
            retH = pd.to_numeric(out[ret_col], errors="coerce").fillna(0.0)
            out["exit_price_sim"] = ep * (1.0 + retH)
            out["exit_reason"] = "horizon"
        else:
            out["exit_price_sim"] = ep
            out["exit_reason"] = "none"
    else:
        price_cols = sorted(price_cols, key=lambda s: int(s.replace("price_d","")))[:H]
        tp_vals = out["tp_price"].to_numpy(dtype=float)
        sl_vals = out["sl_price"].to_numpy(dtype=float)
        ep_vals = ep.to_numpy(dtype=float)

        hits, reasons = [], []
        # iterrows es claro (si el CSV es grande, se puede vectorizar más adelante)
        for idx, row in out.iterrows():
            chosen_price, reason = None, None
            tp = tp_vals[idx]; sl = sl_vals[idx]; e = ep_vals[idx]
            sd = row["side"]
            for c in price_cols:
                p = row.get(c)
                if pd.isna(p): 
                    continue
                p = float(p)
                if sd == "BUY":
                    if p >= tp:  chosen_price, reason = tp, "tp"; break
                    if p <= sl:  chosen_price, reason = sl, "sl"; break
                elif sd == "SELL":
                    if p <= tp:  chosen_price, reason = tp, "tp"; break
                    if p >= sl:  chosen_price, reason = sl, "sl"; break
            if chosen_price is None:
                last_col = price_cols[-1]
                last_px = row.get(last_col)
                chosen_price = float(last_px) if pd.notna(last_px) else e
                reason = "horizon"

            hits.append(chosen_price)
            reasons.append(reason)

        out["exit_price_sim"] = hits
        out["exit_reason"] = reasons

    # Tamaño y PnL
    out["shares"] = np.floor(per_trade_cash / ep).astype(int).clip(lower=0)
    exit_px = pd.to_numeric(out["exit_price_sim"], errors="coerce").astype(float)

    gross_buy  = (exit_px - ep) * out["shares"]
    gross_sell = (ep - exit_px) * out["shares"]
    out["gross_pnl"] = np.where(is_buy, gross_buy, np.where(is_sell, gross_sell, 0.0))
    out["net_pnl"]   = out["gross_pnl"] - (2.0 * commission_side)

    return out


def kpis_from_trades(out: pd.DataFrame, month: str, pol: dict) -> dict:
    tp = (out["exit_reason"] == "tp").mean() if "exit_reason" in out.columns else np.nan
    sl = (out["exit_reason"] == "sl").mean() if "exit_reason" in out.columns else np.nan
    hz = (out["exit_reason"] == "horizon").mean() if "exit_reason" in out.columns else np.nan
    return {
        "month": month,
        "tp_pct": float(pol["tp_pct"]),
        "sl_pct": float(pol["sl_pct"]),
        "horizon_days": int(pol["horizon_days"]),
        "min_abs_y": float(pol.get("min_abs_y", 0.0)),
        "per_trade_cash": float(pol.get("per_trade_cash", 1000.0)),
        "commission_side": float(pol.get("commission_side", 5.0)),
        "trades": int(out.shape[0]),
        "tp_rate": float(tp) if pd.notna(tp) else None,
        "sl_rate": float(sl) if pd.notna(sl) else None,
        "horizon_rate": float(hz) if pd.notna(hz) else None,
        "gross_pnl_sum": float(out["gross_pnl"].sum()),
        "net_pnl_sum": float(out["net_pnl"].sum()),
    }


def parse_args():
    ap = argparse.ArgumentParser(description="Grid search de política (TP/SL/H) sobre validation_join_auto.csv")
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--validation-dir", default=None, help="Default: reports/forecast/<month>/validation")
    ap.add_argument("--csv-in", default=None, help="Default: <validation-dir>/validation_join_auto.csv")
    ap.add_argument("--grid-tp", default="0.05,0.06,0.07", help="Lista de TP pct, e.g. '0.05,0.06,0.07'")
    ap.add_argument("--grid-sl", default="0.01,0.02,0.03", help="Lista de SL pct, e.g. '0.01,0.02,0.03'")
    ap.add_argument("--grid-h",  default="2,3,5", help="Lista de horizontes (días), e.g. '1,2,3,5'")
    ap.add_argument("--min-abs-y", type=float, default=0.0, help="Filtro por |y_pred| si existe")
    ap.add_argument("--per-trade-cash", type=float, default=2000.0)
    ap.add_argument("--commission-side", type=float, default=5.0)
    ap.add_argument("--long-only", action="store_true", help="Si se usa, deja solo señales BUY")
    ap.add_argument("--save-details", action="store_true", help="Guardar CSV/JSON por combinación")
    ap.add_argument("--out-dir", default=None, help="Default: validation-dir")
    ap.add_argument("--summary-out", default=None, help="CSV de ranking (default: <out-dir>/grid_summary.csv)")
    ap.add_argument("--use-inline", action="store_true", help="Usa apply_policy_inline en lugar de importar")
    return ap.parse_args()


def main():
    args = parse_args()

    base   = args.validation_dir or f"reports/forecast/{args.month}/validation"
    csv_in = args.csv_in or str(Path(base) / "validation_join_auto.csv")
    out_dir = Path(args.out_dir or base)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_in)

    # ── Filtro LONG-ONLY (nuevo) ────────────────────────────────────────────────
    if args.long_only:
        if "side" in df.columns:
            df["side"] = df["side"].astype(str).str.upper().str.strip()
            before = len(df)
            df = df[df["side"] == "BUY"].copy()
            print(f"[LONG-ONLY] Filtradas {before - len(df)} filas no-BUY ({len(df)} restantes).")
        else:
            df["side"] = "BUY"
            print("[LONG-ONLY] No existía columna 'side', todas las señales se marcan como BUY.")
    # ───────────────────────────────────────────────────────────────────────────

    grid_tp = [float(x) for x in str(args.grid_tp).split(",") if x.strip()]
    grid_sl = [float(x) for x in str(args.grid_sl).split(",") if x.strip()]
    grid_h  = [int(x)   for x in str(args.grid_h).split(",")  if x.strip()]

    rows = []
    for tp, sl, H in itertools.product(grid_tp, grid_sl, grid_h):
        pol = dict(
            month=args.month,
            tp_pct=tp,
            sl_pct=sl,
            horizon_days=H,
            min_abs_y=args.min_abs_y,
            per_trade_cash=args.per_trade_cash,
            commission_side=args.commission_side,
            long_only=args.long_only,
        )

        use_inline = (apply_policy is None) or args.use_inline
        out = apply_policy_inline(df, pol) if use_inline else apply_policy(df, pol)

        row = kpis_from_trades(out, args.month, pol)
        rows.append(row)

        if args.save_details:
            tag = f"{tp}_{sl}_H{H}"
            out.to_csv(out_dir / f"validation_trades_policy_{tag}.csv", index=False, encoding="utf-8")
            with open(out_dir / f"kpi_policy_{tag}.json", "w", encoding="utf-8") as f:
                json.dump(row, f, ensure_ascii=False, indent=2)

        print(f"TP={tp:.2%} SL={sl:.2%} H={H} -> NetPnL={row['net_pnl_sum']:.2f}")

    summary = pd.DataFrame(rows).sort_values("net_pnl_sum", ascending=False)
    summary_out = args.summary_out or str(out_dir / "grid_summary.csv")
    summary.to_csv(summary_out, index=False, encoding="utf-8")
    print(f"\n✅ Grid listo. Ranking → {summary_out}")


if __name__ == "__main__":
    main()
