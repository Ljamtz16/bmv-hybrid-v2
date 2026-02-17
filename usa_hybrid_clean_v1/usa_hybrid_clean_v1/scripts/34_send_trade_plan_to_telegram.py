# scripts/34_send_trade_plan_to_telegram.py
import os, csv, uuid, time, argparse
from datetime import datetime
import requests


def env(name, default=None):
    v = os.getenv(name, default)
    if v is None:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def load_env_file(path: str) -> bool:
    """Load simple KEY=VALUE lines from a .env file into process environment.
    Returns True if loaded, False if file missing.
    """
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


def send_telegram(msg: str):
    token = env("TELEGRAM_BOT_TOKEN")
    chat = env("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, data={"chat_id": chat, "text": msg, "parse_mode": "HTML"})
    r.raise_for_status()
    return r.json()


def ensure_dir(p: str):
    d = os.path.dirname(p)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def now_utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def main():
    ap = argparse.ArgumentParser(description="Envía trade_plan a Telegram y registra en CSV")
    ap.add_argument("--trade-plan", required=True)
    ap.add_argument("--log", default="data/trading/predictions_log.csv")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--created-at", default=None, help="Override created_at_utc (ISO, e.g., 2025-10-27T14:30:00)")
    ap.add_argument("--env-file", default=".env", help="Ruta al archivo .env con TELEGRAM_* (opcional)")
    ap.add_argument("--dry-run", action="store_true", help="No envía a Telegram ni escribe en el log; sólo imprime")
    ap.add_argument("--no-send", action="store_true", help="Escribe en el log pero NO envía a Telegram")
    args = ap.parse_args()

    # Cargar .env si existe
    load_env_file(args.env_file)

    ensure_dir(args.log)
    fieldnames = [
        "prediction_id",
        "created_at_utc",
        "tag",
        "ticker",
        "side",
        "entry",
        "tp_price",
        "sl_price",
        "qty",
        "exposure",
        "prob_win",
        "y_hat",
        "horizon_days",
        "status",
        "status_ts_utc",
        "exit_price",
        "pnl_usd",
        "notes",
    ]

    # Cargar existentes para evitar duplicados (idempotencia)
    existing_rows = []
    if os.path.exists(args.log):
        with open(args.log, "r", newline="", encoding="utf-8") as f:
            existing_rows = list(csv.DictReader(f))

    # Firma para deduplicar: month(tag)|ticker|side|entry|tp|sl
    def row_signature(tag, r):
        try:
            entry = float(r["entry"])
            tp = float(r["tp_price"])
            sl = float(r["sl_price"])
        except Exception:
            entry = float(r.get("entry", 0) or 0)
            tp = float(r.get("tp_price", 0) or 0)
            sl = float(r.get("sl_price", 0) or 0)
        return f"{(tag or '').strip()}|{r['ticker']}|{r['side']}|{entry:.6f}|{tp:.6f}|{sl:.6f}"

    open_signatures = set()
    for er in existing_rows:
        if er.get("status") == "OPEN":
            sig = row_signature(er.get("tag", ""), er)
            open_signatures.add(sig)

    with open(args.trade_plan, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Determinar timestamp de creación (permite override para pruebas)
    created_ts = (args.created_at or now_utc_iso()).split(".")[0]

    # En dry-run, no escribimos log ni enviamos mensajes
    if args.dry_run:
        sent, skipped = 0, 0
        for r in rows:
            sig = row_signature(args.tag, r)
            if sig in open_signatures:
                skipped += 1
                print(f"[SKIP] Duplicado abierto: {sig}")
                continue
            # Compose and preview message
            ticker = r["ticker"]
            side = r["side"]
            entry = float(r["entry"])
            tp = float(r["tp_price"])
            sl = float(r["sl_price"])
            qty = int(float(r["qty"]))
            expo = float(r.get("exposure", qty * entry))
            p = float(r.get("prob_win", 0))
            yhat = float(r.get("y_hat", 0))
            H = int(float(r.get("horizon_days", 3)))
            msg = (
                f"\U0001F4C8 <b>PREDICCIÓN (dry-run)</b>\n"
                f"<b>{ticker}  {side}</b>\n"
                f"Entrada: <b>${entry:.2f}</b>\n"
                f"TP: <b>${tp:.2f}</b>  |  SL: <b>${sl:.2f}</b>\n"
                f"Qty: <b>{qty}</b>  |  Exposición: <b>${expo:.2f}</b>\n"
                f"H: <b>{H}d</b>  |  p≈<b>{p:.2f}</b>  |  ŷ≈<b>{yhat:+.4f}</b>\n"
                f"Tag: <code>{args.tag or ''}</code>\n"
                f"— generado {created_ts}Z"
            )
            print(msg)
            sent += 1
        print(f"[DRY-RUN] Mensajes listos: {sent}, duplicados omitidos: {skipped}")
        return

    out_exists = os.path.exists(args.log)
    with open(args.log, "a", newline="", encoding="utf-8") as wf:
        wr = csv.DictWriter(wf, fieldnames=fieldnames)
        if not out_exists:
            wr.writeheader()

        for r in rows:
            sig = row_signature(args.tag, r)
            if sig in open_signatures:
                print(f"[SKIP] Duplicado abierto: {sig}")
                continue
            ticker = r["ticker"]
            side = r["side"]
            entry = float(r["entry"])  # entry es de cierre mas reciente
            tp = float(r["tp_price"])
            sl = float(r["sl_price"])
            qty = int(float(r["qty"]))
            expo = float(r.get("exposure", qty * entry))
            p = float(r.get("prob_win", 0))
            yhat = float(r.get("y_hat", 0))
            H = int(float(r.get("horizon_days", 3)))

            msg = (
                f"\U0001F4C8 <b>PREDICCIÓN</b>\n"
                f"<b>{ticker}  {side}</b>\n"
                f"Entrada: <b>${entry:.2f}</b>\n"
                f"TP: <b>${tp:.2f}</b>  |  SL: <b>${sl:.2f}</b>\n"
                f"Qty: <b>{qty}</b>  |  Exposición: <b>${expo:.2f}</b>\n"
                f"H: <b>{H}d</b>  |  p≈<b>{p:.2f}</b>  |  ŷ≈<b>{yhat:+.4f}</b>\n"
                f"Tag: <code>{args.tag or ''}</code>\n"
                f"— generado {created_ts}Z"
            )
            if not args.no_send:
                send_telegram(msg)

            wr.writerow(
                {
                    "prediction_id": str(uuid.uuid4()),
                    "created_at_utc": created_ts,
                    "tag": args.tag or "",
                    "ticker": ticker,
                    "side": side,
                    "entry": f"{entry:.6f}",
                    "tp_price": f"{tp:.6f}",
                    "sl_price": f"{sl:.6f}",
                    "qty": str(qty),
                    "exposure": f"{expo:.6f}",
                    "prob_win": f"{p:.6f}",
                    "y_hat": f"{yhat:.6f}",
                    "horizon_days": str(H),
                    "status": "OPEN",
                    "status_ts_utc": "",
                    "exit_price": "",
                    "pnl_usd": "",
                    "notes": "",
                }
            )
            time.sleep(0.25)

    print(f"[OK] Enviadas {len(rows)} predicciones y registradas en {args.log}")


if __name__ == "__main__":
    main()
