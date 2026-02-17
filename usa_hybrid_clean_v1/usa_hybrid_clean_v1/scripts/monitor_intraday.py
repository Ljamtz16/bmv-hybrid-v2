"""
monitor_intraday.py
Monitoreo intradía mínimo para actualizar Bitácora H3 y detectar TP/SL.

Estrategia inicial (versión 0.1):
- Cargar bitácora (Excel) y filtrar predicciones ACTIVO.
- Obtener último precio para cada ticker:
    * Si existe archivo intradía reciente (data/intraday5/buffer/<TICKER>.csv) usar último close.
    * Fallback: precio entry (no actualiza PnL real) o daily close si se agrega luego.
- Evaluar si alcanzó TP o SL -> marcar TP_HIT / SL_HIT.
- Actualizar progreso a TP %, días transcurridos y timestamp.
- Guardar de vuelta.
- (Opcional) Enviar mensaje a Telegram reutilizando 33_notify_telegram_intraday (TODO en siguiente iteración si se requiere).

Uso:
  python scripts/monitor_intraday.py --once
  python scripts/monitor_intraday.py --loop --interval-seconds 300

Limitaciones:
- No calcula spreads ni ETTH dinámico.
- No gestiona expiración intradía (solo horizon en días ya manejado en update_prices_from_daily si se usa).

Siguientes mejoras posibles:
- Integrar API de precios streaming / WebSocket.
- Guardar log incremental en reports/intraday/YYYY-MM-DD/alerts.txt.
- Notificaciones Telegram (TP/SL) inmediatas.
"""
import os
import sys
import time
import json
import hashlib
import logging
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# Reusar rutas de bitácora
BITACORA_PATH = r"G:\Mi unidad\Trading proyecto\H3_BITACORA_PREDICCIONES.xlsx" if os.path.exists("G:\\") else "reports/H3_BITACORA_PREDICCIONES.xlsx"
BUFFER_DIR = Path("data/intraday5/buffer")  # snapshots intradía (close,timestamp)
OUTPUTS_DIR = Path("outputs")

# Rate limit + hash guardado Excel
SAVE_COOLDOWN_S = 30
_last_save_ts = 0.0
_last_save_hash = ""
PROCESS_START = time.time()
LAST_ERRORS = 0


def load_bitacora():
    if not os.path.exists(BITACORA_PATH):
        print(f"[monitor] No existe bitácora en {BITACORA_PATH}")
        return None
    try:
        df = pd.read_excel(BITACORA_PATH, sheet_name="Predicciones")
        return df
    except Exception as e:
        print(f"[monitor] ERROR leyendo bitácora: {e}")
        return None


def save_bitacora(df):
    """Rate-limited + hash-diff guardado para reducir I/O y ruido."""
    global _last_save_ts, _last_save_hash, LAST_ERRORS
    now = time.time()
    try:
        payload = df.to_excel(index=False, sheet_name='Predicciones')  # not written yet (placeholder)
    except Exception:
        # Construir payload manual usando to_csv para hashing
        payload_bytes = df.to_csv(index=False).encode()
    else:
        # to_excel a bytes directo no trivial sin ExcelWriter; usamos CSV para hash
        payload_bytes = df.to_csv(index=False).encode()
    current_hash = hashlib.md5(payload_bytes).hexdigest()
    if (now - _last_save_ts) < SAVE_COOLDOWN_S and current_hash == _last_save_hash:
        logging.info("[monitor] Skip save (cooldown/hash)")
        return False
    try:
        with pd.ExcelWriter(BITACORA_PATH, engine='openpyxl', mode='w') as w:
            df.to_excel(w, sheet_name='Predicciones', index=False)
        # Export CSV para dashboard web (ligero)
        try:
            OUTPUTS_DIR.mkdir(exist_ok=True)
            (OUTPUTS_DIR / 'bitacora_intraday.csv').write_text(df.to_csv(index=False))
        except Exception as e:
            logging.warning(f"[monitor] No se pudo exportar bitacora_intraday.csv: {e}")
        _last_save_ts = now
        _last_save_hash = current_hash
        logging.info(f"[monitor] Guardado bitácora ({len(df)} filas)")
        return True
    except Exception as e:
        LAST_ERRORS += 1
        logging.error(f"[monitor] ERROR guardando bitácora: {e}")
        return False


def load_buffer(ticker: str):
    """Lee buffer CSV y retorna DataFrame o None."""
    if not BUFFER_DIR.exists():
        return None
    candidates = list(BUFFER_DIR.glob(f"{ticker}*.csv"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    path = candidates[0]
    try:
        df = pd.read_csv(path)
        return df
    except Exception:
        return None

def extract_last_price(buf_df):
    for c in ["close","Close","last","price"]:
        if c in buf_df.columns and buf_df[c].dropna().shape[0]:
            return float(buf_df[c].dropna().iloc[-1])
    return None

def buffer_freshness_minutes(buf_df):
    if buf_df is None or buf_df.empty:
        return None
    ts_col = "timestamp" if "timestamp" in buf_df.columns else None
    if not ts_col:
        return None
    try:
        ts_last = pd.to_datetime(buf_df[ts_col].iloc[-1], utc=True)
        age_min = (pd.Timestamp.now(tz="UTC") - ts_last).total_seconds()/60.0
        return age_min
    except Exception:
        return None


def update_active_positions():
    df = load_bitacora()
    if df is None:
        return
    if 'Status' not in df.columns:
        print('[monitor] Formato inesperado bitácora (sin Status)')
        return

    active_mask = df['Status'] == 'ACTIVO'
    if active_mask.sum() == 0:
        print('[monitor] No hay posiciones ACTIVO')
        return

    # Forzar dtype float64 en columna "Progreso a TP %" antes del loop
    col_progress = "Progreso a TP %"
    if col_progress not in df.columns:
        df[col_progress] = pd.Series(dtype="float64")
    else:
        df[col_progress] = pd.to_numeric(df[col_progress], errors="coerce").astype("float64")

    now = datetime.now(timezone.utc)
    updated = 0
    tp_hits = 0
    sl_hits = 0
    fresh_buffers = 0
    total_active = int(active_mask.sum())

    for idx in df[active_mask].index:
        ticker = str(df.at[idx,'Ticker'])
        side = df.at[idx,'Side']
        entry = float(df.at[idx,'Entry Price']) if pd.notna(df.at[idx,'Entry Price']) else None
        tp_price = float(df.at[idx,'TP Price']) if pd.notna(df.at[idx,'TP Price']) else None
        sl_price = float(df.at[idx,'SL Price']) if pd.notna(df.at[idx,'SL Price']) else None

        buf_df = load_buffer(ticker)
        last_price = extract_last_price(buf_df) if buf_df is not None else None
        # Freshness check
        age_min = buffer_freshness_minutes(buf_df)
        if age_min is not None and age_min > 10:
            logging.warning(f"[{ticker}] buffer staled {age_min:.1f} min")
        if age_min is not None and age_min <= 10:
            fresh_buffers += 1
        if last_price is None:
            # fallback: mantener precio actual
            last_price = float(df.at[idx,'Precio Actual']) if pd.notna(df.at[idx,'Precio Actual']) else entry
            if last_price is None:
                continue
        df.at[idx,'Precio Actual'] = last_price
        df.at[idx,'Última Actualización'] = now.strftime('%Y-%m-%d %H:%M')

        # Progreso a TP mejorado con asimetrías TP/SL
        # Para LONG: progreso = (current - entry) / (tp - entry) * 100
        # Para SHORT: progreso = (entry - current) / (entry - tp) * 100
        # Negativo significa avanzando hacia SL
        progress = 0.0
        if side == 'BUY' and tp_price and entry and tp_price > entry:
            # Distancia total de entry a TP
            tp_dist = tp_price - entry
            # Distancia actual desde entry
            current_move = last_price - entry
            progress = (current_move / tp_dist) * 100.0
            # Limitar a rango realista: si alcanzó SL, mostrar negativo
            if sl_price and last_price <= sl_price:
                sl_dist = entry - sl_price
                progress = -((entry - last_price) / sl_dist) * 100.0
        elif side != 'BUY' and tp_price and entry and entry > tp_price:
            # SHORT: TP abajo
            tp_dist = entry - tp_price
            current_move = entry - last_price
            progress = (current_move / tp_dist) * 100.0
            if sl_price and last_price >= sl_price:
                sl_dist = sl_price - entry
                progress = -((last_price - entry) / sl_dist) * 100.0
        
        # Usar loc para evitar FutureWarning de dtype incompatible
        df.loc[idx, col_progress] = round(progress, 2)

        # Guardar serie de progreso para dashboard (append incremental)
        try:
            progress_file = OUTPUTS_DIR / f"progress_series_{ticker}.csv"
            ts_now = now.strftime('%Y-%m-%d %H:%M:%S')
            progress_entry = pd.DataFrame({
                'timestamp': [ts_now],
                'progreso_tp': [round(progress, 2)],
                'precio_actual': [round(last_price, 2)]
            })
            if progress_file.exists():
                existing = pd.read_csv(progress_file)
                # Limitar a últimas 100 entradas para no crecer indefinidamente
                if len(existing) >= 100:
                    existing = existing.iloc[-99:]
                combined = pd.concat([existing, progress_entry], ignore_index=True)
                combined.to_csv(progress_file, index=False)
            else:
                progress_entry.to_csv(progress_file, index=False)
        except Exception as e:
            logging.warning(f"[{ticker}] No se pudo guardar progress_series: {e}")

        # Chequeo TP/SL
        hit = None
        if side == 'BUY':
            if tp_price and last_price >= tp_price:
                hit = 'TP_HIT'
            elif sl_price and last_price <= sl_price:
                hit = 'SL_HIT'
        else:  # SHORT
            if tp_price and last_price <= tp_price:
                hit = 'TP_HIT'
            elif sl_price and last_price >= sl_price:
                hit = 'SL_HIT'
        if hit:
            df.at[idx,'Status'] = hit
            df.at[idx,'Fecha Cierre'] = now.strftime('%Y-%m-%d')
            df.at[idx,'Exit Price'] = last_price
            # Exit reason clasificación simple
            reason = 'TP_natural' if hit == 'TP_HIT' else 'SL_natural'
            if 'Exit Reason' not in df.columns:
                df['Exit Reason'] = pd.Series(dtype='string')
            df.at[idx,'Exit Reason'] = reason
            if entry:
                pnl_usd = (last_price - entry) * 100 if side=='BUY' else (entry - last_price)*100
                pnl_pct = ((last_price - entry)/entry*100) if side=='BUY' else ((entry - last_price)/entry*100)
                df.at[idx,'PnL USD'] = round(pnl_usd,2)
                df.at[idx,'PnL %'] = round(pnl_pct,2)
            if hit=='TP_HIT':
                tp_hits += 1
            else:
                sl_hits += 1
        updated += 1

    saved = save_bitacora(df)
    logging.info(f"[monitor] Actualizados {updated} activos (TP:{tp_hits} SL:{sl_hits}) saved={saved}")
    
    # Exportar equity curve (PnL acumulado) para dashboard
    try:
        # Calcular equity solo con trades cerrados
        closed_mask = df['Status'].isin(['TP_HIT', 'SL_HIT'])
        closed_df = df[closed_mask].copy()
        if len(closed_df) > 0:
            # Ordenar por fecha de cierre
            if 'Fecha Cierre' in closed_df.columns:
                closed_df['Fecha Cierre'] = pd.to_datetime(closed_df['Fecha Cierre'], errors='coerce')
                closed_df = closed_df.sort_values('Fecha Cierre')
            
            # Calcular PnL acumulado
            pnl_vals = pd.to_numeric(closed_df['PnL USD'], errors='coerce').fillna(0)
            closed_df['PnL_Acumulado'] = pnl_vals.cumsum()
            
            # Exportar equity series
            equity_data = closed_df[['Ticker', 'Fecha Cierre', 'PnL USD', 'PnL %', 'PnL_Acumulado', 'Exit Reason']].copy()
            equity_data['Fecha Cierre'] = equity_data['Fecha Cierre'].dt.strftime('%Y-%m-%d %H:%M')
            (OUTPUTS_DIR / 'equity_curve.csv').write_text(equity_data.to_csv(index=False))
    except Exception as e:
        logging.warning(f"[monitor] No se pudo exportar equity_curve: {e}")
    
    # Health snapshot
    try:
        OUTPUTS_DIR.mkdir(exist_ok=True)
        # Calcular estado general para dashboard
        status = 'ok' if LAST_ERRORS == 0 else 'warning'
        health = {
            "uptime_s": round(time.time() - PROCESS_START, 1),
            # usar datetime.now(datetime.UTC) en lugar de utcnow() (deprecado)
            "last_tick_utc": datetime.now(timezone.utc).isoformat(),
            "last_run_utc": datetime.now(timezone.utc).isoformat(),
            "buffers_dir_exists": BUFFER_DIR.exists(),
            "updated_positions": int(updated),
            "tp_hits": int(tp_hits),
            "sl_hits": int(sl_hits),
            "last_save_ts": _last_save_ts,
            "errors_last_run": LAST_ERRORS,
            "status": status,
            "fresh_buffers": int(fresh_buffers),
            "total_buffers": int(total_active),
        }
        (OUTPUTS_DIR / "monitor_health.json").write_text(json.dumps(health, indent=2))
    except Exception as e:
        logging.error(f"[monitor] Error escribiendo health: {e}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--once', action='store_true', help='Ejecutar una sola vez')
    ap.add_argument('--loop', action='store_true', help='Loop continuo')
    ap.add_argument('--interval-seconds', type=int, default=300, help='Intervalo entre ticks en modo loop')
    args = ap.parse_args()

    if args.once:
        update_active_positions()
        return

    if args.loop:
        print(f"[monitor] Iniciando loop cada {args.interval_seconds}s ... Ctrl+C para salir")
        try:
            while True:
                update_active_positions()
                time.sleep(args.interval_seconds)
        except KeyboardInterrupt:
            print('[monitor] Loop detenido por usuario')
        return

    # default
    update_active_positions()

if __name__ == '__main__':
    main()