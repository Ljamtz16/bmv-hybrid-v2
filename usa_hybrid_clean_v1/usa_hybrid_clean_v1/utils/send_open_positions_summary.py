import os, csv, argparse
from datetime import datetime
import pandas as pd
from utils.telegram_utils import load_env_file, send_telegram, throttle_keeper, format_money


def load_log(path: str):
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_daily_prices(path: str) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["date"]) if path and os.path.exists(path) else pd.DataFrame()


def latest_close(px: pd.DataFrame, ticker: str) -> float | None:
    if px is None or px.empty:
        return None
    sub = px[px["ticker"] == ticker]
    if sub.empty:
        return None
    return float(sub.sort_values("date").iloc[-1]["close"])


def main():
    ap = argparse.ArgumentParser(description="Send a compact summary of OPEN positions to Telegram")
    ap.add_argument("--log", default="data/trading/predictions_log.csv")
    ap.add_argument("--daily", default="data/us/ohlcv_us_daily.csv")
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--cooldown-seconds", type=int, default=30)
    ap.add_argument("--throttle-cache", default=".tg_throttle.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env_file(args.env_file)
    guard = throttle_keeper(args.throttle_cache)

    rows = load_log(args.log)
    open_rows = [r for r in rows if r.get("status") == "OPEN"]
    if not open_rows:
        print("[OK] No hay posiciones OPEN para resumir.")
        return

    px = load_daily_prices(args.daily)
    total_upnl = 0.0
    lines = []
    for r in open_rows:
        ticker = r.get("ticker", "?")
        side = r.get("side", "?")
        entry = float(r.get("entry") or 0)
        qty = int(float(r.get("qty") or 0))
        tp = float(r.get("tp_price") or 0)
        sl = float(r.get("sl_price") or 0)
        last = latest_close(px, ticker) or entry
        if side.upper() == "BUY":
            upnl = (last - entry) * qty
        else:
            upnl = (entry - last) * qty
        total_upnl += upnl
        lines.append(f"• {ticker}  {qty}u  E:{format_money(entry)}  TP:{format_money(tp)}  SL:{format_money(sl)}  uPnL:{format_money(upnl)}")

    msg = (
        f"\U0001F9FE <b>Posiciones abiertas</b>\n" +
        "\n".join(lines) +
        f"\n\nΣ uPnL: <b>{format_money(total_upnl)}</b>"
    )

    key = "open_positions_summary:" + datetime.utcnow().strftime("%Y-%m-%d")
    if args.dry_run:
        print("[DRY-RUN]" , msg)
    elif guard(key, cool_sec=max(1, int(args.cooldown_seconds))):
        send_telegram(msg)
        print("[OK] Resumen enviado a Telegram")
    else:
        print("[SKIP] Cooldown activo para resumen de posiciones")


if __name__ == "__main__":
    main()
