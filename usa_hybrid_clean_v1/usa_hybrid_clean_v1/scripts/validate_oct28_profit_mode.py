"""
Validate Oct 28 Profit Mode trades (2 trades: NVDA LONG + AMD SHORT)
"""
import pandas as pd
from pathlib import Path

# Load plan
plan = pd.read_csv("reports/intraday/2025-10-28/trade_plan_intraday.csv")

print("=" * 80)
print("VALIDACIÓN PROFIT MODE - Oct 28, 2025 (2 TRADES)")
print("=" * 80)
print()

total_pnl = 0

for idx, trade in plan.iterrows():
    ticker = trade['ticker']
    direction = trade['direction']
    entry_time = pd.to_datetime(trade['timestamp'])
    entry_price = trade['entry_price']
    tp_price = trade['tp_price']
    sl_price = trade['sl_price']
    exposure = trade['exposure']
    
    print(f"\n{'='*80}")
    print(f"Trade #{idx+1}: {ticker} {direction}")
    print(f"{'='*80}")
    print(f"Entry: ${entry_price:.2f} @ {entry_time}")
    print(f"TP: ${tp_price:.2f} (+2.0%), SL: ${sl_price:.2f} (-0.4%)")
    print(f"Exposure: ${exposure:.2f}")
    print(f"Prob win: {trade['prob_win']*100:.1f}%, P(TP<SL): {trade['p_tp_before_sl']*100:.1f}%")
    print(f"E[PnL]: ${trade['exp_pnl_pct'] * exposure:.2f}")
    print()
    
    # Load intraday data
    intraday_files = list(Path(f"data/us/intraday/{ticker}").glob(f"{ticker}_*.csv"))
    
    if not intraday_files:
        print(f"⚠️  No intraday data for {ticker}")
        continue
    
    # Find file covering Oct 28
    target_date = entry_time.date()
    best_file = None
    
    for file_path in intraday_files:
        parts = file_path.stem.split('_')
        if len(parts) >= 3:
            file_start = pd.to_datetime(parts[1]).date()
            file_end = pd.to_datetime(parts[2]).date()
            if file_start <= target_date <= file_end:
                best_file = file_path
                break
    
    if best_file is None:
        best_file = sorted(intraday_files)[-1]
    
    print(f"📂 Loading: {best_file.name}")
    
    df = pd.read_csv(best_file, header=[0, 1], index_col=0, parse_dates=True)
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
    hit_found = False
    for bar_idx, bar in data_after_entry.iterrows():
        high = bar['High']
        low = bar['Low']
        close = bar['Close']
        
        if direction == 'LONG':
            if high >= tp_price:
                pnl_pct = (tp_price - entry_price) / entry_price
                pnl_usd = pnl_pct * exposure
                print(f"\n✅ TP HIT @ {bar_idx}")
                print(f"   Exit price: ${tp_price:.2f}")
                print(f"   PnL: {pnl_pct*100:+.2f}% (${pnl_usd:+.2f})")
                print(f"   Bars held: {list(data_after_entry.index).index(bar_idx) + 1}")
                total_pnl += pnl_usd
                hit_found = True
                break
            elif low <= sl_price:
                pnl_pct = (sl_price - entry_price) / entry_price
                pnl_usd = pnl_pct * exposure
                print(f"\n❌ SL HIT @ {bar_idx}")
                print(f"   Exit price: ${sl_price:.2f}")
                print(f"   PnL: {pnl_pct*100:+.2f}% (${pnl_usd:+.2f})")
                print(f"   Bars held: {list(data_after_entry.index).index(bar_idx) + 1}")
                total_pnl += pnl_usd
                hit_found = True
                break
        else:  # SHORT
            if low <= tp_price:
                pnl_pct = (entry_price - tp_price) / entry_price
                pnl_usd = pnl_pct * exposure
                print(f"\n✅ TP HIT @ {bar_idx}")
                print(f"   Exit price: ${tp_price:.2f}")
                print(f"   PnL: {pnl_pct*100:+.2f}% (${pnl_usd:+.2f})")
                print(f"   Bars held: {list(data_after_entry.index).index(bar_idx) + 1}")
                total_pnl += pnl_usd
                hit_found = True
                break
            elif high >= sl_price:
                pnl_pct = (entry_price - sl_price) / entry_price
                pnl_usd = pnl_pct * exposure
                print(f"\n❌ SL HIT @ {bar_idx}")
                print(f"   Exit price: ${sl_price:.2f}")
                print(f"   PnL: {pnl_pct*100:+.2f}% (${pnl_usd:+.2f})")
                print(f"   Bars held: {list(data_after_entry.index).index(bar_idx) + 1}")
                total_pnl += pnl_usd
                hit_found = True
                break
    
    if not hit_found:
        # No TP/SL hit - EOD close
        last_close = data_after_entry.iloc[-1]['Close']
        if direction == 'LONG':
            pnl_pct = (last_close - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - last_close) / entry_price
        pnl_usd = pnl_pct * exposure
        print(f"\n⏰ EOD CLOSE @ {data_after_entry.index[-1]}")
        print(f"   Exit price: ${last_close:.2f}")
        print(f"   PnL: {pnl_pct*100:+.2f}% (${pnl_usd:+.2f})")
        print(f"   Bars held: {len(data_after_entry)}")
        total_pnl += pnl_usd

print(f"\n{'='*80}")
print("💰 RESUMEN FINAL")
print(f"{'='*80}")
print(f"Total trades: {len(plan)}")
print(f"PnL total: ${total_pnl:+.2f}")
print(f"PnL promedio: ${total_pnl/len(plan):+.2f} por trade")
print(f"E[PnL] predicho: ${plan['exp_pnl_pct'].sum() * plan['exposure'].mean():.2f}")
print()
