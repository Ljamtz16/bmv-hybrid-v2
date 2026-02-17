#!/usr/bin/env python3
"""Test if the snapshot is loading history correctly"""
import sys
sys.path.insert(0, '.')

from dashboard_unified import load_history_trades, build_trade_snapshot

# Test load_history_trades()
trades = load_history_trades()
print(f'[TEST] load_history_trades() returned {len(trades)} trades')
if trades:
    print(f'[TEST] First trade keys: {list(trades[0].keys())}')
    print(f'[TEST] Sample trade (first): {trades[0]}')

# Test build_trade_snapshot()
snapshot = build_trade_snapshot()
history_count = len(snapshot.get("history", []))
active_count = len(snapshot.get("active", []))
print(f'[TEST] Snapshot has {history_count} history trades')
print(f'[TEST] Snapshot has {active_count} active trades')
summary = snapshot.get("summary", {})
print(f'[TEST] Summary: total_trades={summary.get("total_trades")}, pnl_total={summary.get("pnl_total")}, win_rate={summary.get("win_rate")}')

# Now test the health endpoint
print("\n[HEALTH CHECK]")
print(f"History trades count: {len(snapshot.get('history', []))}")
empty_state_history = len(snapshot.get("history", [])) == 0
print(f"empty_state.history_trades (True=empty): {empty_state_history}")
