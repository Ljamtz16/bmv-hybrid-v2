# scripts/26_policy_recompute_pnl.py
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
import numpy as np

def load_policy(policy_json: str):
    # Acepta UTF-8 con o sin BOM
    with open(policy_json, "r", encoding="utf-8-sig") as f:
        p = json.load(f)
    p.setdefault("tp_pct", 0.03)
    p.setdefault("sl_pct", 0.02)
    p.setdefault("horizon_days", 4)
    p.setdefault("min_abs_y", 0.0)
    p.setdefault("long_only", True)
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

def apply_policy(df: pd.DataFrame, pol: dict) -> pd.DataFrame:
    out = df.copy()

    # Filtros previos
    if "y_pred" in out.columns:
        out = out.loc[out["y_pred"].abs() >= pol["min_abs_y"]].copy()

    # Normaliza columnas clave
    if "side" in out.columns:
        out["side"] = out["side"].apply(_norm_side)
    else:
        out["side"] = "BUY"  # por compatibilidad (siempre mejor tenerlo explícito)

    # TP/SL por lado
    tp_pct = float(pol["tp_pct"])
    sl_pct = float(pol["sl_pct"])
    ep = out["entry_price"].astype(float)

    is_buy  = out["side"].eq("BUY")
    is_sell = out["side"].eq("SELL")

    # BUY: tp=entry*(1+tp), sl=entry*(1-sl)
    # SELL: tp=entry*(1-tp), sl=entry*(1+sl)
    out["tp_price"] = np.where(is_buy,  ep * (1.0 + tp_pct),
                               np.where(is_sell, ep * (1.0 - tp_pct), np.nan))
    out["sl_price"] = np.where(is_buy,  ep * (1.0 - sl_pct),
                               np.where(is_sell, ep * (1.0 + sl_pct), np.nan))

    # Simulación de salida
    H = int(pol["horizon_days"])
    price_cols = [c for c in out.columns if c.startswith("price_d")]
    if not price_cols:
        # Fallback por retorno acumulado a H días
        ret_col = f"ret_{H}d"
        if ret_col in out.columns:
            retH = pd.to_numeric(out[ret_col], errors="coerce").fillna(0.0)
            # BUY: exit = entry*(1+ret), SELL: exit = entry*(1+ret) pero PnL es -ret (se ajusta más abajo)
            out["exit_price_sim"] = ep * (1.0 + retH)
            out["exit_reason"] = "horizon"
        else:
            out["exit_price_sim"] = ep
            out["exit_reason"] = "none"
    else:
        # Recorre días hasta H buscando el primero que toca TP o SL; si no, sale por horizonte
        price_cols = sorted(price_cols, key=lambda s: int(s.replace("price_d","")))[:H]
        hits, reasons = [], []
        tp_vals = out["tp_price"].to_numpy(dtype=float)
        sl_vals = out["sl_price"].to_numpy(dtype=float)
        ep_vals = ep.to_numpy(dtype=float)

        for idx, row in out.iterrows():
            chosen_price, reason = None, None
            tp = tp_vals[idx]; sl = sl_vals[idx]; e = ep_vals[idx]

            for c in price_cols:
                p = row.get(c)
                if pd.isna(p):  # sin dato ese día
                    continue
                p = float(p)

                if row["side"] == "BUY":
                    if p >= tp:  chosen_price, reason = tp, "tp"; break
                    if p <= sl:  chosen_price, reason = sl, "sl"; break
                elif row["side"] == "SELL":
                    # En SELL: TP está por debajo, SL por arriba. Las comparaciones ya son correctas con los niveles calculados.
                    if p <= tp:  chosen_price, reason = tp, "tp"; break
                    if p >= sl:  chosen_price, reason = sl, "sl"; break

            if chosen_price is None:
                last_col = price_cols[-1]
                last_px = row.get(last_col)
                chosen_price = float(last_px) if pd.notna(last_px) else e
                reason = "horizon"

            hits.append(chosen_price); reasons.append(reason)

        out["exit_price_sim"] = hits
        out["exit_reason"] = reasons

    # Sizing y PnL (BUY vs SELL)
    per_trade_cash = float(pol["per_trade_cash"])
    comm = float(pol["commission_side"])

    out["shares"] = np.floor(per_trade_cash / ep).astype(int).clip(lower=0)

    # BUY: PnL = (exit - entry) * shares
    # SELL: PnL = (entry - exit) * shares
    exit_px = out["exit_price_sim"].astype(float)
    gross_buy  = (exit_px - ep) * out["shares"]
    gross_sell = (ep - exit_px) * out["shares"]
    out["gross_pnl"] = np.where(is_buy, gross_buy,
                         np.where(is_sell, gross_sell, 0.0))

    # Comisión ida+vuelta (plana por trade)
    out["net_pnl"] = out["gross_pnl"] - (2.0 * comm)
    return out

def main():
    ap = argparse.ArgumentParser(description="Recalcula PnL/TP/SL/H en la validación aplicando una política.")
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--policy-json", required=True, help="JSON generado por 25_load_wf_policy.py o manual")
    ap.add_argument("--validation-dir", default=None, help="Default: reports/forecast/<month>/validation")
    ap.add_argument("--csv-in", help="Default: <validation-dir>/validation_join_auto.csv")
    ap.add_argument("--csv-out", help="Default: <validation-dir>/validation_trades_policy.csv")
    ap.add_argument("--kpi-json-out", help="Default: <validation-dir>/kpi_policy.json")
    args = ap.parse_args()

    base = args.validation_dir or f"reports/forecast/{args.month}/validation"
    csv_in = args.csv_in or str(Path(base) / "validation_join_auto.csv")
    df = pd.read_csv(csv_in)

    pol = load_policy(args.policy_json)
    out = apply_policy(df, pol)

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

    print(f"OK -> {csv_out}")
    print(f"KPIs -> {kpi_out}")

if __name__ == "__main__":
    main()
