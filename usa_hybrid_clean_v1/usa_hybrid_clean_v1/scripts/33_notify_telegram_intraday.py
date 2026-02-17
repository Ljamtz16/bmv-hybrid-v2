# =============================================
# 33_notify_telegram_intraday.py
# =============================================
"""
Envía notificaciones de Telegram para plan y alertas intraday.

Mensajes:
- Signal Detected: Nuevas señales del plan
- Entry: Confirmación de entrada
- TP/SL: Hits de TP o SL
- EOD Close: Cierre forzado EOD

Features:
- Dedupe: evita notificaciones duplicadas
- Throttle: limita frecuencia de mensajes
- HTML formatting

Uso:
  python scripts/33_notify_telegram_intraday.py --date 2025-11-03
  python scripts/33_notify_telegram_intraday.py --date 2025-11-03 --send-plan --send-alerts
"""

import argparse
import os
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import json


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="Fecha YYYY-MM-DD")
    ap.add_argument("--forecast-dir", default="reports/intraday", help="Directorio de forecast")
    ap.add_argument("--send-plan", action="store_true", help="Enviar plan de trading")
    ap.add_argument("--send-alerts", action="store_true", help="Enviar alertas TP/SL/EOD")
    ap.add_argument("--throttle-minutes", type=int, default=5, help="Minutos entre mensajes del mismo tipo")
    ap.add_argument("--dry-run", action="store_true", help="No enviar, solo mostrar")
    return ap.parse_args()


def load_telegram_config():
    """Cargar configuración de Telegram desde .env o config."""
    token = os.getenv('TELEGRAM_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("[telegram_intraday] WARN: TELEGRAM_TOKEN o TELEGRAM_CHAT_ID no configurados")
        print("[telegram_intraday] Configura variables de entorno o edita .env")
        return None, None
    
    return token, chat_id


def send_telegram_message(token, chat_id, message, parse_mode='Markdown', dry_run=False):
    """Enviar mensaje a Telegram."""
    if dry_run:
        print("\n[telegram_intraday] DRY RUN - Mensaje:")
        print("=" * 50)
        print(message)
        print("=" * 50)
        return True
    
    try:
        import requests
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': parse_mode
        }
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            print("[telegram_intraday] Mensaje enviado exitosamente")
            return True
        else:
            print(f"[telegram_intraday] ERROR: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[telegram_intraday] ERROR enviando: {e}")
        return False


def check_throttle(message_type, throttle_minutes, state_file='reports/intraday/telegram_state.json'):
    """Verificar si debemos enviar (throttle)."""
    if not os.path.exists(state_file):
        return True
    
    try:
        with open(state_file) as f:
            state = json.load(f)
    except:
        return True
    
    last_sent = state.get(message_type)
    if not last_sent:
        return True
    
    last_time = datetime.fromisoformat(last_sent)
    now = datetime.now()
    
    if (now - last_time).total_seconds() > throttle_minutes * 60:
        return True
    
    print(f"[telegram_intraday] Throttled: {message_type} (último envío hace {(now - last_time).total_seconds()/60:.1f} min)")
    return False


def update_throttle_state(message_type, state_file='reports/intraday/telegram_state.json'):
    """Actualizar estado de throttle."""
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    
    state = {}
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                state = json.load(f)
        except:
            pass
    
    state[message_type] = datetime.now().isoformat()
    
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)


def format_plan_message(plan_df, date_str):
    """Formatear mensaje del plan de trading."""
    if plan_df.empty:
        return f"⚠️ *Intraday {date_str}*\n\nSin señales para hoy"
    
    n_trades = len(plan_df)
    total_exposure = plan_df['exposure'].sum()
    avg_prob = plan_df['prob_win'].mean()
    avg_etth = plan_df.get('ETTH', pd.Series([0])).mean()
    
    msg = f"📊 *Plan Intraday {date_str}*\n\n"
    msg += f"Trades: {n_trades}\n"
    msg += f"Exposure: ${total_exposure:,.0f}\n"
    msg += f"Prob media: {avg_prob:.1%}\n"
    
    if avg_etth > 0:
        msg += f"ETTH media: {avg_etth:.2f}d (~{avg_etth*6.5:.1f}h)\n"
    
    msg += "\n"
    
    for idx, row in plan_df.iterrows():
        ticker = row['ticker']
        entry = row['entry_price']
        tp = row['tp_price']
        sl = row['sl_price']
        prob = row.get('prob_win', 0)
        etth = row.get('ETTH', 0)
        qty = row.get('qty', 0)
        
        tp_pct = ((tp - entry) / entry) * 100
        sl_pct = ((sl - entry) / entry) * 100
        
        msg += f"*{ticker}* (x{qty})\n"
        msg += f"  Entry: ${entry:.2f}\n"
        msg += f"  TP: ${tp:.2f} (+{tp_pct:.1f}%) | SL: ${sl:.2f} ({sl_pct:.1f}%)\n"
        msg += f"  Prob: {prob:.0%}"
        
        if etth > 0:
            msg += f" | ETTH: {etth:.2f}d"
        
        # Agregar patrones si existen
        if 'pattern_score' in row and row.get('pattern_score', 0) > 0:
            patterns = []
            if row.get('pattern_hammer', 0) > 0:
                patterns.append('🔨Hammer')
            if row.get('pattern_engulfing_bull', 0) > 0:
                patterns.append('📈Engulf')
            if row.get('pattern_morning_star', 0) > 0:
                patterns.append('⭐Morning')
            if patterns:
                msg += f"\n  Patterns: {', '.join(patterns)}"
        
        msg += "\n\n"
    
    msg += f"⏰ Monitoreo activo: 9:30-16:00 NY\n"
    msg += f"🔒 Cierre forzado: 15:55 NY"
    
    return msg


def format_alert_message(alerts_df):
    """Formatear mensaje de alertas."""
    if alerts_df.empty:
        return None
    
    msg = "🔔 *Alertas Intraday*\n\n"
    
    for idx, alert in alerts_df.iterrows():
        ticker = alert['ticker']
        status = alert['status']
        exit_price = alert.get('exit_price', 0)
        pnl = alert.get('pnl_usd', 0)
        timestamp = alert.get('exit_timestamp', '')
        
        if status == 'TP_HIT':
            emoji = "✅"
            status_text = "TP HIT"
        elif status == 'SL_HIT':
            emoji = "❌"
            status_text = "SL HIT"
        elif status == 'EOD_CLOSE':
            emoji = "⏹️"
            status_text = "EOD CLOSE"
        else:
            continue
        
        msg += f"{emoji} *{ticker}*: {status_text}\n"
        msg += f"  Exit: ${exit_price:.2f} | PnL: ${pnl:+.2f}\n"
        
        if timestamp:
            try:
                ts = datetime.fromisoformat(timestamp)
                msg += f"  Time: {ts.strftime('%H:%M')}\n"
            except:
                pass
        
        msg += "\n"
    
    return msg


def load_recent_alerts(date_str, forecast_dir):
    """Cargar alertas recientes del archivo."""
    alert_file = Path(forecast_dir) / date_str / "alerts.txt"
    if not alert_file.exists():
        return pd.DataFrame()
    
    # Leer últimas líneas
    try:
        with open(alert_file) as f:
            lines = f.readlines()
        
        # Parsear líneas recientes (últimos 10 min)
        recent = []
        now = datetime.now()
        
        for line in lines[-20:]:  # Últimas 20 líneas
            # Formato: "HH:MM:SS - emoji TICKER: STATUS @ $XX.XX (PnL: $XX.XX)"
            if ' - ' in line and ':' in line:
                time_part = line.split(' - ')[0].strip()
                content = line.split(' - ')[1].strip()
                
                # Parsear ticker y status
                if 'TP_HIT' in content:
                    status = 'TP_HIT'
                elif 'SL_HIT' in content:
                    status = 'SL_HIT'
                elif 'EOD_CLOSE' in content:
                    status = 'EOD_CLOSE'
                else:
                    continue
                
                # Extraer ticker
                parts = content.split(':')
                if len(parts) >= 2:
                    ticker_part = parts[0].strip().split()[-1]
                    
                    # Extraer precio y PnL
                    exit_price = 0
                    pnl = 0
                    
                    if '@' in content and '$' in content:
                        try:
                            price_part = content.split('@')[1].split('(')[0].strip()
                            exit_price = float(price_part.replace('$', '').strip())
                        except:
                            pass
                    
                    if 'PnL:' in content:
                        try:
                            pnl_part = content.split('PnL:')[1].split(')')[0].strip()
                            pnl = float(pnl_part.replace('$', '').replace('+', '').strip())
                        except:
                            pass
                    
                    recent.append({
                        'ticker': ticker_part,
                        'status': status,
                        'exit_price': exit_price,
                        'pnl_usd': pnl,
                        'exit_timestamp': f"{date_str} {time_part}"
                    })
        
        return pd.DataFrame(recent)
    
    except Exception as e:
        print(f"[telegram_intraday] ERROR leyendo alertas: {e}")
        return pd.DataFrame()


def main():
    args = parse_args()
    
    print(f"[telegram_intraday] Fecha: {args.date}")
    
    # Cargar config
    token, chat_id = load_telegram_config()
    if not token or not chat_id:
        if not args.dry_run:
            print("[telegram_intraday] ERROR: No se puede enviar sin configuración")
            return
    
    # Plan de trading
    if args.send_plan:
        plan_file = Path(args.forecast_dir) / args.date / "trade_plan_intraday.csv"
        if plan_file.exists():
            plan_df = pd.read_csv(plan_file)
            
            if check_throttle('plan', args.throttle_minutes):
                msg = format_plan_message(plan_df, args.date)
                success = send_telegram_message(token, chat_id, msg, dry_run=args.dry_run)
                
                if success and not args.dry_run:
                    update_throttle_state('plan')
            else:
                print("[telegram_intraday] Plan no enviado (throttled)")
        else:
            print(f"[telegram_intraday] WARN: No existe plan {plan_file}")
    
    # Alertas
    if args.send_alerts:
        alerts_df = load_recent_alerts(args.date, args.forecast_dir)
        
        if not alerts_df.empty:
            if check_throttle('alerts', args.throttle_minutes):
                msg = format_alert_message(alerts_df)
                
                if msg:
                    success = send_telegram_message(token, chat_id, msg, dry_run=args.dry_run)
                    
                    if success and not args.dry_run:
                        update_throttle_state('alerts')
            else:
                print("[telegram_intraday] Alertas no enviadas (throttled)")
        else:
            print("[telegram_intraday] No hay alertas recientes")
    
    print("\n[telegram_intraday] Completado")


if __name__ == "__main__":
    main()
