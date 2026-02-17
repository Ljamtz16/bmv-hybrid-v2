# scripts/35_check_predictions_and_notify.py
import os, sys, csv, argparse
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except Exception:  # py<3.9 fallback optional
    ZoneInfo = None
import requests, pandas as pd
# Ensure project root is on sys.path so `utils` is importable when running directly
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.telegram_utils import load_env_file as tg_load_env, send_telegram as tg_send, throttle_keeper, format_money


def env(name, default=None): 
    v = os.getenv(name, default)
    if v is None:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def send_telegram(msg: str):
    token = env("TELEGRAM_BOT_TOKEN")
    chat = env("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, data={"chat_id": chat, "text": msg, "parse_mode": "HTML"})
    r.raise_for_status()
    return r.json()


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


def load_prices_daily(path: str) -> pd.DataFrame:  # date,ticker,open,high,low,close,volume
    return pd.read_csv(path, parse_dates=["date"])


def load_prices_intraday(path: str) -> pd.DataFrame:  # datetime,ticker,open,high,low,close,volume
    return pd.read_csv(path, parse_dates=["datetime"]) if path else None


def main():
    ap = argparse.ArgumentParser(description="Evalúa predicciones y notifica TP/SL/EXPIRED por Telegram")
    ap.add_argument("--log", default="data/trading/predictions_log.csv")
    ap.add_argument("--daily", required=True)
    ap.add_argument("--intraday", default=None)
    ap.add_argument("--today", default=None)  # YYYY-MM-DD (interpreted in market TZ)
    ap.add_argument("--market-tz", default="America/New_York", help="Zona horaria de mercado para ventanas")
    ap.add_argument("--notify", choices=["ALL", "TP_SL_ONLY", "NONE"], default="ALL",
                    help="Controla qué resultados se notifican por Telegram")
    ap.add_argument("--dry-run", action="store_true", help="No envía ni persiste; sólo imprime cambios detectados")
    ap.add_argument("--env-file", default=".env", help="Ruta al archivo .env con TELEGRAM_* (opcional)")
    ap.add_argument("--min-sessions", type=int, default=1,
                    help="Sesiones mínimas (cierres de mercado) a esperar antes de marcar EXPIRED (default 1)")
    args = ap.parse_args()

    # Cargar variables desde .env si existe
    # Cargar variables desde .env si existe (central util)
    tg_load_env(args.env_file)
    guard = throttle_keeper()

    # Hoy en tz de mercado
    if args.today is None:
        if ZoneInfo is not None:
            today = datetime.now(ZoneInfo(args.market_tz)).date()
        else:
            today = datetime.utcnow().date()
    else:
        # Interpretar --today como fecha de mercado
        today = datetime.fromisoformat(args.today).date()
    px_daily = load_prices_daily(args.daily)
    px_intr = load_prices_intraday(args.intraday)

    if not os.path.exists(args.log):
        print(f"[WARN] No existe log {args.log}")
        return

    with open(args.log, "r", newline="", encoding="utf-8") as f:
        preds = list(csv.DictReader(f))

    updated = False
    for r in preds:
        if r.get("status") != "OPEN":
            continue

        ticker = r["ticker"]
        side = r["side"]
        entry = float(r["entry"])  # precio de entrada planificado
        tp = float(r["tp_price"])
        sl = float(r["sl_price"])
        qty = int(float(r["qty"]))
        H = int(float(r.get("horizon_days", 3)))
        # Convertir created_at_utc (naive UTC) a fecha de mercado
        created_naive = datetime.fromisoformat(r["created_at_utc"])  # generado en UTC sin tz
        if ZoneInfo is not None:
            created_market = created_naive.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(args.market_tz))
            start_date = created_market.date()
        else:
            start_date = created_naive.date()  # fallback
        end_date = start_date + timedelta(days=H)
        # Exigir un mínimo de sesiones antes de marcar EXPIRED
        earliest_expire = start_date + timedelta(days=max(0, int(args.min_sessions)))

        hit_tp = hit_sl = False
        exit_px = None

        sub = None
        if px_intr is not None:
            sub = px_intr[(px_intr["ticker"] == ticker) &
                          (px_intr["datetime"].dt.date >= start_date) &
                          (px_intr["datetime"].dt.date <= min(end_date, today))]
            if not sub.empty:
                # Resolver por primer toque (más realista que comprobar .any() global)
                for _, k in sub.sort_values("datetime").iterrows():
                    if side == "BUY":
                        if k["high"] >= tp:
                            hit_tp = True; exit_px = tp; break
                        if k["low"] <= sl:
                            hit_sl = True; exit_px = sl; break
                    else:  # SELL
                        if k["low"] <= tp:
                            hit_tp = True; exit_px = tp; break
                        if k["high"] >= sl:
                            hit_sl = True; exit_px = sl; break
                if exit_px is None:
                    exit_px = float(sub.iloc[-1]["close"])  # última vela observada en ventana

        if px_intr is None or (sub is not None and sub.empty):
            sd = px_daily[(px_daily["ticker"] == ticker) &
                          (px_daily["date"].dt.date >= start_date) &
                          (px_daily["date"].dt.date <= min(end_date, today))]
            if not sd.empty:
                hit_tp = (sd["high"] >= tp).any() if side == "BUY" else (sd["low"] <= tp).any()
                hit_sl = (sd["low"] <= sl).any() if side == "BUY" else (sd["high"] >= sl).any()
                exit_px = float(sd.iloc[-1]["close"])  # último close

        status = None
        note = ""
        if hit_tp and hit_sl:
            # Resolver conservadoramente por cercanía al último precio observado
            status = "TP_HIT" if abs(exit_px - tp) <= abs(exit_px - sl) else "SL_HIT"
            note = "Ambos niveles tocados; resolución conservadora por cercanía."
        elif hit_tp:
            status = "TP_HIT"
        elif hit_sl:
            status = "SL_HIT"
        else:
            # No marcar EXPIRED hasta cumplir sesiones mínimas
            if today > end_date and today > earliest_expire:
                status = "EXPIRED"
            else:
                continue  # aún en ventana, sin resultado

        if status in ("TP_HIT", "SL_HIT", "EXPIRED") and exit_px is not None:
            exit_price = tp if status == "TP_HIT" else sl if status == "SL_HIT" else exit_px
            pnl = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
            emoji = "\u2705" if status == "TP_HIT" else ("\U0001F6D1" if status == "SL_HIT" else "\u23F3")
            msg = (
                f"{emoji} <b>RESULTADO</b>\n"
                f"<b>{ticker}  {side}</b>\n"
                f"Entrada: {format_money(entry)} → Salida: {format_money(exit_price)}\n"
                f"TP: {format_money(tp)} | SL: {format_money(sl)}\n"
                f"Qty: {qty} | PnL: <b>{format_money(pnl)}</b>\n"
                f"Estado: <b>{status}</b>\n"
                f"Ventana: {start_date.isoformat()} → {min(end_date, today).isoformat()}\n"
                f"{note}"
            )

            # Política de notificación
            should_notify = True
            if args.notify == "NONE":
                should_notify = False
            elif args.notify == "TP_SL_ONLY" and status == "EXPIRED":
                should_notify = False

            key = f"trade_event:{r.get('prediction_id','?')}|{ticker}:{status}:{exit_price:.4f}"
            if args.dry_run:
                print(f"[DRY-RUN] {msg}")
            elif should_notify and guard(key, cool_sec=20):
                tg_send(msg)

            # Persistencia (siempre actualizar en memoria; escritura al final según dry-run)
            r["status"] = status
            r["status_ts_utc"] = datetime.utcnow().replace(microsecond=0).isoformat()
            r["exit_price"] = f"{exit_price:.6f}"
            r["pnl_usd"] = f"{pnl:.6f}"
            r["notes"] = note
            updated = True

    if args.dry_run:
        print("[DRY-RUN] No se escribieron cambios en el log.")
        return

    if updated and preds:
        fieldnames = preds[0].keys()
        os.makedirs(os.path.dirname(args.log), exist_ok=True)
        with open(args.log, "w", newline="", encoding="utf-8") as wf:
            wr = csv.DictWriter(wf, fieldnames=fieldnames)
            wr.writeheader()
            for x in preds:
                wr.writerow(x)
        print(f"[OK] Log actualizado: {args.log}")
    else:
        print("[OK] Sin cambios: no hubo resultados nuevos.")


if __name__ == "__main__":
    main()
