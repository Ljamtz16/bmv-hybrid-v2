import argparse
import itertools
import json
import os
from pathlib import Path

import pandas as pd


def load_signals(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
    return df


def filter_signals(df: pd.DataFrame, month: str, min_prob: float, min_abs_yhat: float, gate_col: str = None) -> pd.DataFrame:
    out = df.copy()
    if 'date' in out.columns:
        out = out[out['date'].dt.strftime('%Y-%m') == month]
    if min_prob and 'prob_win' in out.columns:
        out = out[out['prob_win'] >= float(min_prob)]
    if min_abs_yhat and 'y_hat' in out.columns:
        out = out[out['y_hat'].abs() >= float(min_abs_yhat)]
    if gate_col is None:
        gate_col = 'gate_pattern_ok' if 'gate_pattern_ok' in out.columns else ('gate_ok' if 'gate_ok' in out.columns else None)
    if gate_col:
        out = out[out[gate_col] == 1]
    return out


def estimate_pnl(df: pd.DataFrame, tp: float, sl: float, per_trade_cash: float) -> float:
    pnl = 0.0
    for _, r in df.iterrows():
        ret = float(r.get('y_hat', 0.0))
        if ret >= tp:
            rr = tp
        elif ret <= -sl:
            rr = -sl
        else:
            rr = ret
        pnl += rr * per_trade_cash
    return pnl


def main():
    ap = argparse.ArgumentParser(description="Autotune min_prob/min_abs_yhat/gate_threshold to reach target trades and maximize PnL")
    ap.add_argument('--month', required=True)
    ap.add_argument('--signals', default=None, help='Path to signals CSV; default: reports/forecast/<month>/forecast_with_patterns.csv if exists else forecast_signals.csv')
    ap.add_argument('--tp-pct', type=float, default=0.07)
    ap.add_argument('--sl-pct', type=float, default=0.01)
    ap.add_argument('--per-trade-cash', type=float, default=200.0)
    ap.add_argument('--target-min-trades', type=int, default=8)
    ap.add_argument('--target-max-trades', type=int, default=15)
    ap.add_argument('--grid-prob', default='0.55,0.60,0.65,0.70')
    ap.add_argument('--grid-abs', default='0.05,0.06,0.07,0.08')
    ap.add_argument('--out-json', default=None, help='Output JSON with recommended thresholds')
    args = ap.parse_args()

    month_dir = Path('reports') / 'forecast' / args.month
    sig = args.signals
    if sig is None:
        s1 = month_dir / 'forecast_with_patterns.csv'
        s2 = month_dir / 'forecast_signals.csv'
        sig = s1 if s1.exists() else s2
    df = load_signals(str(sig))

    grid_prob = [float(x) for x in args.grid_prob.split(',') if x]
    grid_abs = [float(x) for x in args.grid_abs.split(',') if x]

    best = None
    candidates = []
    for p, a in itertools.product(grid_prob, grid_abs):
        dff = filter_signals(df, args.month, min_prob=p, min_abs_yhat=a)
        trades = len(dff)
        pnl = estimate_pnl(dff, args.tp_pct, args.sl_pct, args.per_trade_cash)
        score = -abs(max(args.target_min_trades - trades, 0) + max(trades - args.target_max_trades, 0)) * 1e6 + pnl
        item = {
            'min_prob': p,
            'min_abs_yhat': a,
            'trades': int(trades),
            'net_pnl_sum': pnl,
            'score': score,
        }
        candidates.append(item)
        if best is None or item['score'] > best['score']:
            best = item

    out = {
        'month': args.month,
        'tp_pct': args.tp_pct,
        'sl_pct': args.sl_pct,
        'per_trade_cash': args.per_trade_cash,
        'target_min_trades': args.target_min_trades,
        'target_max_trades': args.target_max_trades,
        'best': best,
        'grid_top5': sorted(candidates, key=lambda x: x['score'], reverse=True)[:5],
    }

    out_path = Path(args.out_json) if args.out_json else (month_dir / 'autotune_thresholds.json')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[autotune] Saved -> {out_path}")
    print(best)


if __name__ == '__main__':
    main()
