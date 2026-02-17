#!/usr/bin/env python3
"""
paper/paper_broker.py
Minimal paper broker with persistent state on disk.
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
import argparse


def load_state(state_dir):
    """Load broker state from disk."""
    state_file = Path(state_dir) / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return {"cash": 1000.0, "equity": 1000.0, "timestamp": datetime.now().isoformat()}


def save_state(state_dir, state):
    """Save broker state to disk."""
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    state_file = Path(state_dir) / "state.json"
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def place_order(state_dir, ticker, side, qty, requested_price, order_type="MKT"):
    """Place an order and return order_id."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    
    orders_file = state_dir / "orders.csv"
    
    # Load existing orders
    if orders_file.exists():
        orders_df = pd.read_csv(orders_file)
        order_id = int(orders_df["order_id"].max()) + 1
    else:
        orders_df = pd.DataFrame()
        order_id = 1
    
    new_order = {
        "order_id": order_id,
        "ts": datetime.now().isoformat(),
        "ticker": ticker,
        "side": side,
        "qty": qty,
        "order_type": order_type,
        "requested_price": requested_price,
        "status": "NEW",
    }
    
    orders_df = pd.concat([orders_df, pd.DataFrame([new_order])], ignore_index=True)
    orders_df.to_csv(orders_file, index=False)
    
    return order_id


def apply_fill(state_dir, order_id, fill_price, fee=0.0):
    """Apply a fill to an order."""
    state_dir = Path(state_dir)
    
    # Load order
    orders_file = state_dir / "orders.csv"
    orders_df = pd.read_csv(orders_file)
    order = orders_df[orders_df["order_id"] == order_id].iloc[0]
    
    # Create fill
    fills_file = state_dir / "fills.csv"
    if fills_file.exists():
        fills_df = pd.read_csv(fills_file)
        fill_id = int(fills_df["fill_id"].max()) + 1
    else:
        fills_df = pd.DataFrame()
        fill_id = 1
    
    new_fill = {
        "fill_id": fill_id,
        "order_id": order_id,
        "ts": datetime.now().isoformat(),
        "ticker": order["ticker"],
        "side": order["side"],
        "qty": order["qty"],
        "fill_price": fill_price,
        "fee": fee,
    }
    
    fills_df = pd.concat([fills_df, pd.DataFrame([new_fill])], ignore_index=True)
    fills_df.to_csv(fills_file, index=False)
    
    # Update order status
    orders_df.loc[orders_df["order_id"] == order_id, "status"] = "FILLED"
    orders_df.to_csv(orders_file, index=False)
    
    # Update state (deduct cash)
    state = load_state(state_dir)
    cost = fill_price * order["qty"] + fee
    if order["side"] == "BUY":
        state["cash"] -= cost
    else:
        state["cash"] += cost
    state["timestamp"] = datetime.now().isoformat()
    save_state(state_dir, state)
    
    return fill_id


def mark_to_market(state_dir, price_map, ts=None):
    """
    Update positions to market prices and record snapshot.
    
    Args:
        state_dir: state directory
        price_map: dict {ticker: last_price}
        ts: timestamp (default now)
    """
    state_dir = Path(state_dir)
    if ts is None:
        ts = datetime.now().isoformat()
    
    # Load fills to compute positions
    fills_file = state_dir / "fills.csv"
    if not fills_file.exists():
        return
    
    fills_df = pd.read_csv(fills_file)
    
    # Compute positions by ticker
    positions_list = []
    total_unrealized = 0.0
    total_realized = 0.0
    
    for ticker in fills_df["ticker"].unique():
        ticker_fills = fills_df[fills_df["ticker"] == ticker]
        
        qty = 0
        avg_price = 0.0
        cost_basis = 0.0
        
        for _, fill in ticker_fills.iterrows():
            if fill["side"] == "BUY":
                new_qty = qty + fill["qty"]
                cost_basis = (qty * avg_price + fill["qty"] * fill["fill_price"]) / new_qty if new_qty > 0 else 0
                qty = new_qty
                avg_price = cost_basis
            else:
                realized = (fill["fill_price"] - avg_price) * fill["qty"]
                total_realized += realized
                qty -= fill["qty"]
        
        if qty > 0:
            last_price = price_map.get(ticker, avg_price)
            unrealized = (last_price - avg_price) * qty
            total_unrealized += unrealized
            
            positions_list.append({
                "ts": ts,
                "ticker": ticker,
                "qty": qty,
                "avg_price": avg_price,
                "last_price": last_price,
                "unrealized_pnl": unrealized,
            })
    
    # Save positions snapshot
    pos_df = pd.DataFrame(positions_list)
    pos_file = state_dir / "positions.csv"
    pos_df.to_csv(pos_file, index=False)
    
    # Update state equity
    state = load_state(state_dir)
    state["equity"] = state["cash"] + total_unrealized + total_realized
    state["unrealized_pnl"] = total_unrealized
    state["realized_pnl"] = total_realized
    state["timestamp"] = ts
    save_state(state_dir, state)
    
    # Append to ledger
    ledger_file = state_dir / "pnl_ledger.csv"
    ledger_row = {
        "ts": ts,
        "cash": state["cash"],
        "equity": state["equity"],
        "unrealized_pnl": total_unrealized,
        "realized_pnl": total_realized,
    }
    
    if ledger_file.exists():
        ledger_df = pd.read_csv(ledger_file)
        ledger_df = pd.concat([ledger_df, pd.DataFrame([ledger_row])], ignore_index=True)
    else:
        ledger_df = pd.DataFrame([ledger_row])
    
    ledger_df.to_csv(ledger_file, index=False)


def init_broker(state_dir, cash=1000.0):
    """Initialize broker state."""
    state = {
        "cash": cash,
        "equity": cash,
        "timestamp": datetime.now().isoformat(),
    }
    save_state(state_dir, state)
    print(f"[OK] Broker initialized at {state_dir} with ${cash}")


def status(state_dir):
    """Print broker status."""
    state = load_state(state_dir)
    print(f"\n=== BROKER STATUS ===")
    print(f"Cash:       ${state.get('cash', 0.0):.2f}")
    print(f"Equity:     ${state.get('equity', 0.0):.2f}")
    print(f"Timestamp:  {state.get('timestamp')}")
    
    # Count open positions
    pos_file = Path(state_dir) / "positions.csv"
    if pos_file.exists():
        pos_df = pd.read_csv(pos_file)
        print(f"Open pos:   {len(pos_df)}")
        if len(pos_df) > 0:
            for _, pos in pos_df.iterrows():
                print(f"  {pos['ticker']}: {pos['qty']:.0f} @ ${pos['avg_price']:.2f} (unrealized: ${pos['unrealized_pnl']:.2f})")
    else:
        print(f"Open pos:   0")
    print()


def main():
    ap = argparse.ArgumentParser(description="Paper broker state management")
    subparsers = ap.add_subparsers(dest="command", help="Command")
    
    init_parser = subparsers.add_parser("init", help="Initialize broker")
    init_parser.add_argument("--cash", type=float, default=1000.0)
    init_parser.add_argument("--state-dir", required=True)
    
    status_parser = subparsers.add_parser("status", help="Print status")
    status_parser.add_argument("--state-dir", required=True)
    
    args = ap.parse_args()
    
    if args.command == "init":
        init_broker(args.state_dir, args.cash)
    elif args.command == "status":
        status(args.state_dir)


if __name__ == "__main__":
    main()
