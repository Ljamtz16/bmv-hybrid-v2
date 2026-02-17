import pandas as pd

df = pd.read_csv('paper_summary.csv')
baseline = df[df['tag'] == 'relaxed_p018_wk42']
momentum = df[df['tag'] == 'with_momentum']

print("\n" + "=" * 60)
print("A/B COMPARISON: Baseline vs Momentum Filter")
print("=" * 60)

print("\nBASELINE (relaxed_p018_wk42 - Sin momentum):")
baseline_trades = int(baseline["num_plan_trades"].sum())
baseline_pnl = baseline["exp_pnl_sum_usd"].sum()
baseline_days_with_trades = baseline[baseline["num_plan_trades"] > 0]
baseline_prob = baseline_days_with_trades["prob_win_mean"].mean()
baseline_spread = baseline_days_with_trades["spread_mean_bps"].mean()
baseline_etth = baseline_days_with_trades["etth_median_days"].mean()

print(f"  Total Trades: {baseline_trades}")
print(f"  E[PnL] Total: ${baseline_pnl:.2f}")
print(f"  Prob Win (mean): {baseline_prob:.3f} ({baseline_prob*100:.1f}%)")
print(f"  Spread Mean: {baseline_spread:.2f} bps")
print(f"  ETTH Median: {baseline_etth:.3f} days ({baseline_etth*6.5:.1f} hours)")
print(f"  E[PnL] per trade: ${baseline_pnl/baseline_trades:.2f}")

print("\nWITH MOMENTUM FILTER:")
momentum_trades = int(momentum["num_plan_trades"].sum())
momentum_pnl = momentum["exp_pnl_sum_usd"].sum()
momentum_days_with_trades = momentum[momentum["num_plan_trades"] > 0]
momentum_prob = momentum_days_with_trades["prob_win_mean"].mean()
momentum_spread = momentum_days_with_trades["spread_mean_bps"].mean()
momentum_etth = momentum_days_with_trades["etth_median_days"].mean()

print(f"  Total Trades: {momentum_trades}")
print(f"  E[PnL] Total: ${momentum_pnl:.2f}")
print(f"  Prob Win (mean): {momentum_prob:.3f} ({momentum_prob*100:.1f}%)")
print(f"  Spread Mean: {momentum_spread:.2f} bps")
print(f"  ETTH Median: {momentum_etth:.3f} days ({momentum_etth*6.5:.1f} hours)")
print(f"  E[PnL] per trade: ${momentum_pnl/momentum_trades:.2f}")

print("\n" + "=" * 60)
print("IMPACT ANALYSIS")
print("=" * 60)

trades_change = (momentum_trades - baseline_trades) / baseline_trades * 100
pnl_change = (momentum_pnl - baseline_pnl) / baseline_pnl * 100
prob_change = (momentum_prob - baseline_prob) * 100
spread_change = (momentum_spread - baseline_spread) / baseline_spread * 100

print(f"  Trade frequency: {trades_change:+.1f}% ({momentum_trades} vs {baseline_trades})")
print(f"  E[PnL] total: {pnl_change:+.1f}% (${momentum_pnl:.2f} vs ${baseline_pnl:.2f})")
print(f"  Prob Win: {prob_change:+.1f}pp ({momentum_prob*100:.1f}% vs {baseline_prob*100:.1f}%)")
print(f"  Spread Mean: {spread_change:+.1f}%")
print(f"  E[PnL] per trade: ${momentum_pnl/momentum_trades:.2f} vs ${baseline_pnl/baseline_trades:.2f}")

print("\n" + "=" * 60)
print("CONCLUSION")
print("=" * 60)

if momentum_prob >= 0.50:
    print("✅ Win rate ≥50% - READY to increase prob_min to 0.30-0.35")
elif momentum_prob >= 0.45:
    print("⚠️  Win rate 45-50% - Consider 2-week validation before adjusting")
else:
    print("❌ Win rate <45% - Continue optimization or recalibration needed")

print(f"\nRecommendation: ", end="")
if momentum_trades >= 5 and momentum_prob >= 0.45:
    print("Momentum filter IMPROVES quality. Recommend keeping it enabled.")
    if momentum_prob >= 0.50:
        print("Next: Run 2-week validation to collect 15-20 trades, then increase prob_min to 0.30")
    else:
        print("Next: Run 2-week validation with current settings to confirm ≥50% win rate")
else:
    print("Need more data. Consider lowering p_tp_before_sl_min to 0.15 for higher frequency.")

print("=" * 60 + "\n")
