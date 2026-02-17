"""
Validación de trades generados con NUEVA configuración (prob_win≥5%)
Compara predicciones vs realidad usando datos intraday reales
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, time

def load_intraday_data(ticker, start_date, end_date):
    """Carga datos intraday desde CSV"""
    intraday_dir = Path("data/us/intraday") / ticker
    
    # Buscar archivo que cubra el rango
    files = list(intraday_dir.glob(f"{ticker}_*_15m.csv"))
    if not files:
        raise FileNotFoundError(f"No intraday data for {ticker}")
    
    # Find file that covers the date range (by parsing filename)
    target_date = pd.to_datetime(start_date).date()
    best_file = None
    
    for file_path in files:
        # Parse filename: TICKER_START_END_15m.csv
        parts = file_path.stem.split('_')
        if len(parts) >= 3:
            file_start = pd.to_datetime(parts[1]).date()
            file_end = pd.to_datetime(parts[2]).date()
            
            # Check if target date is within file range
            if file_start <= target_date <= file_end:
                best_file = file_path
                break
    
    if best_file is None:
        # Fallback: use most recent file
        best_file = sorted(files)[-1]
    
    print(f"  📂 Cargando: {best_file.name}")
    
    df = pd.read_csv(best_file, header=[0, 1], index_col=0, parse_dates=True)
    df.columns = df.columns.droplevel(1)  # Remove ticker level
    df.index = pd.to_datetime(df.index)
    
    # Filter by date range
    mask = (df.index.date >= pd.to_datetime(start_date).date()) & \
           (df.index.date <= pd.to_datetime(end_date).date())
    df = df[mask]
    
    return df

def validate_trade(trade, intraday_df):
    """Valida un trade contra datos reales"""
    ticker = trade['ticker']
    direction = trade['direction']
    entry_time = pd.to_datetime(trade['timestamp'])
    entry_price = trade['entry_price']
    tp_price = trade['tp_price']
    sl_price = trade['sl_price']
    
    # Filter intraday data from entry onwards (same day only)
    trade_date = entry_time.date()
    mask = (intraday_df.index.date == trade_date) & \
           (intraday_df.index >= entry_time)
    data_after_entry = intraday_df[mask]
    
    if len(data_after_entry) == 0:
        return {
            'outcome': 'NO_DATA',
            'pnl': 0,
            'bars_held': 0,
            'exit_time': None,
            'exit_price': entry_price,
            'reason': 'No intraday data after entry'
        }
    
    # Check each bar for TP/SL hit
    for idx, bar in data_after_entry.iterrows():
        high = bar['High']
        low = bar['Low']
        close = bar['Close']
        
        if direction == 'LONG':
            # Check TP hit (high >= tp_price)
            if high >= tp_price:
                pnl = (tp_price - entry_price) / entry_price
                bars = len(intraday_df[intraday_df.index <= idx])
                return {
                    'outcome': 'TP_HIT',
                    'pnl': pnl,
                    'bars_held': bars,
                    'exit_time': idx,
                    'exit_price': tp_price,
                    'reason': f'TP hit at {tp_price:.2f}'
                }
            
            # Check SL hit (low <= sl_price)
            if low <= sl_price:
                pnl = (sl_price - entry_price) / entry_price
                bars = len(intraday_df[intraday_df.index <= idx])
                return {
                    'outcome': 'SL_HIT',
                    'pnl': pnl,
                    'bars_held': bars,
                    'exit_time': idx,
                    'exit_price': sl_price,
                    'reason': f'SL hit at {sl_price:.2f}'
                }
        
        else:  # SHORT
            # Check TP hit (low <= tp_price)
            if low <= tp_price:
                pnl = (entry_price - tp_price) / entry_price
                bars = len(intraday_df[intraday_df.index <= idx])
                return {
                    'outcome': 'TP_HIT',
                    'pnl': pnl,
                    'bars_held': bars,
                    'exit_time': idx,
                    'exit_price': tp_price,
                    'reason': f'TP hit at {tp_price:.2f}'
                }
            
            # Check SL hit (high >= sl_price)
            if high >= sl_price:
                pnl = (entry_price - sl_price) / entry_price
                bars = len(intraday_df[intraday_df.index <= idx])
                return {
                    'outcome': 'SL_HIT',
                    'pnl': pnl,
                    'bars_held': bars,
                    'exit_time': idx,
                    'exit_price': sl_price,
                    'reason': f'SL hit at {sl_price:.2f}'
                }
    
    # No TP/SL hit - close at EOD
    last_bar = data_after_entry.iloc[-1]
    exit_price = last_bar['Close']
    
    if direction == 'LONG':
        pnl = (exit_price - entry_price) / entry_price
    else:
        pnl = (entry_price - exit_price) / entry_price
    
    return {
        'outcome': 'EOD_CLOSE',
        'pnl': pnl,
        'bars_held': len(data_after_entry),
        'exit_time': data_after_entry.index[-1],
        'exit_price': exit_price,
        'reason': f'Closed at EOD at {exit_price:.2f}'
    }

# Main validation
dates = ["2025-10-16", "2025-10-17", "2025-10-22", "2025-10-31"]

print("=" * 80)
print("VALIDACIÓN DE TRADES - NUEVA CONFIGURACIÓN (prob_win≥5%)")
print("=" * 80)
print()

all_results = []
for date in dates:
    plan_path = Path(f"reports/intraday/{date}/trade_plan_intraday.csv")
    
    if not plan_path.exists():
        print(f"⚠️  {date}: No hay plan generado")
        continue
    
    plan = pd.read_csv(plan_path)
    
    if len(plan) == 0:
        print(f"📭 {date}: Plan vacío (0 trades)")
        continue
    
    print(f"\n{'=' * 80}")
    print(f"📅 FECHA: {date}")
    print(f"{'=' * 80}")
    print(f"Trades en plan: {len(plan)}")
    print(f"Tickers: {', '.join(plan['ticker'].unique())}")
    print()
    
    for idx, trade in plan.iterrows():
        ticker = trade['ticker']
        print(f"\n🔹 Trade #{idx+1}: {ticker} {trade['direction']}")
        print(f"   Entry: ${trade['entry_price']:.2f} @ {trade['timestamp']}")
        print(f"   TP: ${trade['tp_price']:.2f} (+{((trade['tp_price']/trade['entry_price']-1)*100):.2f}%)")
        print(f"   SL: ${trade['sl_price']:.2f} ({((trade['sl_price']/trade['entry_price']-1)*100):.2f}%)")
        print(f"   Qty: {trade['qty']}, Exposure: ${trade['exposure']:.2f}")
        print(f"   Prob Win: {trade['prob_win']*100:.1f}%, P(TP<SL): {trade['p_tp_before_sl']*100:.1f}%")
        
        try:
            # Load intraday data
            intraday_df = load_intraday_data(ticker, date, date)
            
            # Validate trade
            result = validate_trade(trade, intraday_df)
            
            # Display result
            outcome_emoji = {
                'TP_HIT': '✅',
                'SL_HIT': '❌',
                'EOD_CLOSE': '⏰',
                'NO_DATA': '⚠️'
            }
            
            emoji = outcome_emoji.get(result['outcome'], '❓')
            print(f"\n   {emoji} RESULTADO: {result['outcome']}")
            print(f"      Razón: {result['reason']}")
            print(f"      PnL: {result['pnl']*100:+.2f}%")
            print(f"      Barras sostenidas: {result['bars_held']}")
            if result['exit_time']:
                print(f"      Salida: {result['exit_time']}")
            
            # Calculate dollar PnL
            dollar_pnl = result['pnl'] * trade['exposure']
            print(f"      PnL en USD: ${dollar_pnl:+.2f}")
            
            # Store result
            all_results.append({
                'date': date,
                'ticker': ticker,
                'direction': trade['direction'],
                'entry_price': trade['entry_price'],
                'exit_price': result['exit_price'],
                'outcome': result['outcome'],
                'pnl_pct': result['pnl'],
                'pnl_usd': dollar_pnl,
                'exposure': trade['exposure'],
                'prob_win': trade['prob_win'],
                'bars_held': result['bars_held']
            })
            
        except Exception as e:
            print(f"\n   ⚠️  ERROR: {e}")

# Summary
print(f"\n\n{'=' * 80}")
print("📊 RESUMEN GENERAL")
print(f"{'=' * 80}")

if all_results:
    df_results = pd.DataFrame(all_results)
    
    total_trades = len(df_results)
    tp_hits = len(df_results[df_results['outcome'] == 'TP_HIT'])
    sl_hits = len(df_results[df_results['outcome'] == 'SL_HIT'])
    eod_closes = len(df_results[df_results['outcome'] == 'EOD_CLOSE'])
    
    total_pnl = df_results['pnl_usd'].sum()
    avg_pnl = df_results['pnl_usd'].mean()
    
    win_rate = (tp_hits / total_trades * 100) if total_trades > 0 else 0
    avg_prob_win = df_results['prob_win'].mean() * 100
    
    print(f"\n📈 Estadísticas:")
    print(f"   Total trades: {total_trades}")
    print(f"   TP hits: {tp_hits} ({tp_hits/total_trades*100:.1f}%)")
    print(f"   SL hits: {sl_hits} ({sl_hits/total_trades*100:.1f}%)")
    print(f"   EOD closes: {eod_closes} ({eod_closes/total_trades*100:.1f}%)")
    print(f"\n💰 Rentabilidad:")
    print(f"   PnL total: ${total_pnl:+.2f}")
    print(f"   PnL promedio: ${avg_pnl:+.2f}")
    print(f"   Win rate real: {win_rate:.1f}%")
    print(f"   Win rate predicho: {avg_prob_win:.1f}%")
    print(f"   Error de calibración: {abs(win_rate - avg_prob_win):.1f}%")
    
    print(f"\n📋 Detalle por ticker:")
    ticker_summary = df_results.groupby('ticker').agg({
        'pnl_usd': ['count', 'sum', 'mean'],
        'outcome': lambda x: (x == 'TP_HIT').sum()
    }).round(2)
    print(ticker_summary)
    
    # Save results
    output_path = "reports/intraday/validation_new_config_october.csv"
    df_results.to_csv(output_path, index=False)
    print(f"\n💾 Resultados guardados: {output_path}")
    
else:
    print("\n⚠️  No se validaron trades (no hay planes o faltan datos)")

print()
