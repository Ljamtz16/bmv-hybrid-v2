import pandas as pd
from ..execution.hybrid_v2 import execute_hybrid_v2

def scan_tau_pnl(signals_df, side, h1_map, d1_map, grid, exec_cfg):
    best_tau, best_pnl = None, -1e18
    rows = []
    for tau in grid:
        pnl_sum = 0.0; ntr = 0
        sub = signals_df[(signals_df["side"]==side) & (signals_df["prob"]>=tau)]
        for _, s in sub.iterrows():
            res = execute_hybrid_v2(
                h1_map, d1_map, s["ticker"], s["date"], s["side"], s["prob"],
                tp_mult=exec_cfg["tp_atr_mult"], sl_mult=exec_cfg["sl_atr_mult"],
                commission=exec_cfg["commission_pct"], slippage=exec_cfg["slippage_pct"],
                max_holding_days=exec_cfg["max_holding_days"],
                trail_atr_mult=exec_cfg["trail_atr_mult"],
                trail_activation_atr=exec_cfg["trail_activation_atr"],
                break_even_atr=exec_cfg["break_even_atr"]
            )
            pnl_sum += res["pnl"]; ntr += 1
        rows.append({"side": side, "tau": tau, "pnl": pnl_sum, "trades": ntr})
        if pnl_sum > best_pnl:
            best_pnl, best_tau = pnl_sum, tau
    return best_tau, best_pnl, pd.DataFrame(rows)
