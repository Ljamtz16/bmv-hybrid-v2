import pandas as pd
import os
from pathlib import Path

print('=' * 80)
print('RESUMEN COMPLETO DEL SISTEMA DE TRADING - HYBRID ML USA')
print('=' * 80)

# 1. DATOS
print('\n### 1. BASE DE DATOS ###')
data_path = Path('data/us/intraday_15m/consolidated_15m.parquet')
if data_path.exists():
    df_data = pd.read_parquet(data_path)
    print(f'Barras totales: {len(df_data):,}')
    print(f'Fecha inicio: {df_data["timestamp"].min()}')
    print(f'Fecha fin: {df_data["timestamp"].max()}')
    print(f'Tickers: {df_data["ticker"].nunique()}')
    print(f'Lista tickers: {sorted(df_data["ticker"].unique())}')

# 2. MODELO
print('\n### 2. MODELO PREDICTIVO ###')
model_path = Path('evidence/retrained_prob_win_robust/models_per_ticker.pkl')
if model_path.exists():
    print(f'Modelo: {model_path.name}')
    print('Tipo: XGBoost por ticker')
    print('Target: Probabilidad de ganar (prob_win)')
    
forecast_path = Path('evidence/forecast_retrained_robust/forecast_prob_win_retrained.csv')
if forecast_path.exists():
    df_forecast = pd.read_csv(forecast_path)
    print(f'\nPredicciones totales: {len(df_forecast):,}')
    print(f'Prob_win promedio: {df_forecast["prob_win_retrained"].mean():.2%}')
    print(f'Señales BUY: {(df_forecast["pred_label"] == 1).sum()}')
    print(f'Señales SELL: {(df_forecast["pred_label"] == 0).sum()}')

# 3. PLANES DE TRADING
print('\n### 3. PLANES DE TRADING ###')
plans_dir = Path('evidence/weekly_plans')
plan_files = sorted(plans_dir.glob('plan_*.csv'))
if plan_files:
    latest_std = [f for f in plan_files if 'standard' in f.name][-1]
    latest_pw55 = [f for f in plan_files if 'probwin55' in f.name][-1]
    
    df_std = pd.read_csv(latest_std)
    df_pw55 = pd.read_csv(latest_pw55)
    
    print(f'Plan STANDARD ({latest_std.name}):')
    print(f'  Posiciones: {len(df_std)}')
    print(f'  Tickers: {list(df_std["ticker"].values)}')
    print(f'  Exposición total: ${df_std["exposure"].sum():,.2f}')
    print(f'  Prob_win promedio: {df_std["prob_win"].mean():.2%}')
    
    print(f'\nPlan PROBWIN_55 ({latest_pw55.name}):')
    print(f'  Posiciones: {len(df_pw55)}')
    if len(df_pw55) > 0:
        print(f'  Tickers: {list(df_pw55["ticker"].values)}')
        print(f'  Exposición total: ${df_pw55["exposure"].sum():,.2f}')
        print(f'  Prob_win promedio: {df_pw55["prob_win"].mean():.2%}')
    else:
        print('  (Sin posiciones - filtro muy estricto)')

# 4. HISTORIAL DE TRADES
print('\n### 4. HISTORIAL DE OPERACIONES ###')
hist_path = Path('val/trade_history_closed.csv')
if hist_path.exists():
    df_hist = pd.read_csv(hist_path)
    print(f'Trades cerrados: {len(df_hist)}')
    
    wins = df_hist[df_hist['pnl'] > 0]
    losses = df_hist[df_hist['pnl'] <= 0]
    
    print(f'\nWins: {len(wins)} ({len(wins)/len(df_hist)*100:.1f}%)')
    print(f'Losses: {len(losses)} ({len(losses)/len(df_hist)*100:.1f}%)')
    print(f'\nP&L Total: ${df_hist["pnl"].sum():.2f}')
    print(f'Win promedio: ${wins["pnl"].mean():.2f}' if len(wins) > 0 else 'Win promedio: N/A')
    print(f'Loss promedio: ${losses["pnl"].mean():.2f}' if len(losses) > 0 else 'Loss promedio: N/A')
    
    print(f'\nPor exit_reason:')
    print(df_hist['exit_reason'].value_counts().to_string())
    
    print(f'\nÚltimos 5 trades:')
    print(df_hist[['ticker', 'side', 'pnl', 'pnl_pct', 'exit_reason', 'date']].tail(5).to_string(index=False))

# 5. DASHBOARD
print('\n### 5. DASHBOARD ###')
print('URL Local: http://localhost:7777')
print('URL LAN: http://192.168.1.69:7777')
print('Pestañas:')
print('  - Trade Monitor: Posiciones activas con precios en tiempo real')
print('  - Comparación Plan: STANDARD vs PROBWIN_55')
print('  - Historial: Trades cerrados y métricas')

print('\n' + '=' * 80)
