#!/usr/bin/env python3
"""
paper/test_paper_integration.py
Integration test suite for paper trading system.
"""

import argparse
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime


def test_intraday_data():
    """Test intraday_data.py exists and imports."""
    try:
        from intraday_data import download_intraday
        print("✅ intraday_data.download_intraday OK")
        return True
    except Exception as e:
        print(f"❌ intraday_data error: {e}")
        return False


def test_intraday_simulator():
    """Test intraday_simulator.py exists and imports."""
    try:
        from intraday_simulator import simulate_trades
        print("✅ intraday_simulator.simulate_trades OK")
        return True
    except Exception as e:
        print(f"❌ intraday_simulator error: {e}")
        return False


def test_metrics():
    """Test metrics.py exists and imports."""
    try:
        from metrics import summary_stats, equity_curve, max_drawdown, cagr
        print("✅ metrics imports OK")
        return True
    except Exception as e:
        print(f"❌ metrics error: {e}")
        return False


def test_paper_broker():
    """Test paper_broker.py exists and imports."""
    try:
        from paper_broker import load_state, save_state, place_order, apply_fill
        print("✅ paper_broker imports OK")
        return True
    except Exception as e:
        print(f"❌ paper_broker error: {e}")
        return False


def test_paper_executor():
    """Test paper_executor.py exists and imports."""
    try:
        from paper_executor import execute_trade_plan
        print("✅ paper_executor.execute_trade_plan OK")
        return True
    except Exception as e:
        print(f"❌ paper_executor error: {e}")
        return False


def test_paper_reconciler():
    """Test paper_reconciler.py exists and imports."""
    try:
        from paper_reconciler import mark_to_market_live
        print("✅ paper_reconciler.mark_to_market_live OK")
        return True
    except Exception as e:
        print(f"❌ paper_reconciler error: {e}")
        return False


def test_dashboard():
    """Test dashboard exists and imports."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "dashboards"))
        from dashboard_trade_monitor import generate_html
        print("✅ dashboard_trade_monitor.generate_html OK")
        return True
    except Exception as e:
        print(f"❌ dashboard error: {e}")
        return False


def test_wf_month():
    """Test wf_paper_month.py exists and imports."""
    try:
        from wf_paper_month import get_weekday_range, get_asof_date
        print("✅ wf_paper_month imports OK")
        return True
    except Exception as e:
        print(f"❌ wf_paper_month error: {e}")
        return False


def test_directory_structure():
    """Test that all required directories exist."""
    dirs = [
        Path("paper"),
        Path("dashboards"),
        Path("data/intraday_1h"),
        Path("paper_state"),
    ]
    
    all_ok = True
    for d in dirs:
        if d.exists():
            print(f"✅ {d}/ exists")
        else:
            print(f"❌ {d}/ missing")
            all_ok = False
    
    return all_ok


def test_trade_plan_mock():
    """Test creating mock trade plan and loading it."""
    try:
        mock_plan = pd.DataFrame({
            "ticker": ["AMD", "XOM"],
            "qty": [10, 5],
            "entry_price": [150.0, 95.0],
            "prob_win": [0.65, 0.58],
            "etth_days": [2.5, 5.0],
        })
        
        tmp_csv = Path("test_trade_plan.csv")
        mock_plan.to_csv(tmp_csv, index=False)
        
        # Load it back
        loaded = pd.read_csv(tmp_csv)
        assert len(loaded) == 2, "Trade plan row count mismatch"
        assert "qty" in loaded.columns, "Missing qty column"
        
        tmp_csv.unlink()  # Clean up
        print("✅ Trade plan mock OK")
        return True
    except Exception as e:
        print(f"❌ Trade plan mock error: {e}")
        return False


def main():
    ap = argparse.ArgumentParser(description="Integration tests for paper trading")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    
    print("=" * 60)
    print("PAPER TRADING INTEGRATION TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("Directory Structure", test_directory_structure),
        ("Intraday Data", test_intraday_data),
        ("Intraday Simulator", test_intraday_simulator),
        ("Metrics", test_metrics),
        ("Paper Broker", test_paper_broker),
        ("Paper Executor", test_paper_executor),
        ("Paper Reconciler", test_paper_reconciler),
        ("Dashboard", test_dashboard),
        ("WF Month", test_wf_month),
        ("Trade Plan Mock", test_trade_plan_mock),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n[{name}]")
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"❌ {name} exception: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    pct = 100 * passed / total
    
    print(f"RESULTS: {passed}/{total} ({pct:.0f}%)")
    
    if all(results):
        print("✅ ALL TESTS PASSED")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
