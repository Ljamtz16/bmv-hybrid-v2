#!/usr/bin/env python3
"""
paper/paper_executor.py
Execute trades from trade_plan into paper broker.
"""

import argparse
import pandas as pd
from pathlib import Path
from paper_broker import place_order, apply_fill, load_state


def execute_trades(trade_plan_path, state_dir, slippage_bps=5, fee_per_trade=0.0):
    """
    Read trade_plan.csv and execute orders in paper broker.
    
    Args:
        trade_plan_path: path to trade_plan.csv
        state_dir: state directory
        slippage_bps: basis points of slippage
        fee_per_trade: fee per trade
    """
    
    # Load trade plan
    trade_plan = pd.read_csv(trade_plan_path)
    trade_plan = trade_plan[trade_plan["qty"] > 0]
    
    if trade_plan.empty:
        print("[WARN] No trades with qty > 0 in plan")
        return
    
    print(f"[INFO] Executing {len(trade_plan)} trades...")
    
    # Place and fill orders
    for idx, row in trade_plan.iterrows():
        ticker = row["ticker"]
        side = str(row["side"]).upper()
        qty = float(row["qty"])
        entry_price = float(row["entry"])
        
        # Apply slippage
        slippage_mult = 1.0 + (slippage_bps / 10000.0) if side == "BUY" else 1.0 - (slippage_bps / 10000.0)
        fill_price = entry_price * slippage_mult
        
        # Place order
        order_id = place_order(state_dir, ticker, side, qty, entry_price, order_type="MKT")
        print(f"  [{ticker}] Order {order_id}: {side} {qty} @ ${entry_price:.2f}")
        
        # Apply fill immediately
        apply_fill(state_dir, order_id, fill_price, fee=fee_per_trade)
        print(f"    Filled @ ${fill_price:.2f}")
    
    # Print final state
    state = load_state(state_dir)
    print(f"\n[OK] Execution complete")
    print(f"  Cash remaining: ${state['cash']:.2f}")


def main():
    ap = argparse.ArgumentParser(description="Execute trades in paper broker")
    ap.add_argument("--trade-plan", required=True, help="Path to trade_plan.csv")
    ap.add_argument("--state-dir", required=True, help="State directory")
    ap.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage in basis points")
    ap.add_argument("--fee-per-trade", type=float, default=0.0, help="Fee per trade")
    
    args = ap.parse_args()
    
    execute_trades(args.trade_plan, args.state_dir, args.slippage_bps, args.fee_per_trade)


if __name__ == "__main__":
    main()
