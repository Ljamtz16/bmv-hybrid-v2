#!/usr/bin/env python3
"""
Trade Dashboard Unificado - 4 Pestañas Profesionales
"""
import pandas as pd
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template_string, jsonify
import logging
import socket
import pytz
import pandas_market_calendars as mcal

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

TRADE_PLAN_PATH = Path("val/trade_plan_EXECUTE.csv")
TRADE_HISTORY_PATH = Path("val/trade_history_closed.csv")
STANDARD_PLAN_PATH = Path("val/trade_plan_STANDARD.csv")
STANDARD_PLANS_DIR = Path("evidence") / "weekly_plans"
STANDARD_TRACK_PATH = Path("val/standard_plan_tracking.csv")

# Cache de precios (TTL 30s)
PRICE_CACHE = {}
CACHE_TTL = 30

def get_max_capital():
    """Lee capital máximo de config o usa 800 por defecto"""
    try:
        import yaml
        config_path = Path("config/base.yaml")
        if config_path.exists():
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
                return cfg.get('capital_max', 800)
    except:
        pass
    return 800

def get_cached_prices(tickers):
    """Obtiene precios actuales con cache de 30s. Batch request."""
    import yfinance as yf
    from datetime import datetime, timedelta
    
    now = datetime.now()
    result = {}
    tickers_to_fetch = []
    
    for ticker in tickers:
        cached = PRICE_CACHE.get(ticker)
        if cached and (now - cached['timestamp']).seconds < CACHE_TTL:
            result[ticker] = cached['price']
        else:
            tickers_to_fetch.append(ticker)
    
    # Batch fetch para tickers no cacheados
    if tickers_to_fetch:
        try:
            # yfinance batch (espacio separado)
            tickers_str = ' '.join(tickers_to_fetch)
            data = yf.download(tickers_str, period='1d', interval='1m', progress=False, threads=True)
            
            for ticker in tickers_to_fetch:
                try:
                    if len(tickers_to_fetch) == 1:
                        price = float(data['Close'].iloc[-1])
                    else:
                        price = float(data['Close'][ticker].iloc[-1])
                    PRICE_CACHE[ticker] = {'price': price, 'timestamp': now}
                    result[ticker] = price
                except:
                    result[ticker] = None
        except:
            # Fallback: individual si batch falla
            for ticker in tickers_to_fetch:
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="1d", interval="1m")
                    if not hist.empty:
                        price = float(hist['Close'].iloc[-1])
                        PRICE_CACHE[ticker] = {'price': price, 'timestamp': now}
                        result[ticker] = price
                    else:
                        result[ticker] = None
                except:
                    result[ticker] = None
    
    return result

def get_local_ip():
    try:
        import socket
        # Obtener todas las interfaces
        hostname = socket.gethostname()
        all_ips = socket.gethostbyname_ex(hostname)[2]
        # Filtrar IPv4 válidas que NO sean 127.x.x.x ni 169.x.x.x
        for ip in all_ips:
            if not ip.startswith('127.') and not ip.startswith('169.') and not ip.startswith('192.168.137'):
                return ip
        # Si no encontramos una buena IP, retornar la primera válida
        for ip in all_ips:
            if not ip.startswith('127.') and not ip.startswith('169.'):
                return ip
        return "127.0.0.1"
    except:
        return "127.0.0.1"

def estimate_time_to_target(ticker, current_price, target_price, side="BUY"):
    """Estima tiempo basado en distancia real a target y velocidad combinada (70% velocity + 30% ATR)."""
    try:
        import yfinance as yf
        
        # Obtener histórico de 1 minuto (últimas 5 días)
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d", interval="1m")
        
        if hist.empty or len(hist) < 20:
            return None
        
        # Método 1: Velocidad actual (últimos 60 minutos)
        changes_recent = hist['Close'].diff().dropna().tail(60)
        if len(changes_recent) > 0:
            velocity_current = changes_recent.abs().mean()
        else:
            velocity_current = 0
        
        # Método 2: Volatilidad histórica (ATR - Average True Range de 14 períodos)
        high_low = hist['High'] - hist['Low']
        high_close = abs(hist['High'] - hist['Close'].shift())
        low_close = abs(hist['Low'] - hist['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.tail(14).mean()
        
        # Combinar: 70% velocidad actual + 30% ATR (volatilidad esperada)
        if velocity_current > 0 and atr > 0:
            combined_velocity = (velocity_current * 0.7) + (atr * 0.3)
        elif velocity_current > 0:
            combined_velocity = velocity_current
        elif atr > 0:
            combined_velocity = atr
        else:
            return None
        
        # Distancia a recorrer (basado en precio actual y target real)
        distance = abs(target_price - current_price)
        
        # Tiempo estimado en minutos
        estimated_minutes = distance / combined_velocity
        
        return max(1, int(round(estimated_minutes)))
        
    except Exception as e:
        print(f"[WARNING] Error estimating time for {ticker}: {e}")
        return None

def get_time_from_plan(ticker, plan_path=None):
    """Lee tiempo estimado del CSV del plan desde columna 'etth_days_raw' y convierte a minutos."""
    try:
        if plan_path is None:
            plan_path = TRADE_PLAN_PATH
        
        if not Path(plan_path).exists():
            return None
        
        df = pd.read_csv(plan_path)
        if 'etth_days_raw' not in df.columns:
            return None
        
        row = df[df['ticker'].str.upper() == ticker.upper()]
        if row.empty:
            return None
        
        time_days = row.iloc[0]['etth_days_raw']
        if pd.isna(time_days) or time_days <= 0:
            return None
        
        # Convertir de días a minutos (1 día = 24 * 60 = 1440 minutos)
        minutes = int(time_days * 24 * 60)
        return max(1, minutes)
    except Exception as e:
        print(f"[WARNING] Error reading plan time for {ticker}: {e}")
        return None

def get_market_status():
    """Obtiene el estado del mercado NYSE usando zona horaria correcta y calendario real"""
    try:
        ny_tz = pytz.timezone('US/Eastern')
        now_ny = datetime.now(ny_tz)
        today = now_ny.date()
        current_time = now_ny.time()
        
        # Obtener calendario NYSE
        nyse = mcal.get_calendar('NYSE')
        schedule = nyse.schedule(start_date=today, end_date=today)
        
        # Si no hay schedule, es día no laborable (fin de semana o feriado)
        if schedule.empty:
            return "🔴 CERRADO", "danger", "Fin de semana o feriado"
        
        # Obtener horas de apertura y cierre
        market_open = schedule.iloc[0]['market_open'].tz_convert(ny_tz).time()
        market_close = schedule.iloc[0]['market_close'].tz_convert(ny_tz).time()
        
        # Verificar si el mercado está abierto
        if market_open <= current_time < market_close:
            time_str = f"{market_open.strftime('%H:%M')} - {market_close.strftime('%H:%M')} ET"
            return "🟢 ABIERTO", "success", time_str
        else:
            time_str = f"Cerrado - Abre {market_open.strftime('%H:%M')} ET"
            return "🔴 CERRADO", "danger", time_str
            
    except Exception as e:
        print(f"[WARNING] Error checking market status: {e}")
        # Fallback simple
        hour = datetime.now().hour
        if 14 <= hour < 21:
            return "⚠️ ABIERTO (estimado)", "warning", "09:30 - 16:00 ET"
        else:
            return "🔴 CERRADO", "danger", "Fuera de horario"

def load_active_trades():
    """Carga trades activos y obtiene precios actuales con cache"""
    try:
        if not TRADE_PLAN_PATH.exists():
            return []
            
        df = pd.read_csv(TRADE_PLAN_PATH)
        trades = []
        
        # Obtener todos los tickers para batch fetch
        tickers = [row.get("ticker", "") for _, row in df.iterrows()]
        prices = get_cached_prices(tickers)
        
        for _, row in df.iterrows():
            ticker = row.get("ticker", "")
            entry = float(row.get("entry", 0))
            tp = float(row.get("tp_price", 0))
            sl = float(row.get("sl_price", 0))
            
            # Obtener precio del cache
            current_price = prices.get(ticker, entry)
            if current_price is None:
                current_price = entry
            
            # Calcular PnL actual
            side = str(row.get("side", "BUY")).upper()
            if side == "BUY":
                pnl = current_price - entry
            else:  # SELL
                pnl = entry - current_price
            
            # Priorizar tiempo del plan (etth_days_raw) si existe
            time_to_tp = get_time_from_plan(ticker, TRADE_PLAN_PATH)
            if time_to_tp is None and tp > 0:
                # Fallback: estimador basado en volatilidad
                time_to_tp = estimate_time_to_target(ticker, current_price, tp, side)
            
            time_to_sl = None
            if sl > 0:
                time_to_sl = estimate_time_to_target(ticker, current_price, sl, side)
            
            trades.append({
                "ticker": ticker,
                "side": side,
                "entry": entry,
                "exit": current_price,  # Precio actual
                "tp": tp,
                "sl": sl,
                "qty": int(row.get("qty", 1)),
                "prob_win": float(row.get("prob_win", 50)),
                "pnl": pnl,
                "time_to_tp": time_to_tp,
                "time_to_sl": time_to_sl
            })
        
        return trades
        
    except Exception as e:
        print(f"[WARNING] Error loading trades: {e}")
        import traceback
        traceback.print_exc()
    return []

def _load_latest_standard_plan():
    """Carga el plan STANDARD más reciente (val o evidence/weekly_plans)."""
    try:
        if STANDARD_PLAN_PATH.exists():
            return pd.read_csv(STANDARD_PLAN_PATH)

        if STANDARD_PLANS_DIR.exists():
            standard_files = sorted(STANDARD_PLANS_DIR.glob("plan_standard_*.csv"))
            if standard_files:
                return pd.read_csv(standard_files[-1])
    except Exception as e:
        print(f"[WARNING] Error loading STANDARD plan: {e}")
    return pd.DataFrame()

def _normalize_standard_plan(plan_df):
    if plan_df is None or plan_df.empty:
        return pd.DataFrame()

    def pick(row, *keys, default=None):
        for k in keys:
            if k in row and pd.notna(row[k]):
                return row[k]
        return default

    rows = []
    now_iso = datetime.now().isoformat()
    for _, row in plan_df.iterrows():
        ticker = str(pick(row, "ticker", default="")).upper()
        if not ticker:
            continue
        side = str(pick(row, "side", "direction", default="BUY")).upper()
        entry = float(pick(row, "entry", "entry_price", default=0) or 0)
        tp_price = float(pick(row, "tp_price", "tp", default=0) or 0)
        sl_price = float(pick(row, "sl_price", "sl", default=0) or 0)
        qty = float(pick(row, "qty", "quantity", default=1) or 1)
        generated_at = str(pick(row, "generated_at", "date", "timestamp", default=now_iso))

        # ID único: STD + ticker + side + entry (evita duplicados)
        trade_id = f"STD-{ticker}-{side}-{entry:.4f}".replace(" ", "T")
        rows.append({
            "trade_id": trade_id,
            "ticker": ticker,
            "side": side,
            "entry": entry,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "qty": qty,
            "plan_type": "STANDARD",
            "entry_time": generated_at,
            "generated_at": generated_at
        })

    return pd.DataFrame(rows)

def _remove_closed_from_plans(closed_tickers, plan_type="ALL"):
    """Remueve tickers cerrados SOLO de archivos activos en val/ (NO toca evidence histórica)."""
    try:
        removed_count = 0
        
        # Remover del plan STANDARD activo (SOLO val/)
        if plan_type in ["STANDARD", "ALL"]:
            if STANDARD_PLAN_PATH.exists():
                df = pd.read_csv(STANDARD_PLAN_PATH)
                original_len = len(df)
                df = df[~df["ticker"].str.upper().isin(closed_tickers)]
                if len(df) < original_len:
                    df.to_csv(STANDARD_PLAN_PATH, index=False)
                    removed_count += original_len - len(df)
                    print(f"[INFO] Removed {original_len - len(df)} closed trades from STANDARD plan (val/)")
        
        # Remover del plan PROBWIN_55 activo (SOLO val/trade_plan_EXECUTE.csv)
        if plan_type in ["PROBWIN_55", "ALL"]:
            if TRADE_PLAN_PATH.exists():
                df = pd.read_csv(TRADE_PLAN_PATH)
                original_len = len(df)
                df = df[~df["ticker"].str.upper().isin(closed_tickers)]
                if len(df) < original_len:
                    df.to_csv(TRADE_PLAN_PATH, index=False)
                    removed_count += original_len - len(df)
                    print(f"[INFO] Removed {original_len - len(df)} closed trades from PROBWIN_55 plan (val/)")
        
        return removed_count
    except Exception as e:
        print(f"[WARNING] Error removing closed trades from plans: {e}")
        return 0

def _track_probwin_plan_to_history():
    """Trackea el plan PROBWIN_55 (EXECUTE) y genera historial cuando alcanza TP/SL."""
    try:
        if not TRADE_PLAN_PATH.exists():
            return
        
        plan_df = pd.read_csv(TRADE_PLAN_PATH)
        if plan_df.empty:
            return
        
        import yfinance as yf
        now_iso = datetime.now().isoformat()
        price_cache = {}
        closed_rows = []
        
        for _, row in plan_df.iterrows():
            ticker = str(row.get("ticker", "")).upper()
            side = str(row.get("side", "BUY")).upper()
            entry = float(row.get("entry", 0) or 0)
            tp_price = float(row.get("tp_price", 0) or 0)
            sl_price = float(row.get("sl_price", 0) or 0)
            qty = float(row.get("qty", 1) or 1)
            
            if not ticker or entry <= 0 or qty <= 0:
                continue
            
            if ticker in price_cache:
                current_price = price_cache[ticker]
            else:
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="1d", interval="1m")
                    current_price = float(hist["Close"].iloc[-1]) if not hist.empty else entry
                except Exception:
                    current_price = entry
                price_cache[ticker] = current_price
            
            hit_tp = False
            hit_sl = False
            if side == "BUY":
                hit_tp = tp_price > 0 and current_price >= tp_price
                hit_sl = sl_price > 0 and current_price <= sl_price
            else:
                hit_tp = tp_price > 0 and current_price <= tp_price
                hit_sl = sl_price > 0 and current_price >= sl_price
            
            if hit_tp or hit_sl:
                exit_reason = "TP" if hit_tp else "SL"
                exit_price = tp_price if hit_tp else sl_price
                pnl = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
                pnl_pct = ((exit_price - entry) / entry * 100) if side == "BUY" else ((entry - exit_price) / entry * 100)
                exposure = entry * qty
                closed_date = now_iso.split("T")[0]
                # ID único: ticker + side + entry + plan_type (evita duplicados)
                trade_id = f"PW55-{ticker}-{side}-{entry:.4f}".replace("/", "-")
                
                closed_rows.append({
                    "ticker": ticker,
                    "side": side,
                    "entry": entry,
                    "exit": exit_price,
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                    "qty": qty,
                    "exposure": exposure,
                    "prob_win": float(row.get("prob_win", 0) or 0),
                    "exit_reason": exit_reason,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "closed_at": now_iso,
                    "date": closed_date,
                    "trade_id": trade_id,
                    "plan_type": "PROBWIN_55"
                })
        
        if not closed_rows:
            return
        
        closed_df = pd.DataFrame(closed_rows)
        
        # IDEMPOTENCIA: Evitar duplicados en historial (por trade_id y ticker+plan_type)
        if TRADE_HISTORY_PATH.exists():
            hist_df = _read_history_csv()
            # Chequeo 1: Por trade_id exacto
            existing_hist_ids = set(hist_df.get("trade_id", pd.Series(dtype=str)).astype(str).tolist())
            closed_df = closed_df[~closed_df["trade_id"].isin(existing_hist_ids)]
            
            # Chequeo 2: Por ticker+plan_type (doble seguridad)
            if not closed_df.empty and not hist_df.empty:
                hist_df["ticker_plan_key"] = hist_df["ticker"].str.upper() + "_" + hist_df.get("plan_type", "UNKNOWN").astype(str)
                closed_df["ticker_plan_key"] = closed_df["ticker"].str.upper() + "_" + closed_df["plan_type"].astype(str)
                existing_keys = set(hist_df["ticker_plan_key"].tolist())
                closed_df = closed_df[~closed_df["ticker_plan_key"].isin(existing_keys)]
                closed_df = closed_df.drop(columns=["ticker_plan_key"])
        
        if closed_df.empty:
            print("[INFO] No new trades to close (already in history)")
            return
        
        header_needed = not TRADE_HISTORY_PATH.exists()
        closed_df.to_csv(TRADE_HISTORY_PATH, mode="a", header=header_needed, index=False)
        
        # Remover tickers cerrados del plan PROBWIN_55
        closed_tickers = set(closed_df["ticker"].str.upper().tolist())
        _remove_closed_from_plans(closed_tickers, "PROBWIN_55")
        
    except Exception as e:
        print(f"[WARNING] Error tracking PROBWIN_55 plan: {e}")

def _track_standard_plan_to_history():
    """Crea y actualiza seguimiento del plan STANDARD y genera historial cerrado (TP/SL)."""
    try:
        plan_df = _normalize_standard_plan(_load_latest_standard_plan())
        if plan_df.empty:
            return

        # Cargar tracking existente o inicializar
        if STANDARD_TRACK_PATH.exists():
            track_df = pd.read_csv(STANDARD_TRACK_PATH)
        else:
            track_df = pd.DataFrame(columns=plan_df.columns)

        existing_ids = set(track_df["trade_id"].astype(str).tolist()) if not track_df.empty else set()
        new_rows = plan_df[~plan_df["trade_id"].isin(existing_ids)]
        if not new_rows.empty:
            track_df = pd.concat([track_df, new_rows], ignore_index=True)

        if track_df.empty:
            return

        import yfinance as yf
        now_iso = datetime.now().isoformat()
        price_cache = {}
        closed_rows = []
        open_rows = []

        for _, row in track_df.iterrows():
            ticker = str(row.get("ticker", "")).upper()
            side = str(row.get("side", "BUY")).upper()
            entry = float(row.get("entry", 0) or 0)
            tp_price = float(row.get("tp_price", 0) or 0)
            sl_price = float(row.get("sl_price", 0) or 0)
            qty = float(row.get("qty", 1) or 1)

            if not ticker or entry <= 0 or qty <= 0:
                continue

            if ticker in price_cache:
                current_price = price_cache[ticker]
            else:
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="1d", interval="1m")
                    current_price = float(hist["Close"].iloc[-1]) if not hist.empty else entry
                except Exception:
                    current_price = entry
                price_cache[ticker] = current_price

            hit_tp = False
            hit_sl = False
            if side == "BUY":
                hit_tp = tp_price > 0 and current_price >= tp_price
                hit_sl = sl_price > 0 and current_price <= sl_price
            else:
                hit_tp = tp_price > 0 and current_price <= tp_price
                hit_sl = sl_price > 0 and current_price >= sl_price

            if hit_tp or hit_sl:
                exit_reason = "TP" if hit_tp else "SL"
                exit_price = tp_price if hit_tp else sl_price
                pnl = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
                pnl_pct = ((exit_price - entry) / entry * 100) if side == "BUY" else ((entry - exit_price) / entry * 100)
                exposure = entry * qty
                closed_date = now_iso.split("T")[0]
                closed_rows.append({
                    "ticker": ticker,
                    "side": side,
                    "entry": entry,
                    "exit": exit_price,
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                    "qty": qty,
                    "exposure": exposure,
                    "prob_win": float(row.get("prob_win", 0) or 0),
                    "exit_reason": exit_reason,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "closed_at": now_iso,
                    "date": closed_date,
                    "trade_id": str(row.get("trade_id", ""))
                })
            else:
                open_rows.append(row)

        # Guardar tracking actualizado
        if open_rows:
            pd.DataFrame(open_rows).to_csv(STANDARD_TRACK_PATH, index=False)
        else:
            if STANDARD_TRACK_PATH.exists():
                STANDARD_TRACK_PATH.unlink(missing_ok=True)

        if not closed_rows:
            return

        closed_df = pd.DataFrame(closed_rows)

        # Asegurar columna plan_type en el historial
        if TRADE_HISTORY_PATH.exists():
            hist_df = _read_history_csv()
            if "plan_type" not in hist_df.columns:
                hist_df["plan_type"] = "UNKNOWN"
                hist_df.to_csv(TRADE_HISTORY_PATH, index=False)

        # IDEMPOTENCIA: Evitar duplicados en historial (por trade_id y ticker+plan_type)
        if TRADE_HISTORY_PATH.exists():
            hist_df = _read_history_csv()
            # Chequeo 1: Por trade_id exacto
            existing_hist_ids = set(hist_df.get("trade_id", pd.Series(dtype=str)).astype(str).tolist())
            closed_df = closed_df[~closed_df["trade_id"].isin(existing_hist_ids)]
            
            # Chequeo 2: Por ticker+plan_type (doble seguridad)
            if not closed_df.empty and not hist_df.empty:
                hist_df["ticker_plan_key"] = hist_df["ticker"].str.upper() + "_" + hist_df.get("plan_type", "UNKNOWN").astype(str)
                closed_df["ticker_plan_key"] = closed_df["ticker"].str.upper() + "_" + closed_df.get("plan_type", "STANDARD").astype(str)
                existing_keys = set(hist_df["ticker_plan_key"].tolist())
                closed_df = closed_df[~closed_df["ticker_plan_key"].isin(existing_keys)]
                closed_df = closed_df.drop(columns=["ticker_plan_key"])

        if closed_df.empty:
            print("[INFO] No new trades to close (already in history)")
            return

        header_needed = not TRADE_HISTORY_PATH.exists()
        if "plan_type" not in closed_df.columns:
            closed_df["plan_type"] = "STANDARD"
        closed_df.to_csv(TRADE_HISTORY_PATH, mode="a", header=header_needed, index=False)

        # Remover tickers cerrados del plan STANDARD
        closed_tickers = set(closed_df["ticker"].str.upper().tolist())
        _remove_closed_from_plans(closed_tickers, "STANDARD")

    except Exception as e:
        print(f"[WARNING] Error tracking STANDARD plan: {e}")

def _read_history_csv():
    try:
        return pd.read_csv(TRADE_HISTORY_PATH)
    except Exception:
        try:
            return pd.read_csv(TRADE_HISTORY_PATH, engine="python", on_bad_lines="skip")
        except Exception as e:
            print(f"[WARNING] Error reading history CSV: {e}")
            return pd.DataFrame()

def load_history_trades():
    try:
        _track_standard_plan_to_history()
        _track_probwin_plan_to_history()  # También trackear plan PROBWIN_55
        if TRADE_HISTORY_PATH.exists():
            df = _read_history_csv()
            trades = []
            for _, row in df.iterrows():
                closed_at_str = str(row.get("closed_at", ""))
                entry_at_str = str(row.get("entry_time", row.get("opened_at", row.get("generated_at", ""))))
                try:
                    closed_dt = pd.to_datetime(closed_at_str)
                    fecha = closed_dt.strftime("%Y-%m-%d")
                    hora = closed_dt.strftime("%H:%M")
                except Exception:
                    fecha = str(row.get("date", ""))
                    hora = "N/A"

                entry_estimated = False
                if not entry_at_str or entry_at_str.lower() in ["nan", "none"]:
                    base_date = str(row.get("date", fecha))
                    entry_at_str = f"{base_date}T09:30:00"
                    entry_estimated = True

                duration_min = None
                try:
                    entry_dt = pd.to_datetime(entry_at_str)
                    closed_dt = pd.to_datetime(closed_at_str)
                    duration_min = int((closed_dt - entry_dt).total_seconds() // 60)
                except Exception:
                    duration_min = None

                trades.append({
                    "fecha": fecha,
                    "hora": hora,
                    "ticker": row.get("ticker", ""),
                    "plan_type": str(row.get("plan_type", "")).upper() or "UNKNOWN",
                    "tipo": str(row.get("side", "BUY")).upper(),
                    "entrada": float(row.get("entry", 0)),
                    "salida": float(row.get("exit", 0)),
                    "tp_price": float(row.get("tp_price", 0)),
                    "sl_price": float(row.get("sl_price", 0)),
                    "pnl": float(row.get("pnl", 0)),
                    "pnl_pct": float(row.get("pnl_pct", 0)),
                    "win_rate": float(row.get("prob_win", 50)),
                    "exit_reason": str(row.get("exit_reason", "")),
                    "qty": float(row.get("qty", 0)),
                    "closed_at": closed_at_str,
                    "trade_id": str(row.get("trade_id", "")),
                    "entry_at": entry_at_str,
                    "entry_estimated": entry_estimated,
                    "duration_min": duration_min
                })
            return trades
    except Exception as e:
        print(f"[WARNING] Error loading history: {e}")
    return []

def load_plan_comparison():
    """Carga planes STANDARD y PROBWIN_55 con cache de precios"""
    try:
        from datetime import datetime
        from pathlib import Path
        
        plans = []
        plans_dir = Path("evidence") / "weekly_plans"
        
        # Intentar cargar planes de hoy
        today = datetime.now().strftime("%Y-%m-%d")
        standard_path = plans_dir / f"plan_standard_{today}.csv"
        probwin55_path = plans_dir / f"plan_probwin55_{today}.csv"
        
        # Si no existen, buscar el archivo más reciente
        if not standard_path.exists():
            standard_files = sorted(plans_dir.glob("plan_standard_*.csv"))
            if standard_files:
                standard_path = standard_files[-1]
        
        if not probwin55_path.exists():
            probwin55_files = sorted(plans_dir.glob("plan_probwin55_*.csv"))
            if probwin55_files:
                probwin55_path = probwin55_files[-1]
        
        # Si no hay plan probwin55 en evidence, usar EXECUTE como fallback
        if not probwin55_path.exists() or (probwin55_path.exists() and pd.read_csv(probwin55_path).empty):
            execute_path = Path("val/trade_plan_EXECUTE.csv")
            if execute_path.exists():
                probwin55_path = execute_path
        
        # Recolectar todos los tickers para batch fetch
        all_tickers = []
        
        # Cargar STANDARD
        standard_data = []
        if standard_path.exists():
            df_std = pd.read_csv(standard_path)
            if not df_std.empty:
                all_tickers.extend([str(row.get("ticker", "")) for _, row in df_std.iterrows()])
        
        # Cargar PROBWIN_55
        probwin_data = []
        if probwin55_path.exists():
            df_prob = pd.read_csv(probwin55_path)
            if not df_prob.empty:
                all_tickers.extend([str(row.get("ticker", "")) for _, row in df_prob.iterrows()])
        
        # Obtener precios en batch
        prices = get_cached_prices(all_tickers) if all_tickers else {}
        
        # Procesar STANDARD
        if standard_path.exists():
            df_std = pd.read_csv(standard_path)
            if not df_std.empty:
                for _, row in df_std.iterrows():
                    entry = float(row.get("entry", 0))
                    tp = float(row.get("tp_price", 0))
                    sl = float(row.get("sl_price", 0))
                    qty = float(row.get("qty", 1))
                    exposure = abs(entry * qty) if not pd.isna(qty) else entry
                    ticker = str(row.get("ticker", ""))
                    side = str(row.get("side", "BUY")).upper()
                    
                    # Obtener precio del cache
                    current_price = prices.get(ticker, entry)
                    if current_price is None:
                        current_price = entry
                    
                    # Calcular cambio
                    change_pct = ((current_price - entry) / entry * 100) if entry > 0 else 0
                    
                    # Priorizar etth del plan
                    time_to_tp = get_time_from_plan(ticker, standard_path)
                    if time_to_tp is None and tp > 0:
                        time_to_tp = estimate_time_to_target(ticker, current_price, tp, side)
                    
                    time_to_sl = None
                    if sl > 0:
                        time_to_sl = estimate_time_to_target(ticker, current_price, sl, side)
                    
                    standard_data.append({
                        "ticker": ticker,
                        "side": side,
                        "entry": entry,
                        "current": current_price,
                        "change_pct": change_pct,
                        "tp": tp,
                        "sl": sl,
                        "prob_win": float(row.get("prob_win", 0)) * 100,
                        "exposure": exposure,
                        "time_to_tp": time_to_tp,
                        "time_to_sl": time_to_sl
                    })
        
        # Procesar PROBWIN_55
        if probwin55_path.exists():
            df_prob = pd.read_csv(probwin55_path)
            if not df_prob.empty:
                for _, row in df_prob.iterrows():
                    entry = float(row.get("entry", 0))
                    tp = float(row.get("tp_price", 0))
                    sl = float(row.get("sl_price", 0))
                    qty = float(row.get("qty", 1))
                    exposure = abs(entry * qty) if not pd.isna(qty) else entry
                    ticker = str(row.get("ticker", ""))
                    side = str(row.get("side", "BUY")).upper()
                    
                    # Obtener precio del cache
                    current_price = prices.get(ticker, entry)
                    if current_price is None:
                        current_price = entry
                    
                    # Calcular cambio
                    change_pct = ((current_price - entry) / entry * 100) if entry > 0 else 0
                    
                    # Priorizar etth del plan
                    time_to_tp = get_time_from_plan(ticker, probwin55_path)
                    if time_to_tp is None and tp > 0:
                        time_to_tp = estimate_time_to_target(ticker, current_price, tp, side)
                    
                    time_to_sl = None
                    if sl > 0:
                        time_to_sl = estimate_time_to_target(ticker, current_price, sl, side)
                    
                    probwin_data.append({
                        "ticker": ticker,
                        "side": side,
                        "entry": entry,
                    "current": current_price,
                    "change_pct": change_pct,
                    "tp": tp,
                    "sl": sl,
                    "prob_win": float(row.get("prob_win", 0)) * 100,
                    "exposure": exposure,
                    "time_to_tp": time_to_tp,
                    "time_to_sl": time_to_sl
                })
        
        # Agregar planes
        if standard_data:
            avg_prob_win = sum(p["prob_win"] for p in standard_data) / len(standard_data) if standard_data else 0
            plans.append({
                "name": "STANDARD",
                "positions": len(standard_data),
                "exposure": sum(p["exposure"] for p in standard_data),
                "prob_win_avg": avg_prob_win,
                "tickers": ", ".join(set(p["ticker"] for p in standard_data)),
                "details": standard_data
            })
        
        if probwin_data:
            avg_prob_win = sum(p["prob_win"] for p in probwin_data) / len(probwin_data) if probwin_data else 0
            plans.append({
                "name": "PROBWIN_55",
                "positions": len(probwin_data),
                "exposure": sum(p["exposure"] for p in probwin_data),
                "prob_win_avg": avg_prob_win,
                "tickers": ", ".join(set(p["ticker"] for p in probwin_data)),
                "details": probwin_data
            })
        
        # Ordenar: PROBWIN_55 primero
        plans.sort(key=lambda x: (x["name"] != "PROBWIN_55", x["name"]))
        
        return plans
    except Exception as e:
        print(f"[WARNING] Error loading plan comparison: {e}")
        import traceback
        traceback.print_exc()
        return []

def calculate_summary():
    history = load_history_trades()
    active = load_active_trades()
    
    pnl_total = sum(t["pnl"] for t in history) if history else 0
    winners = sum(1 for t in history if t["pnl"] > 0) if history else 0
    total = len(history)
    win_rate = (winners / total * 100) if total > 0 else 0
    prob_win_avg = (sum(t["prob_win"] for t in active) / len(active)) if active else 0
    exposure = sum(abs(t["entry"] * t["qty"]) for t in active) if active else 0
    
    return {
        "pnl_total": pnl_total,
        "total_trades": total,
        "win_rate": win_rate,
        "active_trades": len(active),
        "prob_win_avg": prob_win_avg,
        "exposure": exposure,
        "max_capital": get_max_capital()
    }

HTML = '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trade Dashboard</title>
    <style>
        :root {
            --primary: #1e3c72;
            --primary-light: #2a5298;
            --secondary: #0084ff;
            --success: #28a745;
            --danger: #dc3545;
            --warning: #ff9800;
            --purple: #667eea;
            --purple-dark: #764ba2;
            --text-dark: #1e3c72;
            --text-muted: #999;
            --bg-white: #ffffff;
            --bg-gray: #f5f5f5;
            --border-light: #eee;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header {
            background: var(--bg-white);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 8px 16px rgba(0,0,0,0.1);
        }
        .header h1 { color: var(--text-dark); font-size: 32px; margin-bottom: 12px; font-weight: 600; }
        .header-info { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px; }
        .header-left p { color: var(--text-muted); font-size: 13px; margin: 4px 0; }
        .status-badge {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 18px;
            border-radius: 24px;
            font-weight: 600;
            font-size: 13px;
        }
        .status-badge.success { background: #d4edda; color: #155724; }
        .status-badge.danger { background: #f8d7da; color: #721c24; }
        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        .status-dot.success { background: var(--success); }
        .status-dot.danger { background: var(--danger); }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
        .tabs {
            display: flex;
            gap: 0;
            margin-bottom: 24px;
            background: var(--bg-white);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            flex-wrap: wrap;
        }
        .tab-btn {
            flex: 1 1 200px;
            padding: 16px 20px;
            border: none;
            background: var(--bg-gray);
            cursor: pointer;
            font-size: 15px;
            font-weight: 600;
            color: #666;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            border-bottom: 3px solid transparent;
        }
        .tab-btn:hover { background: #efefef; }
        .tab-btn.active { background: var(--bg-white); color: var(--secondary); border-bottom-color: var(--secondary); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: var(--bg-white);
            padding: 20px;
            border-radius: 12px;
            border-left: 4px solid var(--secondary);
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        }
        .stat-card.profit { border-left-color: var(--success); }
        .stat-card.loss { border-left-color: var(--danger); }
        .stat-label { color: var(--text-muted); font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; }
        .stat-value { font-size: 32px; font-weight: 700; color: var(--text-dark); line-height: 1; margin-bottom: 6px; }
        .stat-value.profit { color: var(--success); }
        .stat-value.loss { color: var(--danger); }
        .stat-subtext { color: #bbb; font-size: 12px; }
        .trades-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
        .trade-card {
            background: var(--bg-white);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            border-left: 4px solid var(--secondary);
        }
        .trade-card.profit { border-left-color: var(--success); }
        .trade-card.loss { border-left-color: var(--danger); }
        .trade-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border-light);
        }
        .trade-ticker { font-size: 24px; font-weight: 700; color: var(--text-dark); }
        .trade-info { display: flex; gap: 8px; align-items: center; }
        .trade-side {
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
        }
        .trade-side.buy { background: #d4edda; color: #155724; }
        .trade-side.sell { background: #f8d7da; color: #721c24; }
        .trade-pnl { font-size: 20px; font-weight: 700; }
        .trade-pnl.profit { color: #28a745; }
        .trade-pnl.loss { color: #dc3545; }
        .trade-rows { display: flex; flex-direction: column; gap: 0; }
        .trade-row {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            font-size: 13px;
            border-bottom: 1px solid #f5f5f5;
        }
        .trade-row:last-child { border-bottom: none; }
        .trade-label { color: #999; font-weight: 600; }
        .trade-value { color: #1e3c72; font-weight: 700; }
        .trade-stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-top: 16px;
            padding-top: 12px;
            border-top: 1px solid #eee;
            text-align: center;
        }
        .trade-stat-label { color: #999; font-size: 11px; font-weight: 600; margin-bottom: 4px; }
        .trade-stat-value { color: #1e3c72; font-size: 18px; font-weight: 700; }
        .empty-state { text-align: center; padding: 60px 20px; background: white; border-radius: 12px; color: #999; }
        .empty-state h2 { color: #1e3c72; margin-bottom: 8px; font-size: 18px; }
        .table-wrapper { background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        .summary-table-wrap { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
        .summary-table-wrap table { min-width: 520px; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #f9f9f9; padding: 16px; text-align: left; font-weight: 700; color: #1e3c72; font-size: 12px; text-transform: uppercase; border-bottom: 2px solid #eee; }
        td { padding: 16px; border-bottom: 1px solid #eee; color: #666; font-size: 13px; }
        tr:hover { background: #f9f9f9; }
        tr:last-child td { border-bottom: none; }
        .pnl-positive { color: #28a745; font-weight: 700; }
        .pnl-negative { color: #dc3545; font-weight: 700; }
        .btn-refresh {
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: linear-gradient(135deg, #0084ff 0%, #005acc 100%);
            color: white;
            border: none;
            border-radius: 50%;
            width: 60px;
            height: 60px;
            font-size: 24px;
            cursor: pointer;
            box-shadow: 0 6px 16px rgba(0,132,255,0.4);
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .btn-refresh:hover { transform: scale(1.1); box-shadow: 0 8px 20px rgba(0,132,255,0.6); }
        .btn-refresh.spinning { animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        @media (max-width: 768px) {
            .tabs { border-radius: 10px; }
            .tab-btn { flex: 1 1 50%; padding: 12px 10px; font-size: 13px; }
            .summary-table-wrap table { min-width: 480px; }
        }

        @media (max-width: 480px) {
            .tabs { border-radius: 8px; }
            .tab-btn { flex: 1 1 50%; padding: 10px 8px; font-size: 11px; }
            .summary-table-wrap table { min-width: 420px; }
        }

        .report-view-btn {
            padding: 10px 18px;
            background: #f5f5f5;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            color: #333;
            transition: all 0.2s;
        }
        .report-view-btn:hover { background: #efefef; border-color: #bbb; }
        .report-view-btn.active {
            background: linear-gradient(135deg, #0084ff 0%, #005acc 100%);
            color: white;
            border-color: #005acc;
        }

        .report-card {
            background: white;
            border-radius: 14px;
            padding: 20px;
            box-shadow: 0 6px 18px rgba(0,0,0,0.10);
        }
        .report-title {
            font-size: 18px;
            font-weight: 700;
            color: #1e3c72;
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }
        .report-subtitle {
            color: #6b7280;
            font-size: 12px;
            margin-bottom: 12px;
        }
        .report-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 10px;
            border-radius: 16px;
            background: #f0f7ff;
            color: #0084ff;
            font-weight: 700;
            font-size: 11px;
        }

        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #c0c0c0; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #888; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Trade Dashboard Unificado</h1>
            <div class="header-info">
                <div class="header-left">
                    <p><strong>Actualizado:</strong> <span id="updateTime">{{ now }}</span></p>
                    <p><small>Monitoreo en tiempo real | Precios desde Yahoo Finance</small></p>
                </div>
                <div class="status-badge {{ market_status_class }}">
                    <span class="status-dot {{ market_status_class }}"></span>
                    <span>{{ market_status }} | {{ market_time }}</span>
                </div>
            </div>
        </div>
        
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab(0)"><span style="font-size: 20px;">📊</span> Trade Monitor</button>
            <button class="tab-btn" onclick="switchTab(1)"><span style="font-size: 20px;">⚖️</span> Plan Comparison</button>
            <button class="tab-btn" onclick="switchTab(2)"><span style="font-size: 20px;">📋</span> Historial</button>
            <button class="tab-btn" onclick="switchTab(3)"><span style="font-size: 20px;">📈</span> Reporte Historico</button>
        </div>
        
        <div class="tab-content active" id="tab0">
            <div class="stats-grid" id="statsGrid"></div>
            <div class="trades-grid" id="tradesGrid"></div>
        </div>
        
        <div class="tab-content" id="tab1">
            <div style="display: flex; flex-direction: column; gap: 32px;">
                <!-- Tabla resumen colapsable -->
                <div style="background: white; border-radius: 16px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.12);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; cursor: pointer;" onclick="toggleSummaryTable()">
                        <h2 style="color: #1e3c72; font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 12px; margin: 0;">
                            <span style="font-size: 28px;">📊</span>
                            Resumen de Planes
                        </h2>
                        <button id="toggleSummaryBtn" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 10px 20px; border-radius: 24px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 8px; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4); transition: all 0.3s ease;">
                            <span id="toggleIcon">▼</span>
                            <span id="toggleText">Ocultar</span>
                        </button>
                    </div>
                    <div id="summaryTableContainer" style="overflow: hidden; transition: max-height 0.4s ease, opacity 0.3s ease; max-height: 1000px; opacity: 1;">
                        <div class="summary-table-wrap">
                            <table style="width: 100%; border-collapse: separate; border-spacing: 0;">
                            <thead>
                                <tr style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white;">
                                    <th style="padding: 16px; text-align: left; font-weight: 600; border-radius: 8px 0 0 0;">Plan</th>
                                    <th style="padding: 16px; text-align: center; font-weight: 600;">Posiciones</th>
                                    <th style="padding: 16px; text-align: center; font-weight: 600;">Exposición</th>
                                    <th style="padding: 16px; text-align: center; font-weight: 600; border-radius: 0 8px 0 0;">Prob Win Avg</th>
                                </tr>
                            </thead>
                            <tbody id="comparisonTable">
                                <tr><td colspan="4" style="text-align: center; padding: 40px; color: #999;">Sin datos disponibles</td></tr>
                            </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                
                <!-- Detalles de posiciones mejorado -->
                <div id="comparisonDetails"></div>
            </div>
        </div>
        
        <div class="tab-content" id="tab2">
            <div class="trades-grid" id="historyGrid"></div>
        </div>

        <div class="tab-content" id="tab3">
            <div id="reportContent" style="display: none;">
                <div style="display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap;">
                    <button class="report-view-btn active" onclick="switchReportView('grouped')">Agrupado por Fecha</button>
                    <button class="report-view-btn" onclick="switchReportView('detailed')">Detalles y Duración</button>
                    <button class="report-view-btn" onclick="switchReportView('timeline')">Timeline Visual</button>
                    <button class="report-view-btn" onclick="switchReportView('plan')">Comparativa por Plan</button>
                </div>
                <div id="reportGrouped" style="display: block;"></div>
                <div id="reportDetailed" style="display: none;"></div>
                <div id="reportTimeline" style="display: none;"></div>
                <div id="reportPlan" style="display: none;"></div>
            </div>
            <div id="reportEmpty" style="text-align: center; padding: 40px;">
                <h3 style="color: #999;">Cargando reporte...</h3>
            </div>
        </div>
    </div>
    
    <button class="btn-refresh" id="refreshBtn" onclick="refreshDashboard()">↻</button>
    
    <script>
        const API = window.location.origin + '/api';
        const PRICE_DECIMALS = 2;
        
        // Formato financiero consistente
        const formatCurrency = (value) => {
            return new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value);
        };
        
        const formatPercent = (value) => {
            return new Intl.NumberFormat('en-US', {
                style: 'percent',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value / 100);
        };
        
        function switchTab(i) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab' + i).classList.add('active');
            document.querySelectorAll('.tab-btn')[i].classList.add('active');
            if (i === 0) loadTradeMonitor();
            else if (i === 1) loadComparison();
            else if (i === 2) loadHistory();
            else if (i === 3) loadHistoryReport();
        }
        
        function loadTradeMonitor() {
            fetch(API + '/trades').then(r => r.json()).then(data => {
                const s = data.summary;
                document.getElementById('statsGrid').innerHTML = `
                    <div class="stat-card ${s.pnl_total >= 0 ? 'profit' : 'loss'}">
                        <div class="stat-label">P&L TOTAL</div>
                        <div class="stat-value ${s.pnl_total >= 0 ? 'profit' : 'loss'}">${formatCurrency(s.pnl_total)}</div>
                        <div class="stat-subtext">${s.total_trades} trades cerrados</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">EXPOSICIÓN</div>
                        <div class="stat-value">${formatCurrency(s.exposure)}</div>
                        <div class="stat-subtext">de ${formatCurrency(s.max_capital)} cap</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">TRADES ACTIVOS</div>
                        <div class="stat-value">${s.active_trades}</div>
                        <div class="stat-subtext">posiciones abiertas</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">PROB. WIN</div>
                        <div class="stat-value">${s.prob_win_avg.toFixed(2)}%</div>
                        <div class="stat-subtext">promedio</div>
                    </div>
                `;
                
                if (!data.trades || data.trades.length === 0) {
                    document.getElementById('tradesGrid').innerHTML = '<div class="empty-state" style="grid-column: 1/-1;"><h2>No hay trades activos</h2></div>';
                    return;
                }
                
                document.getElementById('tradesGrid').innerHTML = data.trades.map(t => `
                    <div class="trade-card ${t.pnl > 0 ? 'profit' : 'loss'}">
                        <div class="trade-header">
                            <div class="trade-ticker">${t.ticker}</div>
                            <div class="trade-info">
                                <span class="trade-side ${t.side.toLowerCase()}">${t.side}</span>
                                <div class="trade-pnl ${t.pnl > 0 ? 'profit' : 'loss'}">${formatCurrency(t.pnl)}</div>
                            </div>
                        </div>
                        
                        <!-- Precio Actual destacado (fondo sólido) -->
                        <div style="background: #667eea; border-radius: 8px; padding: 12px; margin: 12px 0; text-align: center; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);">
                            <div style="color: rgba(255,255,255,0.8); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">Precio Actual</div>
                            <div style="color: white; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">${formatCurrency(t.exit)}</div>
                            <div style="color: rgba(255,255,255,0.9); font-size: 12px; font-weight: 600; margin-top: 4px;">
                                ${t.pnl >= 0 ? '▲' : '▼'} ${formatPercent((t.pnl / t.entry) * 100)}
                            </div>
                        </div>
                        
                        <div class="trade-rows">
                            <div class="trade-row"><span class="trade-label">Entry</span><span class="trade-value">${formatCurrency(t.entry)}</span></div>
                            <div class="trade-row"><span class="trade-label">Target (TP)</span><span class="trade-value" style="color: #28a745;">${formatCurrency(t.tp)} <small style="color: #999;">(${formatPercent(((t.tp - t.entry) / t.entry) * 100)})</small></span></div>
                            <div class="trade-row"><span class="trade-label">Stop (SL)</span><span class="trade-value" style="color: #dc3545;">${formatCurrency(t.sl)} <small style="color: #999;">(${formatPercent(((t.sl - t.entry) / t.entry) * 100)})</small></span></div>
                        </div>
                        
                        <!-- Tiempo estimado -->
                        <div style="background: linear-gradient(135deg, #fff5e6 0%, #fffbf0 100%); border-radius: 8px; padding: 12px; margin: 12px 0; border-left: 4px solid #ff9800;">
                            <div style="font-size: 11px; color: #666; font-weight: 600; text-transform: uppercase; margin-bottom: 8px;">⏱️ Tiempo Estimado</div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                                <div style="text-align: center;">
                                    <div style="font-size: 10px; color: #28a745; font-weight: 600;">Hasta TP</div>
                                    <div style="font-size: 16px; font-weight: 700; color: #28a745;">${t.time_to_tp ? t.time_to_tp + ' min' : 'N/A'}</div>
                                </div>
                                <div style="text-align: center;">
                                    <div style="font-size: 10px; color: #dc3545; font-weight: 600;">Hasta SL</div>
                                    <div style="font-size: 16px; font-weight: 700; color: #dc3545;">${t.time_to_sl ? t.time_to_sl + ' min' : 'N/A'}</div>
                                </div>
                            </div>
                        </div>
                        <div class="trade-stats">
                            <div><div class="trade-stat-label">Qty</div><div class="trade-stat-value">${t.qty}</div></div>
                            <div><div class="trade-stat-label">Prob Win</div><div class="trade-stat-value">${t.prob_win.toFixed(1)}%</div></div>
                            <div><div class="trade-stat-label">P&L</div><div class="trade-stat-value" style="font-size: 13px; color: ${t.pnl >= 0 ? '#28a745' : '#dc3545'};">$${t.pnl.toFixed(2)}</div></div>
                        </div>
                    </div>
                `).join('');
            }).catch(e => console.error(e));
        }
        
        function loadComparison() {
            fetch(API + '/comparison').then(r => r.json()).then(data => {
                if (!data || data.length === 0) {
                    document.getElementById('comparisonTable').innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 40px; color: #999;">Sin datos de comparación</td></tr>';
                    document.getElementById('comparisonDetails').innerHTML = '';
                    return;
                }
                
                // Tabla resumen con mejor diseño
                document.getElementById('comparisonTable').innerHTML = data.map((plan, idx) => `
                    <tr style="background: ${plan.name === 'PROBWIN_55' ? 'linear-gradient(135deg, #e3f2fd 0%, #f8f9fa 100%)' : 'white'}; border-bottom: 1px solid #eee;">
                        <td style="padding: 20px;">
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="font-size: 24px;">${plan.name === 'STANDARD' ? '📋' : '⭐'}</span>
                                <div>
                                    <div style="font-weight: 700; color: #1e3c72; font-size: 16px;">${plan.name}</div>
                                    ${plan.name === 'PROBWIN_55' ? '<div style="font-size: 11px; color: #0084ff; font-weight: 600; margin-top: 4px;">✓ Recomendado</div>' : ''}
                                </div>
                            </div>
                        </td>
                        <td style="padding: 20px; text-align: center;">
                            <div style="display: inline-block; padding: 8px 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 20px; font-weight: 700; font-size: 16px; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);">
                                ${plan.positions}
                            </div>
                        </td>
                        <td style="padding: 20px; text-align: center; font-size: 16px; font-weight: 700; color: #1e3c72;">
                            $${plan.exposure.toFixed(2)}
                        </td>
                        <td style="padding: 20px; text-align: center;">
                            <div style="display: inline-block; padding: 10px 20px; border-radius: 24px; font-weight: 700; font-size: 15px; background: ${plan.prob_win_avg >= 55 ? 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)' : plan.prob_win_avg >= 50 ? 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)' : 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)'}; color: white; box-shadow: 0 4px 12px ${plan.prob_win_avg >= 55 ? 'rgba(17, 153, 142, 0.4)' : plan.prob_win_avg >= 50 ? 'rgba(245, 87, 108, 0.4)' : 'rgba(250, 112, 154, 0.4)'};">
                                ${plan.prob_win_avg.toFixed(1)}%
                            </div>
                        </td>
                    </tr>
                `).join('');
                
                // Detalle de posiciones con diseño premium
                document.getElementById('comparisonDetails').innerHTML = data.map(plan => `
                    <div style="background: white; border-radius: 16px; padding: 28px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); border: ${plan.name === 'PROBWIN_55' ? '2px solid #0084ff' : '2px solid transparent'};">
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 3px solid ${plan.name === 'PROBWIN_55' ? '#0084ff' : '#1e3c72'};">
                            <h3 style="color: #1e3c72; font-size: 22px; font-weight: 700; display: flex; align-items: center; gap: 12px; margin: 0;">
                                <span style="font-size: 32px;">${plan.name === 'STANDARD' ? '📋' : '⭐'}</span>
                                ${plan.name}
                            </h3>
                            ${plan.name === 'PROBWIN_55' ? '<div style="padding: 8px 20px; background: linear-gradient(135deg, #0084ff 0%, #00a8ff 100%); color: white; border-radius: 24px; font-size: 13px; font-weight: 700; box-shadow: 0 4px 12px rgba(0, 132, 255, 0.4);">✓ RECOMENDADO</div>' : '<div style="padding: 8px 20px; background: #f8f9fa; color: #666; border-radius: 24px; font-size: 13px; font-weight: 600;">Alternativo</div>'}
                        </div>
                        ${plan.details && plan.details.length > 0 ? `
                            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 20px;">
                                ${plan.details.map(pos => `
                                    <div style="background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%); border-radius: 12px; padding: 20px; border: 2px solid ${pos.side === 'BUY' ? '#28a745' : '#dc3545'}; box-shadow: 0 6px 20px rgba(0,0,0,0.08); position: relative; overflow: hidden;">
                                        <div style="position: absolute; top: 0; right: 0; width: 100px; height: 100px; background: ${pos.side === 'BUY' ? 'linear-gradient(135deg, rgba(40, 167, 69, 0.1) 0%, transparent 100%)' : 'linear-gradient(135deg, rgba(220, 53, 69, 0.1) 0%, transparent 100%)'}; border-radius: 0 0 0 100px;"></div>
                                        
                                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; position: relative; z-index: 1;">
                                            <div style="font-size: 24px; font-weight: 800; color: #1e3c72; letter-spacing: -0.5px;">${pos.ticker}</div>
                                            <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
                                                <span style="padding: 6px 12px; border-radius: 8px; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; background: ${pos.side === 'BUY' ? 'linear-gradient(135deg, #28a745 0%, #20c997 100%)' : 'linear-gradient(135deg, #dc3545 0%, #ff6b6b 100%)'}; color: white; box-shadow: 0 4px 12px ${pos.side === 'BUY' ? 'rgba(40, 167, 69, 0.3)' : 'rgba(220, 53, 69, 0.3)'};">${pos.side}</span>
                                                <span style="padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 700; background: ${pos.prob_win >= 55 ? 'linear-gradient(135deg, #28a745 0%, #20c997 100%)' : pos.prob_win >= 50 ? 'linear-gradient(135deg, #ffc107 0%, #ff9800 100%)' : 'linear-gradient(135deg, #dc3545 0%, #ff6b6b 100%)'}; color: white;">Win ${pos.prob_win.toFixed(1)}%</span>
                                            </div>
                                        </div>
                                        
                                        <div style="background: white; border-radius: 8px; padding: 14px; margin-bottom: 12px; box-shadow: inset 0 2px 8px rgba(0,0,0,0.05);">
                                            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; font-size: 13px;">
                                                <div style="display: flex; flex-direction: column;">
                                                    <span style="color: #999; font-weight: 600; font-size: 11px; text-transform: uppercase; margin-bottom: 4px;">Entry</span>
                                                    <span style="color: #1e3c72; font-weight: 800; font-size: 16px;">$${pos.entry.toFixed(2)}</span>
                                                </div>
                                                <div style="display: flex; flex-direction: column;">
                                                    <span style="color: #999; font-weight: 600; font-size: 11px; text-transform: uppercase; margin-bottom: 4px;">Current</span>
                                                    <span style="color: ${pos.change_pct >= 0 ? '#28a745' : '#dc3545'}; font-weight: 800; font-size: 16px;">$${pos.current.toFixed(2)}</span>
                                                    <span style="color: ${pos.change_pct >= 0 ? '#28a745' : '#dc3545'}; font-weight: 700; font-size: 11px;">${pos.change_pct >= 0 ? '+' : ''}${pos.change_pct.toFixed(2)}%</span>
                                                </div>
                                                <div style="display: flex; flex-direction: column; align-items: flex-end;">
                                                    <span style="color: #999; font-weight: 600; font-size: 11px; text-transform: uppercase; margin-bottom: 4px;">Exposure</span>
                                                    <span style="color: #667eea; font-weight: 800; font-size: 16px;">$${pos.exposure.toFixed(2)}</span>
                                                </div>
                                            </div>
                                        </div>
                                        
                                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                                            <div style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); border-radius: 8px; padding: 12px; border-left: 4px solid #28a745;">
                                                <div style="color: #155724; font-weight: 600; font-size: 11px; text-transform: uppercase; margin-bottom: 4px;">TP</div>
                                                <div style="color: #28a745; font-weight: 800; font-size: 16px;">$${pos.tp.toFixed(2)}</div>
                                                <div style="color: #28a745; font-weight: 600; font-size: 11px;">+${((pos.tp - pos.entry) / pos.entry * 100).toFixed(2)}%</div>
                                                ${pos.time_to_tp ? `<div style="color: #28a745; font-weight: 600; font-size: 10px; margin-top: 6px; border-top: 1px solid rgba(40, 167, 69, 0.3); padding-top: 6px;">⏱️ ${pos.time_to_tp} min</div>` : ''}
                                            </div>
                                            <div style="background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%); border-radius: 8px; padding: 12px; border-left: 4px solid #dc3545;">
                                                <div style="color: #721c24; font-weight: 600; font-size: 11px; text-transform: uppercase; margin-bottom: 4px;">SL</div>
                                                <div style="color: #dc3545; font-weight: 800; font-size: 16px;">$${pos.sl.toFixed(2)}</div>
                                                <div style="color: #dc3545; font-weight: 600; font-size: 11px;">${((pos.sl - pos.entry) / pos.entry * 100).toFixed(2)}%</div>
                                                ${pos.time_to_sl ? `<div style="color: #dc3545; font-weight: 600; font-size: 10px; margin-top: 6px; border-top: 1px solid rgba(220, 53, 69, 0.3); padding-top: 6px;">⏱️ ${pos.time_to_sl} min</div>` : ''}
                                            </div>
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                        ` : `
                            <div style="text-align: center; padding: 60px 20px; background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 12px; border: 2px dashed #dee2e6;">
                                <div style="font-size: 48px; margin-bottom: 16px; opacity: 0.5;">📭</div>
                                <p style="font-size: 18px; color: #6c757d; font-weight: 600; margin: 0;">Sin posiciones en este plan</p>
                            </div>
                        `}
                    </div>
                `).join('');
                
            }).catch(err => console.error('Error loading comparison:', err));
        }
        
        function loadHistory() {
            fetch(API + '/history').then(r => r.json()).then(data => {
                if (!data || data.length === 0) {
                    document.getElementById('historyGrid').innerHTML = '<div class="empty-state" style="grid-column: 1/-1;"><h2>Sin historial de trades</h2></div>';
                    return;
                }
                document.getElementById('historyGrid').innerHTML = data.map(t => `
                    <div class="trade-card ${t.pnl > 0 ? 'profit' : 'loss'}">
                        <div class="trade-header">
                            <div class="trade-ticker">${t.ticker}</div>
                            <div class="trade-info">
                                <span class="trade-side ${t.tipo.toLowerCase()}">${t.tipo}</span>
                                <div class="trade-pnl ${t.pnl > 0 ? 'profit' : 'loss'}">$${t.pnl.toFixed(2)}</div>
                            </div>
                        </div>
                        <div class="trade-rows">
                            <div class="trade-row"><span class="trade-label">Fecha</span><span class="trade-value">${t.fecha}</span></div>
                            <div class="trade-row"><span class="trade-label">Hora Cierre (${t.exit_reason})</span><span class="trade-value" style="font-weight: 600; color: ${t.exit_reason === 'TP' ? '#28a745' : t.exit_reason === 'SL' ? '#dc3545' : '#ff9800'};">${t.hora}</span></div>
                            <div class="trade-row"><span class="trade-label">Entry</span><span class="trade-value">$${t.entrada.toFixed(2)}</span></div>
                            <div class="trade-row"><span class="trade-label">Exit</span><span class="trade-value">$${t.salida.toFixed(2)}</span></div>
                            <div class="trade-row"><span class="trade-label">Status</span><span class="trade-value" style="color: ${t.pnl > 0 ? '#28a745' : '#dc3545'};">${t.pnl > 0 ? 'GANANCIA' : 'PÉRDIDA'}</span></div>
                        </div>
                        <div class="trade-stats">
                            <div><div class="trade-stat-label">P&L</div><div class="trade-stat-value" style="color: ${t.pnl > 0 ? '#28a745' : '#dc3545'};">$${t.pnl.toFixed(2)}</div></div>
                            <div><div class="trade-stat-label">Win Rate</div><div class="trade-stat-value">${t.win_rate.toFixed(1)}%</div></div>
                            <div><div class="trade-stat-label">Retorno</div><div class="trade-stat-value" style="font-size: 13px;">${((t.pnl / t.entrada) * 100).toFixed(1)}%</div></div>
                        </div>
                    </div>
                `).join('');
            }).catch(e => console.error(e));
        }

        function switchReportView(view) {
            document.querySelectorAll('.report-view-btn').forEach(b => b.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('reportGrouped').style.display = 'none';
            document.getElementById('reportDetailed').style.display = 'none';
            document.getElementById('reportTimeline').style.display = 'none';
            document.getElementById('reportPlan').style.display = 'none';
            if (view === 'grouped') document.getElementById('reportGrouped').style.display = 'block';
            else if (view === 'detailed') document.getElementById('reportDetailed').style.display = 'block';
            else if (view === 'timeline') document.getElementById('reportTimeline').style.display = 'block';
            else if (view === 'plan') document.getElementById('reportPlan').style.display = 'block';
        }

        function loadHistoryReport() {
            fetch(API + '/history').then(r => r.json()).then(data => {
                if (!data || data.length === 0) {
                    document.getElementById('reportContent').style.display = 'none';
                    document.getElementById('reportEmpty').innerHTML = '<h3 style="color: #999;">Sin historial de trades</h3>';
                    return;
                }
                document.getElementById('reportEmpty').style.display = 'none';
                document.getElementById('reportContent').style.display = 'block';
                renderGroupedView(data);
                renderDetailedView(data);
                renderTimelineView(data);
                renderPlanComparisonView(data);
            }).catch(e => console.error(e));
        }

        function renderGroupedView(data) {
            const grouped = {};
            data.forEach(t => {
                if (!grouped[t.fecha]) grouped[t.fecha] = [];
                grouped[t.fecha].push(t);
            });

            let html = '';
            Object.keys(grouped).sort().reverse().forEach(fecha => {
                const trades = grouped[fecha];
                const dayPnL = trades.reduce((s, t) => s + t.pnl, 0);
                const dayWins = trades.filter(t => t.pnl > 0).length;
                const dayTotal = trades.length;
                const dayAvg = dayPnL / dayTotal;

                html += `
                <div style="margin-bottom: 32px; background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden;">
                    <div style="background: linear-gradient(135deg, ${dayPnL > 0 ? '#f0fdf4' : '#fef2f2'} 0%, white 100%); padding: 20px; border-left: 4px solid ${dayPnL > 0 ? '#28a745' : '#dc3545'};">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px; margin-bottom: 12px;">
                            <div>
                                <div style="font-size: 18px; font-weight: 700; color: #1e3c72; margin-bottom: 8px;">📅 ${fecha}</div>
                                <div style="display: flex; gap: 20px; font-size: 12px; flex-wrap: wrap;">
                                    <div><span style="color: #666;">Total:</span> <span style="font-weight: 600; color: #333;">${dayTotal}</span></div>
                                    <div><span style="color: #666;">Ganancias:</span> <span style="font-weight: 600; color: #28a745;">${dayWins} ✓</span></div>
                                    <div><span style="color: #666;">Pérdidas:</span> <span style="font-weight: 600; color: #dc3545;">${dayTotal - dayWins} ✗</span></div>
                                </div>
                            </div>
                            <div style="text-align: right;">
                                <div style="font-size: 11px; color: #666; margin-bottom: 4px; text-transform: uppercase;">Resultado</div>
                                <div style="font-size: 28px; font-weight: 700; color: ${dayPnL > 0 ? '#28a745' : '#dc3545'};">
                                    ${dayPnL > 0 ? '+' : ''}$${dayPnL.toFixed(2)}
                                </div>
                                <div style="font-size: 12px; color: #666; margin-top: 4px;">Promedio: $${dayAvg.toFixed(2)}</div>
                            </div>
                        </div>
                    </div>

                    <div style="padding: 16px; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px;">
                        ${trades.map(t => `
                            <div class="trade-card ${t.pnl > 0 ? 'profit' : 'loss'}" style="border-left: 4px solid ${t.pnl > 0 ? '#28a745' : '#dc3545'}; background: white;">
                                <div class="trade-header" style="padding: 12px; border-bottom: 1px solid #f0f0f0;">
                                    <div class="trade-ticker" style="font-size: 16px; font-weight: 700; margin-bottom: 6px;">${t.ticker}</div>
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <span class="trade-side ${t.tipo.toLowerCase()}" style="font-size: 12px; font-weight: 600;">${t.tipo}</span>
                                        <span style="font-size: 12px; color: ${t.pnl > 0 ? '#28a745' : '#dc3545'}; font-weight: 600;">${t.exit_reason}</span>
                                    </div>
                                </div>
                                <div style="padding: 12px;">
                                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px;">
                                        <div>
                                            <div style="font-size: 11px; color: #666;">Entry</div>
                                            <div style="font-size: 14px; font-weight: 600;">$${t.entrada.toFixed(2)}</div>
                                        </div>
                                        <div>
                                            <div style="font-size: 11px; color: #666;">Exit</div>
                                            <div style="font-size: 14px; font-weight: 600;">$${t.salida.toFixed(2)}</div>
                                        </div>
                                    </div>
                                    <div style="background: ${t.pnl > 0 ? '#f0fdf4' : '#fef2f2'}; padding: 10px; border-radius: 6px; text-align: center; border: 1px solid ${t.pnl > 0 ? '#dcfce7' : '#fee2e2'};">
                                        <div style="font-size: 11px; color: #666; margin-bottom: 4px;">P&L</div>
                                        <div style="font-size: 18px; font-weight: 700; color: ${t.pnl > 0 ? '#28a745' : '#dc3545'};">${t.pnl > 0 ? '+' : ''}$${t.pnl.toFixed(2)}</div>
                                        <div style="font-size: 11px; color: #666; margin-top: 4px;">${t.pnl_pct > 0 ? '+' : ''}${t.pnl_pct.toFixed(2)}%</div>
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
                `;
            });
            document.getElementById('reportGrouped').innerHTML = html;
        }

        function renderDetailedView(data) {
            let html = '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px;">';
            data.slice().reverse().forEach(t => {
                const priceDiff = (t.salida - t.entrada);
                const priceDiffPct = ((priceDiff / t.entrada) * 100);
                const exposureReal = (t.qty * t.entrada).toFixed(2);
                const profitPerUnit = (t.qty ? (priceDiff / t.qty) : 0).toFixed(4);

                html += `
                <div class="trade-card ${t.pnl > 0 ? 'profit' : 'loss'}" style="background: white; border-left: 4px solid ${t.pnl > 0 ? '#28a745' : '#dc3545'}; border-radius: 12px;">
                    <div class="trade-header" style="padding: 16px 16px 12px 16px; border-bottom: 2px solid #f0f0f0;">
                        <div class="trade-ticker" style="font-size: 20px; font-weight: bold; margin-bottom: 8px;">${t.ticker} ${t.tipo}</div>
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                            <div style="font-size: 11px; color: #666; background: #f5f5f5; padding: 4px 8px; border-radius: 4px;">📅 ${t.fecha}</div>
                            <div style="font-size: 13px; font-weight: 600; color: ${t.pnl > 0 ? '#28a745' : '#dc3545'};">🕐 Cierre: ${t.hora}</div>
                            <div style="font-size: 13px; font-weight: 600; color: #0084ff; background: #f0f7ff; padding: 4px 8px; border-radius: 4px;">⚡ ${t.exit_reason}</div>
                        </div>
                        <div style="margin-top: 8px; font-size: 11px; color: #999; font-style: italic;">${t.entry_estimated ? '* Hora de entrada estimada (plan generado)' : '* Hora de entrada registrada'}</div>
                    </div>

                    <div style="padding: 16px;">
                        <div style="background: #f9f9f9; padding: 12px; border-radius: 8px; margin-bottom: 16px;">
                            <div style="font-size: 11px; color: #888; font-weight: 600; margin-bottom: 8px; text-transform: uppercase;">MOVIMIENTO DEL PRECIO</div>
                            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;">
                                <div>
                                    <div style="font-size: 11px; color: #666;">Entrada</div>
                                    <div style="font-size: 14px; font-weight: 600;">$${t.entrada.toFixed(PRICE_DECIMALS)}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">Salida</div>
                                    <div style="font-size: 14px; font-weight: 600;">$${t.salida.toFixed(PRICE_DECIMALS)}</div>
                                </div>
                                <div style="grid-column: 1/-1;">
                                    <div style="font-size: 11px; color: #666; margin-bottom: 4px;">Diferencia por acción</div>
                                    <div style="font-size: 13px; font-weight: 600; color: ${priceDiff > 0 ? '#28a745' : '#dc3545'};">
                                        ${priceDiff > 0 ? '+' : ''}$${priceDiff.toFixed(PRICE_DECIMALS)} (${priceDiffPct > 0 ? '+' : ''}${priceDiffPct.toFixed(2)}%)
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div style="background: #f9f9f9; padding: 12px; border-radius: 8px; margin-bottom: 16px;">
                            <div style="font-size: 11px; color: #888; font-weight: 600; margin-bottom: 8px; text-transform: uppercase;">POSICIÓN</div>
                            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;">
                                <div>
                                    <div style="font-size: 11px; color: #666;">Hora entrada</div>
                                    <div style="font-size: 13px; font-weight: 600;">${t.entry_at ? t.entry_at.replace('T', ' ') : 'N/A'}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">Duración</div>
                                    <div style="font-size: 13px; font-weight: 600;">${t.duration_min !== null ? t.duration_min + ' min' : 'N/A'}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">Cantidad</div>
                                    <div style="font-size: 14px; font-weight: 600;">${t.qty} acc.</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">P&L por acc</div>
                                    <div style="font-size: 13px; font-weight: 600; color: ${profitPerUnit > 0 ? '#28a745' : '#dc3545'};">$${profitPerUnit}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">Exposición</div>
                                    <div style="font-size: 14px; font-weight: 600;">$${exposureReal}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">TP / SL</div>
                                    <div style="font-size: 13px;">
                                        <div style="color: #28a745; font-weight: 600;">↑ $${t.tp_price.toFixed(2)}</div>
                                        <div style="color: #dc3545; font-weight: 600;">↓ $${t.sl_price.toFixed(2)}</div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div style="background: ${t.pnl > 0 ? '#f0fdf4' : '#fef2f2'}; padding: 12px; border-radius: 8px; border: 1px solid ${t.pnl > 0 ? '#dcfce7' : '#fee2e2'}; margin-bottom: 16px;">
                            <div style="font-size: 11px; color: #888; font-weight: 600; margin-bottom: 8px; text-transform: uppercase;">RESULTADO FINAL</div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                                <div>
                                    <div style="font-size: 11px; color: #666;">P&L Total</div>
                                    <div style="font-size: 18px; font-weight: 700; color: ${t.pnl > 0 ? '#28a745' : '#dc3545'};">${t.pnl > 0 ? '+' : ''}$${t.pnl.toFixed(2)}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #666;">Retorno %</div>
                                    <div style="font-size: 18px; font-weight: 700; color: ${t.pnl_pct > 0 ? '#28a745' : '#dc3545'};">${t.pnl_pct > 0 ? '+' : ''}${t.pnl_pct.toFixed(2)}%</div>
                                </div>
                            </div>
                        </div>

                        <div style="padding-top: 12px; border-top: 2px solid #f0f0f0;">
                            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; font-size: 12px;">
                                <div>
                                    <div style="color: #666; margin-bottom: 4px;">Win Probability</div>
                                    <div style="font-weight: 600; color: #0084ff;">${t.win_rate.toFixed(1)}%</div>
                                </div>
                                <div>
                                    <div style="color: #666; margin-bottom: 4px;">ID</div>
                                    <div style="font-weight: 500; color: #888; font-size: 11px; word-break: break-all;">${t.trade_id}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                `;
            });
            html += '</div>';
            document.getElementById('reportDetailed').innerHTML = html;
        }

        function renderTimelineView(data) {
            const byMonth = {};
            data.forEach(t => {
                const month = t.fecha.substring(0, 7);
                if (!byMonth[month]) byMonth[month] = [];
                byMonth[month].push(t);
            });

            let html = '<div style="padding: 16px 0;">';
            Object.keys(byMonth).sort().reverse().forEach(month => {
                const trades = byMonth[month];
                const monthPnL = trades.reduce((s, t) => s + t.pnl, 0);
                const monthWins = trades.filter(t => t.pnl > 0).length;

                html += `
                <div style="margin-bottom: 32px; background: white; padding: 24px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                        <div style="font-size: 16px; font-weight: 700; color: #1e3c72;">${month}</div>
                        <div style="font-size: 14px; font-weight: 700; color: ${monthPnL > 0 ? '#28a745' : '#dc3545'};">${monthPnL > 0 ? '+' : ''}$${monthPnL.toFixed(2)}</div>
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px;">
                        ${trades.map((t, i) => `
                            <div title="${t.ticker} ${t.tipo} | ${t.fecha} ${t.hora} | P&L: $${t.pnl.toFixed(2)}" style="display: inline-flex; width: 22px; height: 22px; border-radius: 50%; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; color: white; background: ${t.pnl > 0 ? '#28a745' : '#dc3545'}; border: 2px solid white; box-shadow: 0 0 0 1px #ddd;">
                                ${i + 1}
                            </div>
                        `).join('')}
                    </div>
                    <div style="font-size: 12px; color: #666;">
                        ${monthWins} ganancias de ${trades.length} trades | Win Rate: ${((monthWins / trades.length) * 100).toFixed(1)}%
                    </div>
                </div>
                `;
            });
            html += '</div>';
            document.getElementById('reportTimeline').innerHTML = html;
        }

        function renderPlanComparisonView(data) {
            const byPlan = {};
            data.forEach(t => {
                const plan = (t.plan_type || 'UNKNOWN').toUpperCase();
                if (!byPlan[plan]) byPlan[plan] = [];
                byPlan[plan].push(t);
            });

            const plans = Object.keys(byPlan).sort((a, b) => (a === 'STANDARD' ? -1 : b === 'STANDARD' ? 1 : a.localeCompare(b)));

            if (plans.length === 0) {
                document.getElementById('reportPlan').innerHTML = '<div class="empty-state"><h2>Sin datos de planes</h2></div>';
                return;
            }

            let summaryHtml = '<div class="report-card" style="margin-bottom: 16px; background: linear-gradient(135deg, #f8fbff 0%, #ffffff 100%); border: 1px solid #e6f0ff;">' +
                '<div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">' +
                '<div>' +
                '<div class="report-title">📈 Comparativa Histórica por Plan</div>' +
                '<div class="report-subtitle">Seguimiento del rendimiento de cada plan con histórico de cierres TP/SL.</div>' +
                '</div>' +
                '<div class="report-badge">STANDARD tracking activo</div>' +
                '</div>' +
                '</div>' +
                '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">';
            plans.forEach(plan => {
                const trades = byPlan[plan];
                const total = trades.length;
                const pnlTotal = trades.reduce((s, t) => s + t.pnl, 0);
                const wins = trades.filter(t => t.pnl > 0).length;
                const winRate = total > 0 ? (wins / total * 100) : 0;
                const avgPnl = total > 0 ? (pnlTotal / total) : 0;
                const avgRet = total > 0 ? (trades.reduce((s, t) => s + (t.pnl_pct || 0), 0) / total) : 0;

                summaryHtml += `
                <div class="report-card" style="border-left: 4px solid ${plan === 'STANDARD' ? '#0084ff' : '#1e3c72'};">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="font-size: 18px; font-weight: 700; color: #1e3c72;">${plan}</div>
                        <div style="font-size: 12px; color: #666;">${total} trades</div>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                        <div>
                            <div style="font-size: 11px; color: #888;">P&L Total</div>
                            <div style="font-size: 18px; font-weight: 700; color: ${pnlTotal >= 0 ? '#28a745' : '#dc3545'};">${pnlTotal >= 0 ? '+' : ''}$${pnlTotal.toFixed(2)}</div>
                        </div>
                        <div>
                            <div style="font-size: 11px; color: #888;">Win Rate</div>
                            <div style="font-size: 18px; font-weight: 700; color: #1e3c72;">${winRate.toFixed(1)}%</div>
                        </div>
                        <div>
                            <div style="font-size: 11px; color: #888;">Promedio P&L</div>
                            <div style="font-size: 16px; font-weight: 700; color: ${avgPnl >= 0 ? '#28a745' : '#dc3545'};">${avgPnl >= 0 ? '+' : ''}$${avgPnl.toFixed(2)}</div>
                        </div>
                        <div>
                            <div style="font-size: 11px; color: #888;">Retorno Prom.</div>
                            <div style="font-size: 16px; font-weight: 700; color: ${avgRet >= 0 ? '#28a745' : '#dc3545'};">${avgRet >= 0 ? '+' : ''}${avgRet.toFixed(2)}%</div>
                        </div>
                    </div>
                </div>
                `;
            });
            summaryHtml += '</div>';

            let detailHtml = '<div class="report-card" style="margin-top: 12px;">' +
                '<div class="report-title">🧾 Últimos movimientos por plan</div>' +
                '<div class="report-subtitle">Muestra los últimos 6 cierres por cada plan.</div>' +
                '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px;">';
            plans.forEach(plan => {
                const trades = byPlan[plan];
                detailHtml += `
                <div style="background: #fff; border-radius: 12px; padding: 16px; border: 1px solid #eef2f7;">
                    <div style="font-weight: 700; color: #1e3c72; margin-bottom: 8px;">${plan} - Últimos 6 trades</div>
                    ${trades.slice(-6).reverse().map(t => `
                        <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #f0f0f0; font-size: 12px;">
                            <span>${t.ticker} ${t.tipo}</span>
                            <span style="color: ${t.pnl >= 0 ? '#28a745' : '#dc3545'}; font-weight: 600;">${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}</span>
                        </div>
                    `).join('')}
                </div>
                `;
            });
            detailHtml += '</div></div>';

            document.getElementById('reportPlan').innerHTML = `
                ${summaryHtml}
                ${detailHtml}
            `;
        }
        
        function refreshDashboard() {
            const btn = document.getElementById('refreshBtn');
            btn.classList.add('spinning');
            const i = Array.from(document.querySelectorAll('.tab-btn')).indexOf(document.querySelector('.tab-btn.active'));
            if (i === 0) loadTradeMonitor();
            else if (i === 1) loadComparison();
            else if (i === 2) loadHistory();
            else if (i === 3) loadHistoryReport();
            document.getElementById('updateTime').textContent = new Date().toLocaleString();
            setTimeout(() => btn.classList.remove('spinning'), 500);
        }
        
        function toggleSummaryTable() {
            const container = document.getElementById('summaryTableContainer');
            const icon = document.getElementById('toggleIcon');
            const text = document.getElementById('toggleText');
            const btn = document.getElementById('toggleSummaryBtn');
            
            if (container.style.maxHeight === '0px') {
                // Expandir
                container.style.maxHeight = '1000px';
                container.style.opacity = '1';
                icon.textContent = '▼';
                text.textContent = 'Ocultar';
                btn.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
            } else {
                // Colapsar
                container.style.maxHeight = '0px';
                container.style.opacity = '0';
                icon.textContent = '▶';
                text.textContent = 'Mostrar';
                btn.style.background = 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)';
            }
        }
        
        setInterval(refreshDashboard, 30000);
        loadTradeMonitor();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    market_status, status_class, market_time = get_market_status()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return render_template_string(HTML, market_status=market_status, market_status_class=status_class, market_time=market_time, now=now)

@app.route('/api/trades')
def api_trades():
    return jsonify({"trades": load_active_trades(), "summary": calculate_summary()})

@app.route('/api/comparison')
def api_comparison():
    return jsonify(load_plan_comparison())

@app.route('/api/history')
def api_history():
    return jsonify(load_history_trades())

def main():
    import sys
    PORT = 8050
    print("="*80)
    print("TRADE DASHBOARD UNIFICADO")
    print("="*80)
    sys.stdout.flush()
    
    local_ip = get_local_ip()
    print(f"\n[LOCAL ACCESS]:\n  -> http://localhost:{PORT}/")
    print(f"\n[LAN ACCESS]:\n  -> http://{local_ip}:{PORT}/")
    print(f"\n[OK] Servidor escuchando en 0.0.0.0:{PORT}...\n")
    sys.stdout.flush()
    
    try:
        app.run(host="0.0.0.0", port=PORT, debug=False)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
