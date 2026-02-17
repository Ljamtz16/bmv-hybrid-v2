"""
Generar plan semanal estándar + plan con filtro prob_win
Y monitorizar ambos con el dashboard
"""
import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path
import json
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

def calculate_etth_days(ticker, current_price, target_price):
    """
    Calcula tiempo estimado para alcanzar target usando:
    - 70% velocidad intradía (últimos 60 min)
    - 30% ATR histórico (14 períodos)
    
    Retorna: días estimados (float)
    """
    try:
        # Obtener histórico de 1 minuto (últimas 2 horas) para velocidad intradía
        stock = yf.Ticker(ticker)
        hist_intraday = stock.history(period="5d", interval="1m")
        
        if hist_intraday.empty or len(hist_intraday) < 20:
            return None
        
        # Método 1: Velocidad intradía (últimos 60 minutos)
        changes_recent = hist_intraday['Close'].diff().dropna().tail(60)
        velocity_intraday = changes_recent.abs().mean() if len(changes_recent) > 0 else 0
        
        # Método 2: ATR histórico (14 períodos de 1 minuto)
        high_low = hist_intraday['High'] - hist_intraday['Low']
        high_close = abs(hist_intraday['High'] - hist_intraday['Close'].shift())
        low_close = abs(hist_intraday['Low'] - hist_intraday['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.tail(14).mean()
        
        # Combinar: 70% velocidad intradía + 30% ATR
        if velocity_intraday > 0 and atr > 0:
            combined_velocity = (velocity_intraday * 0.7) + (atr * 0.3)
        elif velocity_intraday > 0:
            combined_velocity = velocity_intraday
        elif atr > 0:
            combined_velocity = atr
        else:
            return None
        
        # Distancia a recorrer
        distance = abs(target_price - current_price)
        
        # Tiempo estimado en minutos
        estimated_minutes = distance / combined_velocity if combined_velocity > 0 else None
        
        if estimated_minutes is None or estimated_minutes <= 0:
            return None
        
        # Convertir a días (asumiendo 6.5 horas de mercado = 390 minutos por día)
        trading_minutes_per_day = 390
        estimated_days = estimated_minutes / trading_minutes_per_day
        
        return max(0.01, estimated_days)  # Mínimo 0.01 días
        
    except Exception as e:
        print(f"  [WARNING] Error calculando etth para {ticker}: {e}")
        return None

# Configuración
WEEK_START = datetime.now().strftime("%Y-%m-%d")
FORECAST_FILE = Path("evidence/forecast_retrained_robust/forecast_prob_win_retrained.csv")
PLANS_DIR = Path("evidence/weekly_plans")
MONITOR_DIR = Path("evidence/monitor_this_week")

CAPITAL = 2000
MAX_DEPLOY = 1900
MAX_OPEN = 4
PER_TRADE_CASH = 500
TP_PCT = 0.016  # 1.6%
SL_PCT = 0.010  # 1.0%
HORIZON_DAYS = 2

print("="*80)
print("GENERADOR DE PLANES SEMANALES")
print("="*80)
print(f"\nFecha: {WEEK_START}")
print(f"Capital: ${CAPITAL}")
print(f"Max Deploy: ${MAX_DEPLOY}")
print(f"Max Posiciones: {MAX_OPEN}")
print(f"TP: {TP_PCT*100:.1f}% | SL: {SL_PCT*100:.1f}%")

# Crear directorios
PLANS_DIR.mkdir(parents=True, exist_ok=True)
MONITOR_DIR.mkdir(parents=True, exist_ok=True)

# [1] Cargar forecast
print(f"\n[1] CARGANDO FORECAST")
print("-" * 80)

if not FORECAST_FILE.exists():
    print(f"ERROR: Archivo no existe: {FORECAST_FILE}")
    sys.exit(1)

forecasts = pd.read_csv(FORECAST_FILE)
print(f"  Archivo: {FORECAST_FILE}")
print(f"  Total filas: {len(forecasts):,}")
print(f"  Tickers únicos: {forecasts['ticker'].nunique()}")
print(f"  Rango fechas: {forecasts['date'].min()} a {forecasts['date'].max()}")

# [2] Obtener precios actuales
print(f"\n[2] OBTENIENDO PRECIOS ACTUALES DE MERCADO")
print("-" * 80)

# Usar el close del forecast como precio de entrada
forecasts['date'] = pd.to_datetime(forecasts['date'])
# Usar último día disponible en el forecast
last_forecast_date = forecasts['date'].max()
latest_forecasts = forecasts[forecasts['date'] == last_forecast_date].copy()

print(f"  Última fecha del forecast: {last_forecast_date.date()}")
print(f"  Señales disponibles: {len(latest_forecasts)}")
print(f"\n  Obteniendo precios ACTUALES de yfinance...")

if latest_forecasts.empty:
    print("ERROR: No hay datos en la última fecha del forecast")
    sys.exit(1)

# Obtener precios ACTUALES de yfinance (hoy, 26 enero)
prices = {}
for _, row in latest_forecasts.iterrows():
    ticker = row['ticker']
    try:
        hist = yf.download(ticker, period="5d", interval="1d", progress=False)
        if not hist.empty:
            last_close = float(hist['Close'].iloc[-1])
            prices[ticker] = last_close
            print(f"  {ticker:6} | ${last_close:8.2f} (hoy)")
    except Exception as e:
        # Fallback: usar precio del forecast si yfinance falla
        prices[ticker] = float(row['close'])
        print(f"  {ticker:6} | ${prices[ticker]:8.2f} (forecast del {last_forecast_date.date()})")

if not prices:
    print("ERROR: No se pudieron obtener precios")
    sys.exit(1)

# [3] Generar señales
print(f"\n[3] GENERANDO SEÑALES")
print("-" * 80)

# Usar latest_forecasts como base
# Renombrar prob_win_retrained a prob_win para compatibilidad
if 'prob_win_retrained' in latest_forecasts.columns:
    latest_forecasts = latest_forecasts.copy()
    latest_forecasts['prob_win'] = latest_forecasts['prob_win_retrained']
elif 'prob_win' not in latest_forecasts.columns:
    print("ERROR: No hay columna prob_win o prob_win_retrained")
    sys.exit(1)

# Asignar los precios actuales como entry
latest_forecasts['entry'] = latest_forecasts['ticker'].map(prices)

# Calcular TP/SL
latest_forecasts['side'] = latest_forecasts['prob_win'].apply(lambda v: 'BUY' if v > 0.5 else 'SELL')
latest_forecasts['strength'] = latest_forecasts['prob_win']
latest_forecasts['tp_price'] = latest_forecasts.apply(
    lambda r: r['entry'] * (1 + TP_PCT) if r['side'] == 'BUY' else r['entry'] * (1 - TP_PCT),
    axis=1
)
latest_forecasts['sl_price'] = latest_forecasts.apply(
    lambda r: r['entry'] * (1 - SL_PCT) if r['side'] == 'BUY' else r['entry'] * (1 + SL_PCT),
    axis=1
)

# Cantidad y exposición
latest_forecasts['qty'] = (PER_TRADE_CASH / latest_forecasts['entry']).apply(lambda x: max(1, int(x)))
latest_forecasts['exposure'] = latest_forecasts['qty'] * latest_forecasts['entry']

# [3.5] CALCULAR TIEMPO ESTIMADO (etth_days_raw)
print(f"\n[3.5] CALCULANDO TIEMPO ESTIMADO A TP")
print("-" * 80)

etth_values = []
for _, row in latest_forecasts.iterrows():
    ticker = row['ticker']
    current_price = row['entry']
    tp_price = row['tp_price']
    
    etth = calculate_etth_days(ticker, current_price, tp_price)
    etth_values.append(etth)
    
    if etth is not None:
        print(f"  {ticker:6} | etth: {etth:.2f} días (~{int(etth * 390)} min)")
    else:
        print(f"  {ticker:6} | etth: N/A (sin datos suficientes)")

latest_forecasts['etth_days_raw'] = etth_values
latest_forecasts['etth_days'] = latest_forecasts['etth_days_raw']
latest_forecasts['etth_degraded'] = latest_forecasts['etth_days_raw'].isna()

print(f"\nSeñales generadas: {len(latest_forecasts)}")
for _, row in latest_forecasts.iterrows():
    prob_win = float(row.get('prob_win', 0))
    etth = row.get('etth_days_raw', None)
    etth_str = f"{etth:.2f}d" if etth is not None else "N/A"
    print(f"  {row['ticker']:6} | {row['side']:4} @ ${row['entry']:8.2f} | prob_win: {prob_win:.2f} | etth: {etth_str}")

# [4] Generar PLAN ESTÁNDAR
print(f"\n[4] PLAN ESTÁNDAR (sin filtro adicional)")
print("-" * 80)

plan_std = latest_forecasts.sort_values('strength', ascending=False).head(MAX_OPEN).copy()

# Respetar capital
total_expo = plan_std['exposure'].sum() if not plan_std.empty else 0
if total_expo > MAX_DEPLOY:
    rows = []
    run = 0
    for _, r in plan_std.iterrows():
        if run + r['exposure'] <= MAX_DEPLOY:
            rows.append(r)
            run += r['exposure']
    plan_std = pd.DataFrame(rows) if rows else plan_std.head(1)

plan_std['plan_type'] = 'STANDARD'
plan_std['prob_win_threshold'] = 0.50
plan_std['capital'] = CAPITAL
plan_std['generated_at'] = datetime.now().isoformat()

plan_std_file = PLANS_DIR / f"plan_standard_{WEEK_START}.csv"
plan_std.to_csv(plan_std_file, index=False)
print(f"  Posiciones: {len(plan_std)}")
print(f"  Exposición: ${plan_std['exposure'].sum():.2f}")
print(f"  Guardado: {plan_std_file}")

# [5] Generar PLAN CON PROB_WIN >= 0.55
print(f"\n[5] PLAN CON FILTRO prob_win >= 0.55")
print("-" * 80)

plan_pw = latest_forecasts[latest_forecasts['prob_win'] >= 0.55].sort_values('strength', ascending=False).head(MAX_OPEN).copy()

total_expo_pw = plan_pw['exposure'].sum() if not plan_pw.empty else 0
if total_expo_pw > MAX_DEPLOY:
    rows = []
    run = 0
    for _, r in plan_pw.iterrows():
        if run + r['exposure'] <= MAX_DEPLOY:
            rows.append(r)
            run += r['exposure']
    plan_pw = pd.DataFrame(rows) if rows else plan_pw.head(1)

plan_pw['plan_type'] = 'PROBWIN_55'
plan_pw['prob_win_threshold'] = 0.55
plan_pw['capital'] = CAPITAL
plan_pw['generated_at'] = datetime.now().isoformat()

plan_pw_file = PLANS_DIR / f"plan_probwin55_{WEEK_START}.csv"
plan_pw.to_csv(plan_pw_file, index=False)
print(f"  Posiciones: {len(plan_pw)}")
print(f"  Exposición: ${plan_pw['exposure'].sum():.2f}")
print(f"  Guardado: {plan_pw_file}")

# [6] Crear config para dashboard
print(f"\n[6] CONFIGURANDO DASHBOARD")
print("-" * 80)

config = {
    "week_start": WEEK_START,
    "plans": [
        {
            "name": "STANDARD",
            "file": str(plan_std_file),
            "prob_win_threshold": 0.50,
            "positions": len(plan_std),
            "exposure": float(plan_std['exposure'].sum()),
            "tickers": plan_std['ticker'].tolist()
        },
        {
            "name": "PROBWIN_55",
            "file": str(plan_pw_file),
            "prob_win_threshold": 0.55,
            "positions": len(plan_pw),
            "exposure": float(plan_pw['exposure'].sum()),
            "tickers": plan_pw['ticker'].tolist()
        }
    ],
    "capital": CAPITAL,
    "max_deploy": MAX_DEPLOY,
    "tp_pct": TP_PCT,
    "sl_pct": SL_PCT,
    "dashboard_port": 7777
}

config_file = MONITOR_DIR / f"config_{WEEK_START}.json"
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)

print(f"  Config guardada: {config_file}")

# [7] Resumen
print(f"\n[7] RESUMEN")
print("=" * 80)

comparison = pd.DataFrame([
    {
        'Plan': 'STANDARD',
        'Threshold': '0.50',
        'Posiciones': len(plan_std),
        'Exposición': f"${plan_std['exposure'].sum():.2f}",
        'Tickers': ', '.join(plan_std['ticker'].tolist())
    },
    {
        'Plan': 'PROBWIN_55',
        'Threshold': '0.55',
        'Posiciones': len(plan_pw),
        'Exposición': f"${plan_pw['exposure'].sum():.2f}",
        'Tickers': ', '.join(plan_pw['ticker'].tolist())
    }
])

print("\n" + comparison.to_string(index=False))

print(f"\n\n[PRÓXIMOS PASOS]")
print("="*80)
print(f"1. Dashboard monitorizado en: localhost:7777")
print(f"2. Planes comparados en real-time")
print(f"3. Archivos en: {PLANS_DIR}")
print(f"4. Config en: {config_file}")
print(f"\n✓ PLANES GENERADOS Y LISTOS PARA MONITORIZAR")
