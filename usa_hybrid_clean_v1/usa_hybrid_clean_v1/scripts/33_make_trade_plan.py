# scripts/33_make_trade_plan.py
import os, sys, argparse, math, pandas as pd
from datetime import datetime

# Ensure project root is on sys.path so `utils` is importable when running directly
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.telegram_utils import load_env_file as tg_load_env, send_telegram as tg_send, throttle_keeper, format_money


def load_forecast(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Requerimiento: prob_win (probabilidad de ganancia)
    # y_hat ya no es requerido — fue diseño anterior para retorno esperado
    # que nunca se implementó, así que usamos prob_win como proxy de confianza
    if "prob_win" not in df.columns:
        raise ValueError(f"Missing column 'prob_win' in {path}")
    
    # Respetar gates si existen
    if "gate_ok" in df.columns:
        df = df[df["gate_ok"] == 1]
    if "gate_pattern_ok" in df.columns:
        df = df[df["gate_pattern_ok"] == 1]
    return df


def load_prices(path: str) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["date"])  # date,ticker,open,high,low,close,volume


def last_close(prices_df: pd.DataFrame, ticker: str):
    sub = prices_df[prices_df["ticker"] == ticker]
    if sub.empty:
        return None
    return float(sub.sort_values("date").iloc[-1]["close"])


def main():
    ap = argparse.ArgumentParser(description="Construye un trade plan ejecutable a partir del forecast")
    ap.add_argument("--month", required=True)
    ap.add_argument("--forecast_file", required=True)
    ap.add_argument("--prices_file", required=True)
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--max-open", type=int, default=5)
    ap.add_argument("--tp-pct", type=float, default=0.06)
    ap.add_argument("--sl-pct", type=float, default=0.0015)
    ap.add_argument("--horizon-days", type=int, default=3)
    ap.add_argument("--out", required=True)
    ap.add_argument("--asof-date", default=None, help="YYYY-MM-DD para filtrar forecast a ese día exacto antes de generar el plan")
    ap.add_argument("--preview", type=int, default=5, help="Muestra top-N filas en consola")
    ap.add_argument("--notify-new-signals", action="store_true", help="Envía señales nuevas a Telegram al finalizar")
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--cooldown-seconds", type=int, default=30)
    ap.add_argument("--throttle-cache", default=".tg_throttle.json")
    ap.add_argument("--dry-run", action="store_true", help="Muestra los avisos pero no envía a Telegram")
    args = ap.parse_args()

    # Guardrails
    max_open = max(2, min(5, int(args.max_open)))
    per_trade_cash = math.floor(args.capital / max_open)

    f = load_forecast(args.forecast_file)
    px = load_prices(args.prices_file)

    # Limitar forecast al último día de mercado por ticker
    try:
        f0 = f.copy()
        # Si se indicó --asof-date, filtrar explícitamente por ese día primero
        if args.asof_date:
            try:
                asof = pd.to_datetime(args.asof_date).date()
                if "date" in f.columns:
                    f["date"] = pd.to_datetime(f["date"], errors="coerce")
                    f = f[f["date"].dt.date == asof]
            except Exception:
                pass
        last_dates = px.groupby("ticker")["date"].max().rename("last_date").reset_index()
        if "date" in f.columns:
            f["date"] = pd.to_datetime(f["date"], errors="coerce")
            f = f.merge(last_dates, on="ticker", how="left")
            # Comparar por fecha (sin tiempo)
            f = f[f["date"].dt.date == f["last_date"].dt.date]
            f = f.drop(columns=["last_date"])  # limpiar columna auxiliar
            # Fallback: si quedó vacío (p.ej., forecast no tiene ese último día), usar el último día del forecast por ticker
            if f.empty:
                f = f0.copy()
                if "date" in f.columns:
                    f["date"] = pd.to_datetime(f["date"], errors="coerce")
                    last_f = f.groupby("ticker")["date"].max().rename("last_f").reset_index()
                    f = f.merge(last_f, on="ticker", how="left")
                    f = f[f["date"].dt.date == f["last_f"].dt.date]
                    f = f.drop(columns=["last_f"])  # limpiar auxiliar
    except Exception:
        # Si algo falla, continuar sin filtrar (mejor que romper el plan)
        pass

    # Dirección y fuerza
    # Usar prob_win directamente como confianza de dirección
    # (y_hat sería retorno esperado, pero no está disponible en este pipeline)
    f["side"] = f["prob_win"].apply(lambda v: "BUY" if v > 0.5 else "SELL")
    f["strength"] = f["prob_win"]  # Probabilidad de ganar como métrica de fuerza
    if "pattern_weight" in f.columns:
        f["strength"] *= (1.0 + 0.25 * f["pattern_weight"].fillna(0.0))

    # Entradas con último close
    f["entry"] = f["ticker"].apply(lambda t: last_close(px, t))
    f = f.dropna(subset=["entry"])  # eliminar tickers sin precio reciente

    # TP/SL
    def tp_price(entry, side, tp_pct):
        return entry * (1 + tp_pct) if side == "BUY" else entry * (1 - tp_pct)

    def sl_price(entry, side, sl_pct):
        return entry * (1 - sl_pct) if side == "BUY" else entry * (1 + sl_pct)

    f["tp_price"] = f.apply(lambda r: tp_price(r["entry"], r["side"], args.tp_pct), axis=1)
    f["sl_price"] = f.apply(lambda r: sl_price(r["entry"], r["side"], args.sl_pct), axis=1)

    # Tamaño y exposición
    f["qty"] = (per_trade_cash / f["entry"]).apply(lambda x: max(1, int(x)))
    f["exposure"] = f["qty"] * f["entry"]

    # Selección top por fuerza respetando max_open
    cols = [
        "ticker",
        "side",
        "entry",
        "tp_price",
        "sl_price",
        "qty",
        "exposure",
        "prob_win",
        "strength",
    ]
    opt = [c for c in ["pattern_weight", "gate_ok", "gate_pattern_ok", "date"] if c in f.columns]
    plan = f.sort_values("strength", ascending=False)[cols + opt].head(max_open).copy()

    # Respetar capital total
    total_expo = float(plan["exposure"].sum()) if not plan.empty else 0.0
    if total_expo > args.capital:
        rows, run = [], 0.0
        for _, r in plan.iterrows():
            if run + r["exposure"] <= args.capital:
                rows.append(r)
                run += r["exposure"]
        plan = pd.DataFrame(rows) if rows else plan.head(1)

    plan["per_trade_cash"] = per_trade_cash
    plan["capital_cap"] = args.capital
    plan["horizon_days"] = args.horizon_days
    plan["policy"] = f"Policy_Dynamic_V2_{args.month}"
    plan["generated_at"] = datetime.utcnow().isoformat()

    plan.to_csv(args.out, index=False)
    print(f"[OK] Trade plan -> {args.out}")

    # Preview
    top = min(args.preview, len(plan)) if not plan.empty else 0
    if top > 0:
        print("\n=== PREVIEW (top-{} por strength) ===".format(top))
        print(
            plan[
                [
                    "ticker",
                    "side",
                    "entry",
                    "tp_price",
                    "sl_price",
                    "qty",
                    "exposure",
                    "prob_win",
                    "y_hat",
                    "strength",
                ]
            ]
            .head(top)
            .to_string(index=False)
        )
    else:
        print("\n=== PREVIEW: no hay filas que mostrar ===")

    # Aviso de nuevas señales (opcional)
    if args.notify_new_signals and not plan.empty:
        tg_load_env(args.env_file)
        guard = throttle_keeper(args.throttle_cache)
        sent, skipped = 0, 0
        for _, r in plan.iterrows():
            ticker = str(r["ticker"]).strip()
            side = str(r["side"]).strip()
            entry = float(r["entry"]) if not pd.isna(r["entry"]) else 0.0
            tp = float(r["tp_price"]) if not pd.isna(r["tp_price"]) else 0.0
            sl = float(r["sl_price"]) if not pd.isna(r["sl_price"]) else 0.0
            qty = int(r["qty"]) if not pd.isna(r["qty"]) else 0
            p = float(r.get("prob_win", 0) or 0)
            yhat = float(r.get("y_hat", 0) or 0)
            key = f"new_signal:{ticker}:{side}:{entry:.4f}"
            if not guard(key, cool_sec=max(1, int(args.cooldown_seconds))):
                skipped += 1
                continue
            msg = (
                f"\U0001F7E2 <b>Nueva señal</b>\n"
                f"• <b>{ticker}</b> — <b>{side}</b>\n"
                f"• Entrada: {format_money(entry)}   Qty: {qty}\n"
                f"• TP: {format_money(tp)}   SL: {format_money(sl)}\n"
                f"• prob_win: {p:.2f}   ŷ: {yhat:+.4%}"
            )
            if args.dry_run:
                print(f"[DRY-RUN] {msg}")
            else:
                tg_send(msg)
            sent += 1
        print(f"[notify] nuevas señales enviadas: {sent}, saltadas por cooldown: {skipped}")


if __name__ == "__main__":
    main()
