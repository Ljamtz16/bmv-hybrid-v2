"""
Valida trades de octubre contra datos reales intraday
Calcula win rate, profit/loss real, y métricas de calidad
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import json


def load_intraday_data(ticker, date_str):
    """Cargar datos intraday de un ticker."""
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    
    # Buscar archivos CSV en el directorio del ticker
    ticker_dir = Path(f"data/us/intraday/{ticker}")
    if not ticker_dir.exists():
        return None
    
    # Buscar archivo que contenga la fecha
    csv_files = list(ticker_dir.glob(f"{ticker}_*_15m.csv"))
    
    for csv_file in csv_files:
        try:
            # Saltar las primeras 2 filas de headers
            df = pd.read_csv(csv_file, skiprows=[1, 2])
            
            # Primera columna es Datetime
            df.columns = ['timestamp', 'close', 'high', 'low', 'open', 'volume']
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Filtrar día específico
            day_data = df[df['timestamp'].dt.date == date_obj.date()].copy()
            
            if len(day_data) > 0:
                return day_data.sort_values('timestamp').reset_index(drop=True)
        except Exception as e:
            continue
    
    return None


def validate_trade(trade, intraday_df):
    """Validar un trade contra datos reales."""
    entry_price = trade['entry_price']
    tp_price = trade['tp_price']
    sl_price = trade['sl_price']
    direction = trade.get('direction', 'LONG')
    qty = trade['qty']
    
    # Buscar entry timestamp
    entry_time = pd.to_datetime(trade['timestamp'])
    
    # Datos posteriores a entry
    future_data = intraday_df[intraday_df['timestamp'] > entry_time].copy()
    
    if len(future_data) == 0:
        return {
            'outcome': 'NO_DATA',
            'hit_time': None,
            'exit_price': None,
            'pnl_pct': 0,
            'pnl_usd': 0,
            'bars_to_exit': 0
        }
    
    # EOD force close (15:55 ET)
    eod_time = entry_time.replace(hour=15, minute=55)
    future_data = future_data[future_data['timestamp'] <= eod_time]
    
    if len(future_data) == 0:
        return {
            'outcome': 'EOD_CLOSE',
            'hit_time': entry_time,
            'exit_price': entry_price,
            'pnl_pct': 0,
            'pnl_usd': 0,
            'bars_to_exit': 0
        }
    
    # Buscar TP y SL
    if direction == 'LONG':
        # TP: high >= tp_price
        # SL: low <= sl_price
        tp_hit = future_data[future_data['high'] >= tp_price]
        sl_hit = future_data[future_data['low'] <= sl_price]
    else:  # SHORT
        # TP: low <= tp_price
        # SL: high >= sl_price
        tp_hit = future_data[future_data['low'] <= tp_price]
        sl_hit = future_data[future_data['high'] >= sl_price]
    
    # Determinar qué se alcanzó primero
    tp_time = tp_hit['timestamp'].iloc[0] if len(tp_hit) > 0 else None
    sl_time = sl_hit['timestamp'].iloc[0] if len(sl_hit) > 0 else None
    
    if tp_time is None and sl_time is None:
        # EOD force close
        last_bar = future_data.iloc[-1]
        exit_price = last_bar['close']
        if direction == 'LONG':
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - exit_price) / entry_price
        
        return {
            'outcome': 'EOD_CLOSE',
            'hit_time': last_bar['timestamp'],
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'pnl_usd': pnl_pct * entry_price * qty,
            'bars_to_exit': len(future_data)
        }
    
    # Determinar ganador
    if tp_time and sl_time:
        hit_first = 'TP' if tp_time < sl_time else 'SL'
        hit_time = tp_time if hit_first == 'TP' else sl_time
        exit_price = tp_price if hit_first == 'TP' else sl_price
    elif tp_time:
        hit_first = 'TP'
        hit_time = tp_time
        exit_price = tp_price
    else:
        hit_first = 'SL'
        hit_time = sl_time
        exit_price = sl_price
    
    # Calcular PnL
    if direction == 'LONG':
        pnl_pct = (exit_price - entry_price) / entry_price
    else:
        pnl_pct = (entry_price - exit_price) / entry_price
    
    bars_to_exit = len(future_data[future_data['timestamp'] <= hit_time])
    
    return {
        'outcome': hit_first,
        'hit_time': hit_time,
        'exit_price': exit_price,
        'pnl_pct': pnl_pct,
        'pnl_usd': pnl_pct * entry_price * qty,
        'bars_to_exit': bars_to_exit
    }


def validate_all_october():
    """Validar todos los trades de octubre."""
    results = []
    
    # Cargar planes
    start = datetime(2025, 10, 13)
    end = datetime(2025, 10, 31)
    
    current = start
    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue
        
        plan_file = Path(f"reports/intraday/{date_str}/trade_plan_intraday.csv")
        
        if plan_file.exists():
            plan_df = pd.read_csv(plan_file)
            
            for _, trade in plan_df.iterrows():
                ticker = trade['ticker']
                print(f"Validando {date_str} {ticker} {trade.get('direction', 'LONG')}...")
                
                # Cargar intraday
                intraday_df = load_intraday_data(ticker, date_str)
                
                if intraday_df is None or len(intraday_df) == 0:
                    print(f"  ⚠️  No hay datos intraday")
                    result = {
                        'date': date_str,
                        'ticker': ticker,
                        'direction': trade.get('direction', 'LONG'),
                        'entry_price': trade['entry_price'],
                        'tp_price': trade['tp_price'],
                        'sl_price': trade['sl_price'],
                        'qty': trade['qty'],
                        'exposure': trade['exposure'],
                        'prob_win': trade.get('prob_win', 0),
                        'ETTH': trade.get('ETTH', 0),
                        'outcome': 'NO_DATA',
                        'exit_price': None,
                        'pnl_pct': 0,
                        'pnl_usd': 0,
                        'bars_to_exit': 0,
                        'hit_time': None
                    }
                else:
                    validation = validate_trade(trade, intraday_df)
                    result = {
                        'date': date_str,
                        'ticker': ticker,
                        'direction': trade.get('direction', 'LONG'),
                        'entry_price': trade['entry_price'],
                        'tp_price': trade['tp_price'],
                        'sl_price': trade['sl_price'],
                        'qty': trade['qty'],
                        'exposure': trade['exposure'],
                        'prob_win': trade.get('prob_win', 0),
                        'ETTH': trade.get('ETTH', 0),
                        **validation
                    }
                    
                    print(f"  → {validation['outcome']} | PnL: {validation['pnl_pct']:+.2%} (${validation['pnl_usd']:+.2f}) | Bars: {validation['bars_to_exit']}")
                
                results.append(result)
        
        current += timedelta(days=1)
    
    return pd.DataFrame(results)


def print_validation_summary(df):
    """Imprimir resumen de validación."""
    print("\n" + "="*80)
    print("VALIDACIÓN OCTUBRE 2025 - Resultados Reales")
    print("="*80)
    
    total_trades = len(df)
    tp_trades = (df['outcome'] == 'TP').sum()
    sl_trades = (df['outcome'] == 'SL').sum()
    eod_trades = (df['outcome'] == 'EOD_CLOSE').sum()
    no_data = (df['outcome'] == 'NO_DATA').sum()
    
    win_rate = tp_trades / max(total_trades - no_data, 1)
    total_pnl = df['pnl_usd'].sum()
    avg_pnl = df['pnl_usd'].mean()
    avg_win = df[df['pnl_usd'] > 0]['pnl_usd'].mean() if (df['pnl_usd'] > 0).sum() > 0 else 0
    avg_loss = df[df['pnl_usd'] < 0]['pnl_usd'].mean() if (df['pnl_usd'] < 0).sum() > 0 else 0
    
    print(f"\nTotal trades: {total_trades}")
    print(f"  ✅ TP: {tp_trades} ({tp_trades/max(total_trades, 1)*100:.1f}%)")
    print(f"  ❌ SL: {sl_trades} ({sl_trades/max(total_trades, 1)*100:.1f}%)")
    print(f"  ⏰ EOD: {eod_trades} ({eod_trades/max(total_trades, 1)*100:.1f}%)")
    print(f"  ⚠️  No Data: {no_data}")
    
    print(f"\n📊 Métricas de Performance:")
    print(f"  Win Rate: {win_rate:.1%}")
    print(f"  Total PnL: ${total_pnl:,.2f}")
    print(f"  Avg PnL/Trade: ${avg_pnl:,.2f}")
    print(f"  Avg Win: ${avg_win:,.2f}")
    print(f"  Avg Loss: ${avg_loss:,.2f}")
    print(f"  Profit Factor: {abs(avg_win / avg_loss) if avg_loss != 0 else float('inf'):.2f}")
    
    # Comparar prob_win predicha vs real
    valid_df = df[df['outcome'].isin(['TP', 'SL', 'EOD_CLOSE'])].copy()
    if len(valid_df) > 0:
        valid_df['actual_win'] = (valid_df['pnl_usd'] > 0).astype(int)
        avg_pred_prob = valid_df['prob_win'].mean()
        actual_win_rate = valid_df['actual_win'].mean()
        
        print(f"\n🎯 Calibración del Modelo:")
        print(f"  Prob Win Predicha (media): {avg_pred_prob:.1%}")
        print(f"  Win Rate Real: {actual_win_rate:.1%}")
        print(f"  Error: {abs(avg_pred_prob - actual_win_rate):.1%}")
    
    # Detalle por trade
    print(f"\n{'='*80}")
    print("DETALLE DE TRADES")
    print(f"{'='*80}")
    print(f"{'Fecha':<12} {'Ticker':<6} {'Dir':<5} {'Entry':<8} {'Exit':<8} {'Outcome':<10} {'PnL %':<9} {'PnL $':<10} {'Bars':<6}")
    print(f"{'='*80}")
    
    for _, row in df.iterrows():
        exit_str = f"${row['exit_price']:.2f}" if row['exit_price'] else "N/A"
        print(f"{row['date']:<12} {row['ticker']:<6} {row['direction']:<5} "
              f"${row['entry_price']:<7.2f} {exit_str:<8} {row['outcome']:<10} "
              f"{row['pnl_pct']:>+7.2%}  ${row['pnl_usd']:>+8.2f}  {row['bars_to_exit']:<6}")


if __name__ == "__main__":
    print("Validando trades de octubre contra datos reales...")
    df = validate_all_october()
    print_validation_summary(df)
    
    # Guardar
    out_file = "reports/intraday/october_2025_validation.csv"
    df.to_csv(out_file, index=False)
    print(f"\n✅ Validación guardada: {out_file}")
