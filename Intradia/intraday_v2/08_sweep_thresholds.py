import pandas as pd
import numpy as np
from pathlib import Path
import importlib.util


def _load_module(module_path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def detect_split_tickers(daily_path: str, pct_change_threshold: float = 0.5):
    daily = pd.read_parquet(daily_path).sort_values(['ticker', 'date'])
    daily['pct_change'] = daily.groupby('ticker')['close'].pct_change().abs()
    splits = daily[daily['pct_change'] > pct_change_threshold]
    return set(splits['ticker'].unique())


def main():
    base_dir = Path(r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2')
    artifacts = base_dir / 'artifacts'
    sweep_dir = artifacts / 'sweep'
    sweep_dir.mkdir(parents=True, exist_ok=True)

    plan_module = _load_module(str(base_dir / '05_generate_intraday_plan.py'), 'plan_module')
    backtest_module = _load_module(str(base_dir / '06_execute_intraday_backtest.py'), 'backtest_module')
    generate_intraday_plan = plan_module.generate_intraday_plan
    execute_intraday_backtest = backtest_module.execute_intraday_backtest

    WINDOWS_FILE = str(artifacts / 'intraday_windows.parquet')
    REGIME_FILE = str(artifacts / 'regime_table.parquet')
    MODEL_FILE = str(base_dir / 'models' / 'intraday_probwin_model.pkl')
    FEATURES_FILE = str(base_dir / 'models' / 'intraday_feature_columns.json')
    DAILY_FILE = str(artifacts / 'daily_bars.parquet')
    INTRADAY_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\data\us\intraday_15m\consolidated_15m.parquet'

    split_tickers = detect_split_tickers(DAILY_FILE, pct_change_threshold=0.5)
    print(f"[08] Split tickers detectados: {sorted(split_tickers)}")

    thresholds = [0.60, 0.62, 0.64, 0.66, 0.68, 0.70, 0.72]
    results = []

    for thr in thresholds:
        print(f"\n[08] === Threshold {thr:.2f} ===")
        plan_path = str(sweep_dir / f'intraday_plan_thr_{thr:.2f}.csv')
        plan = generate_intraday_plan(
            WINDOWS_FILE,
            REGIME_FILE,
            MODEL_FILE,
            FEATURES_FILE,
            plan_path,
            threshold=thr,
            tp_mult=0.8,
            sl_mult=0.6,
            time_stop_bars=16,
            max_trades_per_ticker_per_day=1,
            max_trades_per_day=6
        )

        # Filter split tickers
        plan = plan[~plan['ticker'].isin(split_tickers)].copy()
        plan_clean_path = str(sweep_dir / f'intraday_plan_thr_{thr:.2f}_clean.csv')
        plan.to_csv(plan_clean_path, index=False)

        # Backtest
        trades_path = str(sweep_dir / f'intraday_trades_thr_{thr:.2f}.csv')
        equity_path = str(sweep_dir / f'intraday_equity_thr_{thr:.2f}.csv')
        metrics_path = str(sweep_dir / f'intraday_metrics_thr_{thr:.2f}.json')

        metrics = execute_intraday_backtest(
            plan_clean_path,
            INTRADAY_FILE,
            trades_path,
            equity_path,
            metrics_path
        )

        # Trades per day stats
        if len(plan) > 0:
            plan['date_only'] = pd.to_datetime(plan['date']).dt.date
            trades_per_day = plan.groupby('date_only').size()
            mean_tpd = trades_per_day.mean()
            p90_tpd = trades_per_day.quantile(0.9)
        else:
            mean_tpd = 0
            p90_tpd = 0

        results.append({
            'threshold': thr,
            'total_trades': metrics.get('total_trades', 0),
            'valid_trades': metrics.get('valid_trades', 0),
            'pf': metrics.get('pf', 0),
            'wr': metrics.get('wr', 0),
            'pnl_total': metrics.get('pnl_total', 0),
            'max_dd': metrics.get('max_dd', 0),
            'mean_trades_per_day': float(mean_tpd),
            'p90_trades_per_day': float(p90_tpd)
        })

    summary = pd.DataFrame(results)
    summary_path = sweep_dir / 'threshold_sweep_summary.csv'
    summary.to_csv(summary_path, index=False)
    print(f"\n[08] ✅ Sweep summary guardado en: {summary_path}")
    print(summary)


if __name__ == '__main__':
    main()
