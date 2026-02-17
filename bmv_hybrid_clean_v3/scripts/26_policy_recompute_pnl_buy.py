# scripts/26_policy_recompute_pnl.py
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
import numpy as np

# ===================== UTILIDADES =====================

def load_policy(policy_json: str):
    """Carga y normaliza el JSON de política"""
    with open(policy_json, "r", encoding="utf-8-sig") as f:
        p = json.load(f)
    p.setdefault("tp_pct", 0.03)
    p.setdefault("sl_pct", 0.02)
    p.setdefault("horizon_days", 4)
    p.setdefault("min_abs_y", 0.0)
    p.setdefault("long_only", False)
    p.setdefault("per_trade_cash", 1000.0)
    p.setdefault("commission_side", 5.0)
    return p

def _norm_side(val):
    if pd.isna(val):
        return np.nan
    s = str(val).strip().upper()
    if s in {"1", "BUY", "LONG", "BULL"}:  return "BUY"
    if s in {"-1","SELL","SHORT","BEAR"}:   return "SELL"
    if s in {"0","FLAT","NONE","NAN"}:      return np.nan
    return s

# ===================== APLICACIÓN DE POLÍTICA =====================

def apply_policy(df: pd.DataFrame, pol: dict, long_only: bool = False) -> pd.DataFrame:
    """Aplica la política TP/SL/H a un DataFrame de señales"""
    out = df.copy()

    # Filtro por |y_pred|
    if "y_pred" in out.columns:
        out = out.loc[out["y_pred"].abs() >= pol["min_abs_y"]].copy()

    # Normalizar columna side
    if "side" in out.columns:
        out["side"] = out["side"].apply(_norm_side)
    else:
        out["side"] = "BUY"

    # Si es modo long-only, forzar o filtrar
    if long_only or pol.get("long_only", False):
        if "side" in out.columns:
            before = len(out)
            out = out[out["side"] == "BUY"].copy()
            print(f"[LONG-ONLY] Filtradas {before - len(out)} señales no-BUY. Restantes: {len(out)}")
        else:
            out["side"] = "BUY"
            print("[LONG-ONLY] No existía 'side'; todas marcadas como BUY.")

    # TP/SL
    tp_pct = float(pol["tp_pct"])
    sl_pct = float(pol["sl_pct"])
    ep = pd.to_numeric(out["entry_price"], errors="coerce").astype(float)

    is_buy  = out["side"].eq("BUY")
    is_sell = out["side"].eq("SELL")

    out["tp_price"] = np.where(is_buy,  ep * (1.0 + tp_pct),
                               np.where(is_sell, ep * (1.0 - tp_pct), np.nan))
    out["sl_price"] = np.where(is_buy,  ep * (1.0 - sl_pct),
                               np.where(is_sell, ep * (1.0 + sl_pct), np.nan))

    # Simulación de salida
    H = int(pol["horizon_days"])
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

        for idx, row in out.iterrows():
            chosen_price, reason = None, None
            tp = tp_vals[idx]; sl = sl_vals[idx]; e = ep_vals[idx]
            for c in price_cols:
                p = row.get(c)
                if pd.isna(p):
                    continue
                p = float(p)
                if row["side"] == "BUY":
                    if p >= tp:  chosen_price, reason = tp, "tp"; break
                    if p <= sl:  chosen_price, reason = sl, "sl"; break
                elif row["side"] == "SELL":
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

    # Cálculo de PnL
    per_trade_cash = float(pol["per_trade_cash"])
    comm = float(pol["commission_side"])

    out["shares"] = np.floor(per_trade_cash / ep).astype(int).clip(lower=0)
    exit_px = pd.to_numeric(out["exit_price_sim"], errors="coerce").astype(float)

    gross_buy  = (exit_px - ep) * out["shares"]
    gross_sell = (ep - exit_px) * out["shares"]
    out["gross_pnl"] = np.where(is_buy, gross_buy,
                         np.where(is_sell, gross_sell, 0.0))
    out["net_pnl"] = out["gross_pnl"] - (2.0 * comm)
    return out

# ===================== MAIN =====================

def main():
    ap = argparse.ArgumentParser(description="Recalcula PnL/TP/SL/H en la validación aplicando una política.")
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--policy-json", required=True, help="JSON generado por 25_load_wf_policy.py o manual")
    ap.add_argument("--validation-dir", default=None, help="Default: reports/forecast/<month>/validation")
    ap.add_argument("--csv-in", help="Default: <validation-dir>/validation_join_auto.csv")
    ap.add_argument("--csv-out", help="Default: <validation-dir>/validation_trades_policy.csv")
    ap.add_argument("--kpi-json-out", help="Default: <validation-dir>/kpi_policy.json")
    ap.add_argument("--long-only", action="store_true", help="Si se usa, evalúa únicamente señales BUY")
    args = ap.parse_args()

    base = args.validation_dir or f"reports/forecast/{args.month}/validation"
    csv_in = args.csv_in or str(Path(base) / "validation_join_auto.csv")
    df = pd.read_csv(csv_in)

    pol = load_policy(args.policy_json)

    print(f"\n=== Recompute {args.month} ===")
    if args.long_only:
        print("   Modo LONG-ONLY: solo señales BUY")
    out = apply_policy(df, pol, long_only=args.long_only)

    csv_out = args.csv_out or str(Path(base) / "validation_trades_policy.csv")
    Path(csv_out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(csv_out, index=False)

    kpis = {
        "month": args.month,
        "trades": int(out.shape[0]),
        "tp_rate": float((out["exit_reason"]=="tp").mean()) if "exit_reason" in out.columns else None,
        "sl_rate": float((out["exit_reason"]=="sl").mean()) if "exit_reason" in out.columns else None,
        "horizon_rate": float((out["exit_reason"]=="horizon").mean()) if "exit_reason" in out.columns else None,
        "gross_pnl_sum": float(out["gross_pnl"].sum()),
        "net_pnl_sum": float(out["net_pnl"].sum()),
        "per_trade_cash": float(pol["per_trade_cash"]),
        "tp_pct": float(pol["tp_pct"]),
        "sl_pct": float(pol["sl_pct"]),
        "horizon_days": int(pol["horizon_days"]),
    }
    kpi_out = args.kpi_json_out or str(Path(base) / "kpi_policy.json")
    with open(kpi_out, "w", encoding="utf-8") as f:
        json.dump(kpis, f, ensure_ascii=False, indent=2)

    print(f"✅ OK -> {csv_out}")
    print(f"📊 KPIs -> {kpi_out}")
    print(f"🧩 Trades: {kpis['trades']}  NetPnL={kpis['net_pnl_sum']:.2f}")

if __name__ == "__main__":
    main()
