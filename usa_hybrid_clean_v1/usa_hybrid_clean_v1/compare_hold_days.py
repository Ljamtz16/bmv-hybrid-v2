#!/usr/bin/env python3
"""
Compare impact of max_hold_days on trading performance.
"""

import pandas as pd
from pathlib import Path

def load_results(evidence_dir):
    """Load all_trades.csv from evidence directory."""
    trades_file = Path(evidence_dir) / "all_trades.csv"
    if not trades_file.exists():
        return None
    return pd.read_csv(trades_file)

def summarize(df, label):
    """Print summary statistics."""
    if df is None or df.empty:
        print(f"{label}: No data")
        return None
    
    total_pnl = df["pnl"].sum()
    win_rate = (df["pnl"] > 0).mean() * 100
    tp_count = (df["outcome"] == "TP").sum()
    sl_count = (df["outcome"] == "SL").sum()
    to_count = (df["outcome"] == "TIMEOUT").sum()
    
    # Hold time stats
    df_copy = df.copy()
    df_copy["entry_time"] = pd.to_datetime(df_copy["entry_time"])
    df_copy["exit_time"] = pd.to_datetime(df_copy["exit_time"])
    df_copy["hold_hours_calc"] = (df_copy["exit_time"] - df_copy["entry_time"]).dt.total_seconds() / 3600
    
    return {
        "label": label,
        "trades": len(df),
        "pnl": total_pnl,
        "win_rate": win_rate,
        "tp": tp_count,
        "sl": sl_count,
        "timeout": to_count,
        "avg_hold_hours": df_copy["hold_hours_calc"].mean(),
        "max_hold_hours": df_copy["hold_hours_calc"].max(),
    }

def main():
    print("=" * 80)
    print("COMPARISON: max_hold_days & TP/SL Tuning Impact on Performance")
    print("=" * 80)
    
    # Load results
    intraday_old = load_results("evidence/paper_dec_2025_INTRADAY_old")        # max_hold=1, TP=2%, SL=1.2%
    intraday_tuned = load_results("evidence/paper_dec_2025_INTRADAY_TUNED_old")  # max_hold=1, TP=0.8%, SL=0.5%
    two_day = load_results("evidence/paper_dec_2025_FIXED_old")                # max_hold=2, TP=2%, SL=1.2%
    
    # Summarize
    stats = []
    for df, label in [
        (two_day, "Swing (2d, TP=2%, SL=1.2%)"),
        (intraday_old, "Intraday (1d, TP=2%, SL=1.2%)"),
        (intraday_tuned, "Intraday Tuned (1d, TP=0.8%, SL=0.5%)")
    ]:
        s = summarize(df, label)
        if s:
            stats.append(s)
    
    if len(stats) < 2:
        print("\n[ERROR] Missing data. Ensure runs completed.")
        return
    
    # Print comparison table
    print("\n" + "=" * 90)
    print("RESULTS SUMMARY")
    print("=" * 90)
    
    print(f"\n{'Metric':<25} {'Swing 2d':<20} {'Intraday 1d':<20} {'Intraday Tuned':<20}")
    print("-" * 90)
    
    for key in ["trades", "pnl", "win_rate", "tp", "sl", "timeout", "avg_hold_hours"]:
        vals = [s.get(key, 0) for s in stats]
        
        if key == "pnl":
            print(f"{key.upper():<25} ${vals[0]:>7.2f}             ${vals[1]:>7.2f}             ${vals[2]:>7.2f}" if len(vals) > 2 else f"{key.upper():<25} ${vals[0]:>7.2f}             ${vals[1]:>7.2f}")
        elif key == "win_rate":
            print(f"{key.replace('_', ' ').title():<25} {vals[0]:>6.1f}%              {vals[1]:>6.1f}%              {vals[2]:>6.1f}%" if len(vals) > 2 else f"{key.replace('_', ' ').title():<25} {vals[0]:>6.1f}%              {vals[1]:>6.1f}%")
        elif key in ["avg_hold_hours"]:
            print(f"{key.replace('_', ' ').title():<25} {vals[0]:>6.1f}h              {vals[1]:>6.1f}h              {vals[2]:>6.1f}h" if len(vals) > 2 else f"{key.replace('_', ' ').title():<25} {vals[0]:>6.1f}h              {vals[1]:>6.1f}h")
        else:
            print(f"{key.upper():<25} {vals[0]:>8}             {vals[1]:>8}             {vals[2]:>8}" if len(vals) > 2 else f"{key.upper():<25} {vals[0]:>8}             {vals[1]:>8}")
    
    # Outcome distribution comparison
    print("\n" + "=" * 90)
    print("OUTCOME DISTRIBUTION")
    print("=" * 90)
    
    for stat in stats:
        total = stat["trades"]
        tp_pct = stat["tp"] / total * 100
        sl_pct = stat["sl"] / total * 100
        to_pct = stat["timeout"] / total * 100
        
        print(f"\n{stat['label']}:")
        print(f"  TP:      {stat['tp']:>3} ({tp_pct:>5.1f}%)")
        print(f"  SL:      {stat['sl']:>3} ({sl_pct:>5.1f}%)")
        print(f"  TIMEOUT: {stat['timeout']:>3} ({to_pct:>5.1f}%)")
    
    # Key insights
    print("\n" + "=" * 90)
    print("KEY INSIGHTS")
    print("=" * 90)
    
    if len(stats) >= 3:
        print(f"\n📊 P&L Ranking:")
        sorted_by_pnl = sorted(stats, key=lambda x: x["pnl"], reverse=True)
        for i, stat in enumerate(sorted_by_pnl, 1):
            print(f"  {i}. {stat['label']:<40} ${stat['pnl']:>7.2f}")
        
        print(f"\n📊 Win Rate Ranking:")
        sorted_by_wr = sorted(stats, key=lambda x: x["win_rate"], reverse=True)
        for i, stat in enumerate(sorted_by_wr, 1):
            print(f"  {i}. {stat['label']:<40} {stat['win_rate']:>6.1f}%")
        
        print(f"\n📊 TP Hit Rate (resolution efficiency):")
        for stat in stats:
            tp_rate = stat["tp"] / stat["trades"] * 100
            print(f"  {stat['label']:<40} {stat['tp']:>3} trades ({tp_rate:>5.1f}%)")
        
        print(f"\n📊 TIMEOUT Rate (capital inefficiency):")
        for stat in stats:
            to_rate = stat["timeout"] / stat["trades"] * 100
            print(f"  {stat['label']:<40} {stat['timeout']:>3} trades ({to_rate:>5.1f}%)")
        
        print(f"\n✅ WINNER: {sorted_by_pnl[0]['label']}")
        print(f"   - Best P&L: ${sorted_by_pnl[0]['pnl']:.2f}")
        print(f"   - TP Hit Rate: {sorted_by_pnl[0]['tp'] / sorted_by_pnl[0]['trades'] * 100:.1f}%")
        print(f"   - TIMEOUT: {sorted_by_pnl[0]['timeout'] / sorted_by_pnl[0]['trades'] * 100:.1f}% (lower is better)")
        
        best = sorted_by_pnl[0]
        print(f"\n💡 Key Advantage:")
        if "Tuned" in best['label']:
            print(f"   TP=0.8% & SL=0.5% matched to intraday volatility")
            print(f"   Result: {best['tp']} TPs vs {stats[1]['tp']} with aggressive TP=2%")
            print(f"   TIMEOUT reduced from {stats[1]['timeout']} → {best['timeout']} (better capital efficiency)")
        elif "Swing" in best['label']:
            print(f"   2-day hold gives more time to reach TP=2%")
            print(f"   Result: {best['tp']} TPs vs {stats[1]['tp']} with 1-day constraint")
    else:
        pnl_1d = stats[0]["pnl"]
        pnl_2d = stats[1]["pnl"]
        wr_1d = stats[0]["win_rate"]
        wr_2d = stats[1]["win_rate"]
        
        if pnl_2d > pnl_1d:
            improvement = (pnl_2d - pnl_1d) / pnl_1d * 100 if pnl_1d != 0 else float('inf')
            print(f"\n✅ 2-day hold OUTPERFORMS 1-day by ${pnl_2d - pnl_1d:.2f} (+{improvement:.1f}%)")
            print(f"   Reason: More time to hit TP (TP count: {stats[1]['tp']} vs {stats[0]['tp']})")
        else:
            decline = (pnl_1d - pnl_2d) / pnl_1d * 100 if pnl_1d != 0 else 0
            print(f"\n⚠️  1-day hold OUTPERFORMS 2-day by ${pnl_1d - pnl_2d:.2f} (+{decline:.1f}%)")
            print(f"   Reason: Avoiding overnight risk (SL count: {stats[0]['sl']} vs {stats[1]['sl']})")
        
        if wr_2d > wr_1d:
            print(f"✅ 2-day Win Rate higher by {wr_2d - wr_1d:.1f}pp")
        else:
            print(f"⚠️  1-day Win Rate higher by {wr_1d - wr_2d:.1f}pp")
        
        timeout_delta = stats[1]["timeout"] - stats[0]["timeout"]
        if timeout_delta < 0:
            print(f"✅ 2-day has FEWER timeouts ({timeout_delta} trades), more TP/SL resolution")
        else:
            print(f"⚠️  2-day has MORE timeouts (+{timeout_delta} trades), less decisive outcomes")
    
    print("\n" + "=" * 90)

if __name__ == "__main__":
    main()
