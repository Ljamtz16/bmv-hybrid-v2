import os, json, time, argparse, math
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
import yfinance as yf
import requests
from dotenv import load_dotenv, find_dotenv

# ========= Telegram =========
load_dotenv()

env_path = find_dotenv(usecwd=True)
loaded = load_dotenv(env_path, override=True)
print("ENV loaded:", loaded, "| path:", env_path or "<none>")

TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()


def send_tg(msg: str) -> bool:
    """Envía un mensaje a Telegram. Devuelve True si se envió OK."""
    if not TOKEN or not CHAT_ID:
        print(f"[TG] Faltan credenciales: TOKEN={'OK' if TOKEN else 'MISSING'} CHAT_ID={CHAT_ID}")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=15,
        )
        ok = r.status_code == 200 and r.json().get("ok", False)
        if not ok:
            print(f"[TG] Error: HTTP {r.status_code} {r.text}")
        return ok
    except Exception as e:
        print(f"[TG] Excepción: {e}")
        return False

# ========= Utilidades de entorno / IO =========

def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def safe_float(x, default=None):
    try:
        if x is None: return default
        if isinstance(x, (int, float)): return float(x)
        return float(str(x).replace(",", ""))
    except:
        return default

def ensure_mx(ticker: str) -> str:
    # El sistema usa tickers tipo AMXB, GFNORTEO, etc. YFinance requiere ".MX".
    t = ticker.strip()
    return t if t.endswith(".MX") else f"{t}.MX"

def latest_business_day_in(df_dates: pd.Series, until: date) -> pd.Timestamp | None:
    d = pd.to_datetime(df_dates).dt.date
    d = d[d <= until]
    if d.empty: return None
    return pd.Timestamp(max(d))

def pretty_cash(x: float) -> str:
    return f"${x:,.2f}"

# ========= Carga de política =========

def load_policy(month: str, base_dir: str):
    """
    Intenta cargar primero policy_wfbox.json del mes, si no existe toma
    la fila del mes en wf_box/.../policy_selected_walkforward.csv
    """
    wfjson = os.path.join(base_dir, "reports", "forecast", month, "policy_wfbox.json")
    if os.path.exists(wfjson):
        p = read_json(wfjson)
        return {
            "tp_pct": safe_float(p.get("tp_pct")),
            "sl_pct": safe_float(p.get("sl_pct")),
            "horizon_days": int(p.get("horizon_days", 5)),
            "per_trade_cash": safe_float(p.get("per_trade_cash", 2000)),
            "max_open": int(p.get("max_open", 5)),
            "budget": safe_float(p.get("budget", 10000)),
        }

    # CSV walk-forward
    wf_csv = os.path.join(base_dir, "wf_box", "reports", "forecast", "policy_selected_walkforward.csv")
    if not os.path.exists(wf_csv):
        raise FileNotFoundError("No hay política: faltan policy_wfbox.json y wf_box/.../policy_selected_walkforward.csv")

    df = pd.read_csv(wf_csv)
    if "month" not in df.columns:
        raise ValueError("El CSV de walk-forward no tiene columna 'month'")
    row = df.loc[df["month"] == month]
    if row.empty:
        raise ValueError(f"No encontré política para el mes {month} en {wf_csv}")
    r = row.iloc[0].to_dict()
    return {
        "tp_pct": safe_float(r.get("tp_pct")),
        "sl_pct": safe_float(r.get("sl_pct")),
        "horizon_days": int(safe_float(r.get("horizon_days"), 5)),
        "per_trade_cash": safe_float(r.get("per_trade_cash", 2000)),
        "max_open": int(safe_float(r.get("max_open"), 5)),
        "budget": safe_float(r.get("budget", 10000)),
    }

# ========= Selección de señales desde forecast =========

def load_forecast(month: str, base_dir: str) -> pd.DataFrame:
    fc_path = os.path.join(base_dir, "reports", "forecast", month, f"forecast_{month}_with_gate.csv")
    if not os.path.exists(fc_path):
        raise FileNotFoundError(f"No existe {fc_path}. Genera el forecast primero (scripts/12_forecast_and_validate.py).")
    df = pd.read_csv(fc_path)
    # Columnas típicas: ticker / date / side (BUY|SELL) / prob o score / abs_y ...
    # Normalizamos nombres clave si existen con variantes:
    # ticker
    if "ticker" not in df.columns:
        if "symbol" in df.columns: df = df.rename(columns={"symbol":"ticker"})
        else: raise ValueError("El forecast no tiene columna 'ticker' (ni 'symbol').")
    # date/ts
    date_col = None
    for c in ["date", "dt", "signal_date", "session_date"]:
        if c in df.columns:
            date_col = c; break
    if date_col is None: raise ValueError("No encontré columna de fecha (date/dt/signal_date).")
    df["date"] = pd.to_datetime(df[date_col])
    # side
    if "side" not in df.columns:
        for c in ["signal", "action"]:
            if c in df.columns:
                df["side"] = df[c].str.upper()
                break
        if "side" not in df.columns:
            raise ValueError("No encontré columna 'side'/'signal'/'action' (BUY/SELL).")

    # score para ranking: usa abs_y, prob o yhat prob
    score_col = None
    for c in ["abs_y", "prob", "score", "abs_score", "yhat_prob"]:
        if c in df.columns:
            score_col = c; break
    if score_col is None:
        df["__score__"] = 1.0
        score_col = "__score__"

    df["score"] = pd.to_numeric(df[score_col], errors="coerce").fillna(0.0)
    return df[["ticker","date","side","score"]].copy()

def pick_today_signals(df: pd.DataFrame, today: date, max_candidates: int = 10) -> pd.DataFrame:
    # Toma la fecha hábil más reciente <= hoy en el forecast
    chosen_day = latest_business_day_in(df["date"], today)
    if chosen_day is None:
        return df.iloc[0:0].copy()
    day_df = df.loc[df["date"].dt.date == chosen_day.date()].copy()
    if day_df.empty:
        return day_df
    # Una fila por ticker (si hubiera duplicados), nos quedamos con la mayor score
    day_df = day_df.sort_values(["ticker","score"], ascending=[True, False])
    day_df = day_df.groupby("ticker", as_index=False).first()
    # Ordenar por score desc y limitar
    day_df = day_df.sort_values("score", ascending=False).head(max_candidates)
    return day_df

# ========= Paper Trading =========

class PaperBroker:
    def __init__(self, per_trade_cash: float, max_open: int, budget: float, state_file="active_positions.json"):
        self.per_trade_cash = per_trade_cash
        self.max_open = max_open
        self.budget = budget
        self.state_file = state_file
        self._load()

    def _load(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, "r", encoding="utf-8") as f:
                self.positions = json.load(f)
        else:
            self.positions = {}  # id -> dict

    def _save(self):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.positions, f, indent=2, ensure_ascii=False)

    def active_count(self):
        return sum(1 for p in self.positions.values() if p["status"] == "ACTIVE")

    def used_budget(self):
        return sum(p["investment"] for p in self.positions.values() if p["status"] == "ACTIVE")

    def try_open(self, ticker: str, side: str, price: float, tp_pct: float, sl_pct: float, horizon_days: int):
        if self.active_count() >= self.max_open:
            return None, "MAX_OPEN_REACHED"
        if self.used_budget() + self.per_trade_cash > self.budget:
            return None, "BUDGET_EXCEEDED"

        # Tamaño por cash fijo
        qty = max(1, int(self.per_trade_cash // price))
        invest = qty * price

        if side.upper() == "BUY":
            tp = price * (1.0 + tp_pct)
            sl = price * (1.0 - sl_pct)
        else:
            tp = price * (1.0 - tp_pct)
            sl = price * (1.0 + sl_pct)

        pid = f"{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.positions[pid] = {
            "id": pid, "ticker": ticker, "side": side.upper(),
            "entry_price": price, "tp": tp, "sl": sl,
            "qty": qty, "investment": invest,
            "opened_at": datetime.now().isoformat(),
            "max_holding_days": int(horizon_days),
            "status": "ACTIVE"
        }
        self._save()
        return pid, "OPENED"

    def try_close_hits(self, pid: str, last_price: float):
        p = self.positions[pid]
        if p["status"] != "ACTIVE": return False, None, 0.0
        side = p["side"]
        tp = p["tp"]; sl = p["sl"]; entry = p["entry_price"]; qty = p["qty"]
        hit = None
        if side == "BUY":
            if last_price >= tp: hit = "TP_HIT"
            elif last_price <= sl: hit = "SL_HIT"
        else:
            if last_price <= tp: hit = "TP_HIT"
            elif last_price >= sl: hit = "SL_HIT"

        if hit:
            pnl = (last_price - entry) * qty if side == "BUY" else (entry - last_price) * qty
            p["status"] = "CLOSED"
            p["exit_price"] = last_price
            p["exit_at"] = datetime.now().isoformat()
            p["pnl"] = pnl
            p["result"] = hit
            self._save()
            return True, hit, pnl

        # Chequeo por horizonte (tiempo)
        opened = datetime.fromisoformat(p["opened_at"])
        if datetime.now() >= opened + timedelta(days=int(p["max_holding_days"])):
            pnl = (last_price - entry) * qty if side == "BUY" else (entry - last_price) * qty
            p["status"] = "CLOSED"
            p["exit_price"] = last_price
            p["exit_at"] = datetime.now().isoformat()
            p["pnl"] = pnl
            p["result"] = "TIME_EXIT"
            self._save()
            return True, "TIME_EXIT", pnl

        return False, None, 0.0

# ========= Monitor principal =========

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", required=True, help="Mes objetivo YYYY-MM (ej. 2025-10)")
    parser.add_argument("--base-dir", default=".", help="Raíz del repo (default: .)")
    parser.add_argument("--interval-min", type=int, default=15, help="Minutos entre chequeos (default 15)")
    parser.add_argument("--max-new", type=int, default=3, help="Máximo de nuevas aperturas por ciclo")
    args = parser.parse_args()

    month = args.month
    base_dir = os.path.abspath(args.base_dir)

    # Política
    policy = load_policy(month, base_dir)
    tp_pct = float(policy["tp_pct"])
    sl_pct = float(policy["sl_pct"])
    horizon_days = int(policy["horizon_days"])
    per_trade_cash = float(policy["per_trade_cash"])
    max_open = int(policy["max_open"])
    budget = float(policy["budget"])

    print("=== Paper monitor BMV (con forecast y política) ===")
    print(f"Mes: {month}")
    print(f"Política: TP={tp_pct*100:.2f}%  SL={sl_pct*100:.2f}%  H={horizon_days}d  cash/trade={pretty_cash(per_trade_cash)}  max_open={max_open}  budget={pretty_cash(budget)}")

    # Aviso de arranque a Telegram
    send_tg(
        f"🚀 <b>MONITOR BMV</b> iniciado\n"
        f"🗓 Mes {month}\n"
        f"🎯 TP {tp_pct*100:.1f}% | 🛡️ SL {sl_pct*100:.1f}% | ⏳ H {horizon_days}d\n"
        f"💵 {pretty_cash(per_trade_cash)} por trade | 📊 max_open={max_open} | 💼 budget={pretty_cash(budget)}"
    )

    # Forecast
    df_fc = load_forecast(month, base_dir)
    today = datetime.now().date()
    cand = pick_today_signals(df_fc, today, max_candidates=50)

    if cand.empty:
        print("No hay señales para hoy (o no hay fecha <= hoy en el forecast).")
        send_tg("ℹ️ No hay señales para hoy en el forecast.")
        return

    print(f"Señales candidatas hoy: {len(cand)} (top por score)")
    print(cand.head(10).to_string(index=False))

    # Broker papel
    broker = PaperBroker(per_trade_cash=per_trade_cash, max_open=max_open, budget=budget)

    # Bucle
    while True:
        try:
            # 1) Cerrar por TP/SL/horizonte
            active = [(pid, p) for pid, p in broker.positions.items() if p["status"] == "ACTIVE"]
            if active:
                print(f"[{datetime.now():%H:%M:%S}] Activas: {len(active)}")
                # Descargar precios actuales por lote
                tickers = list({ensure_mx(p["ticker"]) for _, p in active})
                if tickers:
                    data = yf.download(tickers=tickers, period="2d", interval="1d", progress=False, group_by="ticker", threads=True)
                    # Normalizar acceso a últimos cierres
                    last_prices = {}
                    for t in tickers:
                        try:
                            if len(tickers) == 1:
                                px = data["Close"].iloc[-1]
                            else:
                                px = data[t]["Close"].iloc[-1]
                            last_prices[t] = float(px)
                        except Exception:
                            pass

                    for pid, p in active:
                        tmx = ensure_mx(p["ticker"])
                        if tmx in last_prices:
                            closed, reason, pnl = broker.try_close_hits(pid, last_prices[tmx])
                            if closed:
                                print(f"-> Cerrada {p['ticker']} por {reason} | PnL {pretty_cash(pnl)}")
                                # 🔔 Telegram cierre
                                emoji = "🎉" if reason == "TP_HIT" else ("🛑" if reason == "SL_HIT" else "⏰")
                                sign  = "BUY" if p["side"]=="BUY" else "SELL"
                                entry = p["entry_price"]; exit_px = broker.positions[pid]["exit_price"]
                                inv   = max(1e-9, p["investment"])
                                pct   = (pnl / inv) * 100.0
                                send_tg(
                                    f"{emoji} <b>POSICIÓN CERRADA</b>\n"
                                    f"{'📈' if sign=='BUY' else '📉'} <b>{p['ticker']}</b> {sign}\n"
                                    f"📍 {reason}\n"
                                    f"💰 Entrada: {pretty_cash(entry)}  →  Salida: {pretty_cash(exit_px)}\n"
                                    f"📊 P&L: {pretty_cash(pnl)} ({pct:+.1f}%)"
                                )
                        else:
                            print(f"Sin precio para {tmx} en este ciclo")

            # 2) Si hay capacidad, intenta abrir nuevas (top score que NO estén activas/abiertas)
            capacity = max_open - broker.active_count()
            to_open = min(capacity, args.max_new)
            if to_open > 0:
                # Filtra tickers no activos
                active_tickers = {p["ticker"] for p in broker.positions.values() if p["status"] == "ACTIVE"}
                open_candidates = cand[~cand["ticker"].isin(active_tickers)].head(to_open)
                if not open_candidates.empty:
                    # Trae precios en bloque
                    tickers_new = [ensure_mx(t) for t in open_candidates["ticker"].tolist()]
                    px_new = yf.download(tickers=tickers_new, period="1d", interval="1d", progress=False, group_by="ticker", threads=True)
                    for _, row in open_candidates.iterrows():
                        t = row["ticker"]; side = str(row["side"]).upper()
                        tmx = ensure_mx(t)
                        try:
                            if len(tickers_new) == 1:
                                price = float(px_new["Close"].iloc[-1])
                            else:
                                price = float(px_new[tmx]["Close"].iloc[-1])
                        except Exception:
                            print(f"No pude obtener precio para {tmx}, salto.")
                            continue

                        pid, status = broker.try_open(t, side, price, tp_pct, sl_pct, horizon_days)
                        if status == "OPENED":
                            print(f"Abrí {t} {side} @ {pretty_cash(price)} | TP {tp_pct*100:.1f}% SL {sl_pct*100:.1f}%")
                            # 🔔 Telegram apertura
                            send_tg(
                                f"🚀 <b>NUEVA POSICIÓN</b>\n"
                                f"{'📈' if side=='BUY' else '📉'} <b>{t}</b> {side}\n"
                                f"💰 Entrada: {pretty_cash(price)}\n"
                                f"🎯 TP: {tp_pct*100:.1f}%  🛡️ SL: {sl_pct*100:.1f}%\n"
                                f"⏳ Horizonte: {horizon_days}d"
                            )
                        else:
                            print(f"No abrí {t}: {status}")

            # 3) Espera
            print(f"Duerme {args.interval_min} min - {datetime.now()+timedelta(minutes=args.interval_min):%H:%M}")
            time.sleep(args.interval_min * 60)

        except KeyboardInterrupt:
            print("Detenido por usuario.")
            send_tg("🛑 Monitor BMV detenido por el usuario.")
            break

        except Exception as e:
            print(f"Error ciclo: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
