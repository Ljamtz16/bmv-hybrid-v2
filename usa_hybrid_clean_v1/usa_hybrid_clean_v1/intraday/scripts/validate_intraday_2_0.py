"""
Validate Intraday 2.0 trade (Oct 28 NVDA)
"""
import pandas as pd
from pathlib import Path

# Load plan
plan = pd.read_csv("reports/intraday/2025-10-28/trade_plan_intraday.csv")

print("=" * 80)
print("VALIDACIÓN INTRADAY 2.0 - Oct 28, 2025")
print("=" * 80)
print("Config: TP=1.2%, SL=0.35%, R:R=3.4:1")
print()

for idx, trade in plan.iterrows():
    ticker = trade['ticker']
    direction = trade['direction']
    entry_time = pd.to_datetime(trade['timestamp'])
    entry_price = trade['entry_price']
    tp_price = trade['tp_price']
    sl_price = trade['sl_price']
    exposure = trade['exposure']
    
    print(f"Trade #{idx+1}: {ticker} {direction}")
    print(f"Entry: ${entry_price:.2f} @ {entry_time}")
    print(f"TP: ${tp_price:.2f} (+1.2%), SL: ${sl_price:.2f} (-0.35%)")
    print(f"Exposure: ${exposure:.2f}")
    print(f"Prob win: {trade['prob_win']*100:.1f}%, P(TP<SL): {trade['p_tp_before_sl']*100:.1f}%")
    print(f"ETTH: {trade['ETTH']:.2f}d ({trade['ETTH']*6.5:.1f}h)")
    print(f"E[PnL]: ${trade['exp_pnl_pct'] * exposure:.2f}")
    print()
    
    # Load intraday data
    intraday_file = f"data/us/intraday/{ticker}/{ticker}_2025-10-13_2025-11-01_15m.csv"
    
    if not Path(intraday_file).exists():
        print(f"⚠️  No intraday data")
        continue
    
    df = pd.read_csv(intraday_file, header=[0, 1], index_col=0, parse_dates=True)
    df.columns = df.columns.droplevel(1)
    df.index = pd.to_datetime(df.index)
    
    # Filter from entry time onwards
    trade_date = entry_time.date()
    mask = (df.index.date == trade_date) & (df.index >= entry_time)
    data_after_entry = df[mask]
    
    if len(data_after_entry) == 0:
        print("⚠️  No data after entry")
        continue
    
    print(f"📊 Bars after entry: {len(data_after_entry)}")
    
    # Check for TP/SL hits
    hit_found = False
    for bar_idx, (bar_time, bar) in enumerate(data_after_entry.iterrows(), 1):
        high = bar['High']
        low = bar['Low']
        
        if direction == 'LONG':
            if high >= tp_price:
                pnl_pct = (tp_price - entry_price) / entry_price
                pnl_usd = pnl_pct * exposure
                print(f"\n✅ TP HIT @ bar {bar_idx} ({bar_time})")
                print(f"   High: ${high:.2f} >= TP ${tp_price:.2f}")
                print(f"   PnL: {pnl_pct*100:+.2f}% (${pnl_usd:+.2f})")
                print(f"   Tiempo: {bar_idx * 15} minutos ({bar_idx * 15 / 60:.1f}h)")
                hit_found = True
                break
            elif low <= sl_price:
                pnl_pct = (sl_price - entry_price) / entry_price
                pnl_usd = pnl_pct * exposure
                print(f"\n❌ SL HIT @ bar {bar_idx} ({bar_time})")
                print(f"   Low: ${low:.2f} <= SL ${sl_price:.2f}")
                print(f"   PnL: {pnl_pct*100:+.2f}% (${pnl_usd:+.2f})")
                print(f"   Tiempo: {bar_idx * 15} minutos ({bar_idx * 15 / 60:.1f}h)")
                hit_found = True
                break
    
    if not hit_found:
        # EOD close
        last_close = data_after_entry.iloc[-1]['Close']
        pnl_pct = (last_close - entry_price) / entry_price
        pnl_usd = pnl_pct * exposure
        print(f"\n⏰ EOD CLOSE @ {data_after_entry.index[-1]}")
        print(f"   Close: ${last_close:.2f}")
        print(f"   PnL: {pnl_pct*100:+.2f}% (${pnl_usd:+.2f})")
        print(f"   Tiempo: {len(data_after_entry) * 15} minutos ({len(data_after_entry) * 15 / 60:.1f}h)")
    
    print()
    
    # Compare with old config
    print("📊 COMPARACIÓN:")
    print(f"   Intraday 1.0 (TP=2.0%, SL=0.4%): SL hit -$1.60 (15 min)")
    print(f"   Intraday 2.0 (TP=1.2%, SL=0.35%): {'TP hit' if hit_found and 'TP' in locals() else 'EOD/SL'}")
    print()
