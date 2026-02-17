# scripts/10_validate_month_forecast.py
from __future__ import annotations

# --- bootstrap para que 'src' se pueda importar (igual que en 09_*) ---
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# ----------------------------------------------------------------------

import os, json, argparse
import pandas as pd
import numpy as np

from src.config import load_cfg
from src.io.loader import load_daily_map, load_hourly_map
from src.features.indicators import ensure_atr_14
from src.execution.hybrid_v2 import execute_hybrid_v2


# ===== Utils =====

def ensure_atr_aliases_inplace(d1_map: dict[str, pd.DataFrame]) -> None:
    """Garantiza que existan ambas columnas ATR14 y ATR_14 en cada DF."""
    for t, df in d1_map.items():
        if df is None or df.empty:
            continue
        df2 = ensure_atr_14(df)
        if "ATR_14" not in df2.columns and "ATR14" in df2.columns:
            df2["ATR_14"] = df2["ATR14"]
        if "ATR14" not in df2.columns and "ATR_14" in df2.columns:
            df2["ATR14"] = df2["ATR_14"]
        d1_map[t] = df2


def run_backtest(sig_df: pd.DataFrame,
                 h1_map: dict[str, pd.DataFrame],
                 d1_map: dict[str, pd.DataFrame],
                 exec_cfg: dict) -> pd.DataFrame:
    """
    Ejecuta cada señal con execute_hybrid_v2 y devuelve un DataFrame de trades.
    Espera columnas: ['ticker','date','side','prob'] (al menos).
    """
    rows = []
    if sig_df is None or sig_df.empty:
        return pd.DataFrame(rows)

    for _, s in sig_df.iterrows():
        t = s["ticker"]
        D = pd.to_datetime(s["date"]).date()
        side = str(s["side"]).upper()
        prob = float(s.get("prob", 0.0))
        if t not in h1_map or t not in d1_map or h1_map[t].empty or d1_map[t].empty:
            continue

        res = execute_hybrid_v2(
            h1_map, d1_map, t, D, side, prob,
            tp_mult=exec_cfg["tp_atr_mult"],
            sl_mult=exec_cfg["sl_atr_mult"],
            commission=exec_cfg["commission_pct"],
            slippage=exec_cfg["slippage_pct"],
            max_holding_days=exec_cfg["max_holding_days"],
            trail_atr_mult=exec_cfg.get("trail_atr_mult", 0.0),
            trail_activation_atr=exec_cfg.get("trail_activation_atr", 0.5),
            break_even_atr=exec_cfg.get("break_even_atr", 1.0),
        )
        rows.append(res)
    return pd.DataFrame(rows)


def kpis(trades_df: pd.DataFrame) -> dict:
    if trades_df is None or trades_df.empty:
        return {"Trades": 0, "WinRate_%": 0.0, "PnL_sum": 0.0, "MDD": 0.0, "Sharpe": 0.0, "Expectancy": 0.0}
    t = int(trades_df.shape[0])
    winrate = float((trades_df["pnl"] > 0).mean() * 100.0)
    pnl_sum = float(trades_df["pnl"].sum())
    eq = trades_df["pnl"].cumsum()
    roll_max = eq.cummax()
    dd = eq - roll_max
    mdd = float(-dd.min())
    ret = trades_df["pnl"]
    sharpe = float(ret.mean() / (ret.std(ddof=1) + 1e-12) * np.sqrt(252))
    expectancy = float(ret.mean())
    return {
        "Trades": t,
        "WinRate_%": round(winrate, 2),
        "PnL_sum": round(pnl_sum, 2),
        "MDD": round(mdd, 2),
        "Sharpe": round(sharpe, 2),
        "Expectancy": round(expectancy, 2),
    }


def first_bar_on_or_after(h1_df: pd.DataFrame, day_ts: pd.Timestamp) -> tuple[pd.Timestamp | None, float | None]:
    """
    Devuelve (timestamp, open) de la primera barra 1h >= day_ts.
    Si no hay barras, (None, None).
    """
    sub = h1_df.loc[h1_df.index >= day_ts]
    if sub.empty:
        return None, None
    ts = sub.index[0]
    op = float(sub.iloc[0]["Open"])
    return ts, op


def enrich_trades_with_levels(trades: pd.DataFrame,
                              h1_map: dict[str, pd.DataFrame],
                              d1_map: dict[str, pd.DataFrame],
                              exec_cfg: dict) -> pd.DataFrame:
    """
    Asegura columnas: entry_date, entry_price, tp, sl.
    Si ya vienen de execute_hybrid_v2, las respeta.
    Si faltan, infiere usando 1h para entry y ATR diario para tp/sl.
    """
    if trades is None or trades.empty:
        return trades

    out = trades.copy()

    # Normaliza tipos mínimos
    if "ticker" in out.columns:
        out["ticker"] = out["ticker"].astype(str)
    if "side" in out.columns:
        out["side"] = out["side"].astype(str).str.upper()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")

    # Asegura columnas
    for c in ["entry_date", "entry_price", "tp", "sl"]:
        if c not in out.columns:
            out[c] = np.nan

    # Evita FutureWarning: dtype datetime antes de asignar
    out["entry_date"] = pd.to_datetime(out["entry_date"], errors="coerce")

    # alias ATR
    def get_atr14(ticker: str, day: pd.Timestamp) -> float | None:
        df = d1_map.get(ticker)
        if df is None or df.empty:
            return None
        day_n = pd.Timestamp(day).normalize()
        if day_n in df.index:
            row = df.loc[day_n]
        else:
            df2 = df.loc[df.index <= day_n]
            if df2.empty:
                return None
            row = df2.iloc[-1]
        if "ATR14" in df.columns:
            return float(row["ATR14"])
        if "ATR_14" in df.columns:
            return float(row["ATR_14"])
        return None

    for i, r in out.iterrows():
        tkr = str(r.get("ticker", ""))
        side = str(r.get("side", "")).upper()
        d = pd.to_datetime(r.get("date")) if "date" in out.columns else None

        # entry_date/entry_price
        ed = r.get("entry_date", pd.NaT)
        ep = r.get("entry_price", np.nan)

        if (pd.isna(ed) or ed is pd.NaT) or pd.isna(ep):
            if tkr in h1_map and d is not None and not pd.isna(d):
                ts, open_px = first_bar_on_or_after(h1_map[tkr], d)
                if ts is not None and open_px is not None:
                    ed = pd.Timestamp(ts)
                    ep = float(open_px)
            out.at[i, "entry_date"] = ed
            out.at[i, "entry_price"] = ep

        # tp/sl
        tp_v = r.get("tp", np.nan)
        sl_v = r.get("sl", np.nan)

        if (pd.isna(tp_v) or pd.isna(sl_v)) and not pd.isna(ep) and d is not None and not pd.isna(d):
            atr = get_atr14(tkr, d)
            if atr is not None:
                tp_mult = float(exec_cfg["tp_atr_mult"])
                sl_mult = float(exec_cfg["sl_atr_mult"])
                if side == "BUY":
                    tp_v = float(ep + tp_mult * atr)
                    sl_v = float(ep - sl_mult * atr)
                else:  # SELL
                    tp_v = float(ep - tp_mult * atr)  # objetivo abajo
                    sl_v = float(ep + sl_mult * atr)  # stop arriba
                out.at[i, "tp"] = tp_v
                out.at[i, "sl"] = sl_v

    # Tipos numéricos
    out["entry_price"] = pd.to_numeric(out["entry_price"], errors="coerce")
    out["tp"] = pd.to_numeric(out["tp"], errors="coerce")
    out["sl"] = pd.to_numeric(out["sl"], errors="coerce")

    return out


# === NUEVO: trayectoria futura (price_d1..dH, ret_d1..dH, ret_{H}d) ===

def _next_trading_prices(d1_df: pd.DataFrame, start_date: pd.Timestamp, H: int, price_col: str="Close") -> list[float|None]:
    """
    Devuelve una lista de largos H con los Close de los siguientes días hábiles
    estrictamente posteriores a start_date (normalizado a fecha).
    """
    if d1_df is None or d1_df.empty:
        return [None]*H
    idx = d1_df.index
    if not isinstance(idx, pd.DatetimeIndex):
        # asume que d1_df viene con índice fecha
        d1_df = d1_df.copy()
        d1_df.index = pd.to_datetime(d1_df.index)
        idx = d1_df.index
    start_n = pd.Timestamp(start_date).normalize()
    sub = d1_df.loc[idx > start_n]
    if sub.empty:
        return [None]*H
    closes = sub[price_col].astype(float).tolist()
    closes = closes[:H]
    if len(closes) < H:
        closes += [None]*(H - len(closes))
    return closes

def enrich_trades_with_future_path(trades: pd.DataFrame,
                                   d1_map: dict[str, pd.DataFrame],
                                   H: int,
                                   price_col: str="Close") -> pd.DataFrame:
    """
    Agrega columnas price_d1..price_dH y ret_d1..ret_dH (acumulado vs entry_price),
    y ret_{H}d (alias).
    """
    if trades is None or trades.empty:
        return trades
    out = trades.copy()
    # asegúrate de tipos
    out["entry_date"] = pd.to_datetime(out.get("entry_date"), errors="coerce")
    out["entry_price"] = pd.to_numeric(out.get("entry_price"), errors="coerce")

    price_cols = [f"price_d{h}" for h in range(1, H+1)]
    ret_cols   = [f"ret_d{h}"   for h in range(1, H+1)]
    for c in price_cols + ret_cols:
        if c not in out.columns:
            out[c] = np.nan

    for i, r in out.iterrows():
        tkr = str(r.get("ticker",""))
        ed  = r.get("entry_date", pd.NaT)
        ep  = r.get("entry_price", np.nan)
        if tkr not in d1_map or pd.isna(ed) or pd.isna(ep):
            continue
        seq = _next_trading_prices(d1_map[tkr], ed, H, price_col=price_col)
        for h, px in enumerate(seq, start=1):
            out.at[i, f"price_d{h}"] = float(px) if px is not None else np.nan
            if px is not None and not pd.isna(ep) and ep != 0:
                out.at[i, f"ret_d{h}"] = (float(px) / float(ep)) - 1.0

    # alias ret_{H}d si no existe
    alias_H = f"ret_{H}d"
    if alias_H not in out.columns:
        out[alias_H] = out[f"ret_d{H}"] if f"ret_d{H}" in out.columns else np.nan

    return out


# ===== Main =====

def parse_args():
    p = argparse.ArgumentParser(description="Validar un pronóstico mensual previamente generado.")
    p.add_argument("--month", required=True, type=str, help="Mes pronosticado, p.ej. 2025-03")
    p.add_argument("--variant", type=str, default="auto",
                   help="Archivo de forecast a validar: auto|with_gate|no_gate|base (default auto)")
    # === NUEVO ===
    p.add_argument("--export-horizon", type=int, default=None,
                   help="H máximo a exportar para price_d*/ret_d* (default: cfg.exec.max_holding_days o 5).")
    p.add_argument("--export-price-col", type=str, default="Close",
                   help="Columna de precio diario a usar para price_d* (default: Close).")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg_path = os.environ.get("CFG", "config/base.yaml")
    cfg = load_cfg(cfg_path)

    ym = args.month
    forecast_dir = Path(getattr(cfg, "reports_dir", "reports")) / "forecast" / ym
    forecast_dir.mkdir(parents=True, exist_ok=True)

    # Elegir archivo de pronóstico a validar
    variant = str(args.variant).lower().strip()
    pick = None
    if variant == "with_gate":
        pick = forecast_dir / f"forecast_{ym}_with_gate.csv"
    elif variant == "no_gate":
        pick = forecast_dir / f"forecast_{ym}_no_gate.csv"
    elif variant == "base":
        pick = forecast_dir / f"forecast_{ym}_base.csv"
    else:
        # auto: prioridad with_gate → no_gate → base
        for name in [f"forecast_{ym}_with_gate.csv",
                     f"forecast_{ym}_no_gate.csv",
                     f"forecast_{ym}_base.csv"]:
            pth = forecast_dir / name
            if pth.exists():
                pick = pth
                break

    if pick is None or not pick.exists():
        print(f"⚠️ No encontré forecast en {forecast_dir}. Genera primero con 09_make_month_forecast.py")
        raise SystemExit(1)

    # Carga robusta del forecast (forzamos parse_dates=["date"])
    sig = pd.read_csv(pick, parse_dates=["date"])
    if sig.empty:
        print("⚠️ El archivo de forecast no tiene señales.")
        raise SystemExit(1)

    # Datos 1D/1H actualizados
    sH, eH = cfg.session.split("-")
    tag_session = f"{sH.replace(':','')}_{eH.replace(':','')}"
    aliases = getattr(cfg, "aliases", None)
    d1_map = load_daily_map(os.path.join(cfg.data_dir, "raw", "1d"), cfg.tickers, aliases=aliases, debug=False)
    h1_map = load_hourly_map(os.path.join(cfg.data_dir, "raw", "1h"), cfg.tickers, aliases=aliases, session_tag=tag_session, debug=False)
    ensure_atr_aliases_inplace(d1_map)

    # Ejecutar SOLO las señales pronosticadas
    exec_cfg = dict(
        tp_atr_mult=cfg.exec.tp_atr_mult,
        sl_atr_mult=cfg.exec.sl_atr_mult,
        commission_pct=cfg.exec.commission_pct,
        slippage_pct=cfg.exec.slippage_pct,
        max_holding_days=cfg.exec.max_holding_days,
        trail_atr_mult=cfg.exec.trail_atr_mult,
        trail_activation_atr=cfg.exec.trail_activation_atr,
        break_even_atr=cfg.exec.break_even_atr,
    )

    trades = run_backtest(sig, h1_map, d1_map, exec_cfg)

    # Enriquecer con entry_date/entry_price/tp/sl (si faltan)
    trades = enrich_trades_with_levels(trades, h1_map, d1_map, exec_cfg)

    # === NUEVO: exportar trayectoria futura ===
    H_export = int(args.export_horizon) if args.export_horizon else int(getattr(cfg.exec, "max_holding_days", 5))
    trades = enrich_trades_with_future_path(trades, d1_map, H_export, price_col=args.export_price_col)

    # Salidas
    out_dir = forecast_dir / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)

    trades_csv = out_dir / f"validation_trades_{variant}.csv"
    trades.to_csv(trades_csv, index=False, encoding="utf-8")

    # KPIs globales y por ticker
    k = kpis(trades)
    with (out_dir / f"kpis_{variant}.json").open("w", encoding="utf-8") as f:
        json.dump(k, f, ensure_ascii=False, indent=2)

    by_ticker = trades.groupby("ticker", dropna=False).agg(
        trades=("pnl", "count"),
        pnl_sum=("pnl", "sum"),
        win_rate=("pnl", lambda x: (x > 0).mean() * 100.0),
    ).reset_index().sort_values("pnl_sum", ascending=False)
    by_ticker.to_csv(out_dir / f"validation_by_ticker_{variant}.csv", index=False, encoding="utf-8")

    # Join forecast vs resultado (para auditar señal por señal)
    sig_j = sig.copy()
    sig_j["date"] = pd.to_datetime(sig_j["date"], errors="coerce")
    trj = trades.copy()

    # ===== normalización antes del merge =====
    def _norm_side(val):
        if pd.isna(val):
            return np.nan
        s = str(val).strip().upper()
        if s in {"1", "BUY", "LONG", "BULL"}:
            return "BUY"
        if s in {"-1", "SELL", "SHORT", "BEAR"}:
            return "SELL"
        if s in {"0", "FLAT", "NONE", "NAN"}:
            return np.nan
        return s

    for df in (sig_j, trj):
        if "ticker" in df.columns:
            df["ticker"] = df["ticker"].astype(str)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        if "side" in df.columns:
            df["side"] = df["side"].apply(_norm_side)

    sig_j = sig_j.dropna(subset=["side"])
    trj   = trj.dropna(subset=["side"])

    # columnas a conservar del trade
    keep_cols_base = ["ticker", "date", "side", "pnl", "reason", "entry_date", "entry_price", "tp", "sl"]
    # + trayectoria
    price_cols = [c for c in trj.columns if c.startswith("price_d")]
    ret_cols   = [c for c in trj.columns if c.startswith("ret_d")] + [c for c in trj.columns if c.startswith("ret_") and c.endswith("d")]
    keep_cols = [c for c in (keep_cols_base + price_cols + ret_cols) if c in trj.columns]

    merged = sig_j.merge(trj[keep_cols], on=["ticker", "date", "side"], how="left")
    merged.to_csv(out_dir / f"validation_join_{variant}.csv", index=False, encoding="utf-8")

    print("✅ Validación lista.")
    print(f"KPIs: {k}")
    print(f"Archivos: {trades_csv}, {out_dir / f'validation_by_ticker_{variant}.csv'}, {out_dir / f'validation_join_{variant}.csv'}")
