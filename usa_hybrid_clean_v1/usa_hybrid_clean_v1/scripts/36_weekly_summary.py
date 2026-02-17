# scripts/36_weekly_summary.py
import os, csv, argparse
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from math import isnan
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>{title}</title>
<style>
 body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }}
 h1 {{ margin: 0 0 8px 0; }}
 .meta {{ color: #666; margin-bottom: 16px; }}
 .kpis {{ display: flex; gap: 16px; margin: 12px 0 20px; }}
 .card {{ border: 1px solid #e3e3e3; border-radius: 8px; padding: 12px 16px; }}
 table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
 th, td {{ border-bottom: 1px solid #eee; padding: 8px 6px; text-align: left; }}
 th {{ background: #fafafa; }}
 .pos {{ color: #0a7f00; }}
 .neg {{ color: #c40000; }}
</style>
</head>
<body>
        <h1>{title}</h1>
    <div class="meta">Window: {start} → {end} ({count} predictions)</div>
    <div class="kpis">
        <div class="card"><b>Closed</b><div>{closed}</div></div>
        <div class="card"><b>TP hits</b><div>{tp_hits}</div></div>
        <div class="card"><b>SL hits</b><div>{sl_hits}</div></div>
        <div class="card"><b>Expired</b><div>{expired}</div></div>
        <div class="card"><b>Hit-rate</b><div>{hit_rate:.1%}</div></div>
        <div class="card"><b>Net PnL</b><div class="{pnl_cls}">{net_pnl:.2f}</div></div>
    </div>

    <h3>Top tickers (by occurrences)</h3>
    <ul>
    {top_tickers}
    </ul>

    <h3>Predictions</h3>
    <table>
        <thead>
            <tr>
                <th>Created</th><th>Ticker</th><th>Side</th><th>Entry</th><th>TP</th><th>SL</th><th>Qty</th><th>Status</th><th>Exit</th><th>PnL</th>
            </tr>
        </thead>
        <tbody>
        {rows}
        </tbody>
    </table>
</body>
</html>
"""


def parse_args():
    ap = argparse.ArgumentParser(description="Weekly HTML summary from predictions_log.csv")
    ap.add_argument("--log", default="data/trading/predictions_log.csv")
    ap.add_argument("--out-html", default="reports/trading/weekly_summary.html")
    ap.add_argument("--days", type=int, default=7, help="Window length in days (default 7)")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD in market TZ")
    ap.add_argument("--market-tz", default="America/New_York")
    ap.add_argument("--title", default="Weekly Trading Summary", help="Title for HTML and Telegram text header")
    ap.add_argument("--send-telegram", action="store_true", help="Send compact text summary to Telegram")
    ap.add_argument("--send-file", action="store_true", help="Send the HTML file as a document to Telegram")
    ap.add_argument("--env-file", default=".env", help="Path to .env with TELEGRAM_* (optional)")
    return ap.parse_args()


def env(name):
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def load_env_file(path: str) -> bool:
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if "=" not in s:
                    continue
                k, v = s.split("=", 1)
                os.environ[k.strip()] = v.strip()
        return True
    except Exception:
        return False


def send_telegram_text(text: str):
    import requests
    token = env("TELEGRAM_BOT_TOKEN")
    chat = env("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, data={"chat_id": chat, "text": text, "parse_mode": "HTML"})
    r.raise_for_status()


def send_telegram_file(path: str, caption: str = ""):
    import requests
    token = env("TELEGRAM_BOT_TOKEN")
    chat = env("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(path, "rb") as f:
        r = requests.post(url, data={"chat_id": chat, "caption": caption}, files={"document": f})
    r.raise_for_status()


def market_today(tz: str, today_str: str | None):
    if today_str:
        return datetime.fromisoformat(today_str).date()
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo(tz)).date()
    return datetime.utcnow().date()


def read_log(path: str):
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def within_window(row, start_date, end_date):
    try:
        c = datetime.fromisoformat(row["created_at_utc"]).date()
    except Exception:
        return False
    return (c >= start_date) and (c <= end_date)


def to_float(v, default=0.0):
    try:
        x = float(v)
        if isnan(x):
            return default
        return x
    except Exception:
        return default


def build_summary(rows):
    closed = [r for r in rows if r.get("status") in ("TP_HIT", "SL_HIT", "EXPIRED")]
    tp_hits = sum(1 for r in closed if r.get("status") == "TP_HIT")
    sl_hits = sum(1 for r in closed if r.get("status") == "SL_HIT")
    expired = sum(1 for r in closed if r.get("status") == "EXPIRED")
    net_pnl = sum(to_float(r.get("pnl_usd"), 0.0) for r in closed)
    hit_rate = (tp_hits / max(1, (tp_hits + sl_hits))) if (tp_hits + sl_hits) > 0 else 0.0

    tickers = Counter([r.get("ticker", "?") for r in rows])
    top_tickers = "\n".join([f"<li><b>{t}</b>: {n}</li>" for t, n in tickers.most_common(8)])

    def tr(r):
        pnl = to_float(r.get("pnl_usd"), 0.0)
        pnl_cls = "pos" if pnl >= 0 else "neg"
        return (
            f"<tr><td>{r.get('created_at_utc','')}</td><td>{r.get('ticker','')}</td><td>{r.get('side','')}</td>"
            f"<td>{to_float(r.get('entry'),0):.2f}</td><td>{to_float(r.get('tp_price'),0):.2f}</td><td>{to_float(r.get('sl_price'),0):.2f}</td>"
            f"<td>{int(float(r.get('qty',0) or 0))}</td><td>{r.get('status','')}</td><td>{to_float(r.get('exit_price'),0):.2f}</td>"
            f"<td class='{pnl_cls}'>{pnl:.2f}</td></tr>"
        )

    rows_html = "\n".join(tr(r) for r in rows)
    pnl_cls = "pos" if net_pnl >= 0 else "neg"

    return {
        "closed": len(closed),
        "tp_hits": tp_hits,
        "sl_hits": sl_hits,
        "expired": expired,
        "net_pnl": net_pnl,
        "hit_rate": hit_rate,
        "pnl_cls": pnl_cls,
        "rows_html": rows_html,
        "top_tickers_html": top_tickers,
    }


def main():
    args = parse_args()

    # Load .env for Telegram if present
    load_env_file(args.env_file)

    today = market_today(args.market_tz, args.today)
    start = today - timedelta(days=max(1, args.days) - 1)
    end = today

    all_rows = read_log(args.log)
    window_rows = [r for r in all_rows if within_window(r, start, end)]

    os.makedirs(os.path.dirname(args.out_html), exist_ok=True)

    s = build_summary(window_rows)
    html = HTML_TEMPLATE.format(
        title=args.title,
        start=start.isoformat(), end=end.isoformat(), count=len(window_rows),
        closed=s["closed"], tp_hits=s["tp_hits"], sl_hits=s["sl_hits"], expired=s["expired"],
        hit_rate=s["hit_rate"], net_pnl=s["net_pnl"], pnl_cls=s["pnl_cls"],
        top_tickers=s["top_tickers_html"], rows=s["rows_html"],
    )

    with open(args.out_html, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[OK] Weekly summary -> {args.out_html}")

    # Compact text message (optional)
    if args.send_telegram:
        text = (
            f"\U0001F4C8 <b>{args.title}</b>\n"
            f"Ventana: {start.isoformat()} → {end.isoformat()}\n"
            f"Predicciones: {len(window_rows)} | Cerradas: {s['closed']}\n"
            f"TP: {s['tp_hits']} | SL: {s['sl_hits']} | Expired: {s['expired']}\n"
            f"Hit-rate: {s['hit_rate']:.1%} | Net PnL: ${s['net_pnl']:.2f}"
        )
        try:
            send_telegram_text(text)
            print("[OK] Resumen enviado a Telegram (texto)")
        except Exception as e:
            print(f"[WARN] No se pudo enviar texto a Telegram: {e}")

    # Send file as document (optional)
    if args.send_file:
        try:
            send_telegram_file(args.out_html, caption="Weekly Summary")
            print("[OK] Archivo HTML enviado a Telegram")
        except Exception as e:
            print(f"[WARN] No se pudo enviar archivo a Telegram: {e}")


if __name__ == "__main__":
    main()
