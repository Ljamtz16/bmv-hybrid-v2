"""
Validate Oct 23 Profit Mode trade
"""
import pandas as pd
from pathlib import Path

# Load plan
plan = pd.read_csv("reports/intraday/2025-10-23/trade_plan_intraday.csv")
print("=" * 80)
print("VALIDACIÓN PROFIT MODE - Oct 23, 2025")
print("=" * 80)
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
    print(f"TP: ${tp_price:.2f} (+2.0%), SL: ${sl_price:.2f} (-0.4%)")
    print(f"Exposure: ${exposure:.2f}")
    print(f"Prob win: {trade['prob_win']*100:.1f}%, P(TP<SL): {trade['p_tp_before_sl']*100:.1f}%")
    print()
    
    # Load intraday data
    intraday_file = f"data/us/intraday/{ticker}/{ticker}_2025-10-20_2025-10-25_15m.csv"
    if not Path(intraday_file).exists():
        print(f"⚠️  No intraday data: {intraday_file}")
        continue
    
    df = pd.read_csv(intraday_file, header=[0, 1], index_col=0, parse_dates=True)
    df.columns = df.columns.droplevel(1)
    df.index = pd.to_datetime(df.index)
    
    # Filter from entry time onwards (same day)
    trade_date = entry_time.date()
    mask = (df.index.date == trade_date) & (df.index >= entry_time)
    data_after_entry = df[mask]
    
    if len(data_after_entry) == 0:
        print("⚠️  No data after entry time")
        continue
    
    print(f"📊 Bars after entry: {len(data_after_entry)}")
    
    # Check for TP/SL hits
    for bar_idx, bar in data_after_entry.iterrows():
        high = bar['High']
        low = bar['Low']
        close = bar['Close']
        
        if direction == 'LONG':
            if high >= tp_price:
                pnl_pct = (tp_price - entry_price) / entry_price
                pnl_usd = pnl_pct * exposure
                print(f"✅ TP HIT @ {bar_idx}")
                print(f"   Price: ${tp_price:.2f}")
                print(f"   PnL: {pnl_pct*100:+.2f}% (${pnl_usd:+.2f})")
                break
            elif low <= sl_price:
                pnl_pct = (sl_price - entry_price) / entry_price
                pnl_usd = pnl_pct * exposure
                print(f"❌ SL HIT @ {bar_idx}")
                print(f"   Price: ${sl_price:.2f}")
                print(f"   PnL: {pnl_pct*100:+.2f}% (${pnl_usd:+.2f})")
                break
        else:  # SHORT
            if low <= tp_price:
                pnl_pct = (entry_price - tp_price) / entry_price
                pnl_usd = pnl_pct * exposure
                print(f"✅ TP HIT @ {bar_idx}")
                print(f"   Price: ${tp_price:.2f}")
                print(f"   PnL: {pnl_pct*100:+.2f}% (${pnl_usd:+.2f})")
                break
            elif high >= sl_price:
                pnl_pct = (entry_price - sl_price) / entry_price
                pnl_usd = pnl_pct * exposure
                print(f"❌ SL HIT @ {bar_idx}")
                print(f"   Price: ${sl_price:.2f}")
                print(f"   PnL: {pnl_pct*100:+.2f}% (${pnl_usd:+.2f})")
                break
    else:
        # No TP/SL hit - EOD close
        last_close = data_after_entry.iloc[-1]['Close']
        if direction == 'LONG':
            pnl_pct = (last_close - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - last_close) / entry_price
        pnl_usd = pnl_pct * exposure
        print(f"⏰ EOD CLOSE @ {data_after_entry.index[-1]}")
        print(f"   Price: ${last_close:.2f}")
        print(f"   PnL: {pnl_pct*100:+.2f}% (${pnl_usd:+.2f})")
    
    print()
