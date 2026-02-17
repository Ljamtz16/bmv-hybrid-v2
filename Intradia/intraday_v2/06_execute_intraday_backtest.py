# Script 06 — Execute Intraday Backtest
# Ejecuta backtest histórico usando el plan intradía
#
# Inputs:
# - artifacts/intraday_plan_clean.csv
# - data/us/intraday_15m/consolidated_15m.parquet
#
# Outputs:
# - artifacts/intraday_trades.csv
# - artifacts/intraday_equity_curve.csv
# - artifacts/intraday_metrics.json

import pandas as pd
import numpy as np
import json
from pathlib import Path

# === DAILY STOP PARAMETERS ===
DAILY_STOP_MAX_SL = 2           # Stop after 2 SL in same day
DAILY_STOP_R_LIMIT = -1.0       # Stop if daily R-multiple <= -1R
ENABLE_DAILY_STOP = True        # Enable/disable daily stop rule


def execute_intraday_backtest(
    plan_path: str,
    intraday_path: str,
    trades_output: str,
    equity_output: str,
    metrics_output: str,
    timezone_target: str = 'America/New_York'
) -> dict:
    """
    Ejecuta backtest del plan intradía.
    
    Returns:
        dict con métricas
    """
    print(f"[06] Cargando plan desde {plan_path}...")
    plan = pd.read_csv(plan_path)
    
    print(f"[06] Cargando intradía desde {intraday_path}...")
    bars = pd.read_parquet(intraday_path)
    
    # Normalizar datetime
    if 'timestamp' in bars.columns and 'datetime' not in bars.columns:
        bars = bars.rename(columns={'timestamp': 'datetime'})
    
    bars['datetime'] = pd.to_datetime(bars['datetime'])
    
    if bars['datetime'].dt.tz is None:
        bars['datetime'] = bars['datetime'].dt.tz_localize(timezone_target)
    else:
        bars['datetime'] = bars['datetime'].dt.tz_convert(timezone_target)
    
    # Parse entry_time
    plan['entry_time'] = pd.to_datetime(plan['entry_time'], utc=True).dt.tz_convert(timezone_target)
    
    # Sort bars para búsqueda
    bars = bars.sort_values(['ticker', 'datetime'])
    bars_grouped = {k: g for k, g in bars.groupby('ticker')}
    
    # Sort plan by date and entry_time for daily stop logic
    plan = plan.sort_values('entry_time')
    
    print(f"\n[06] Ejecutando backtest de {len(plan)} trades...")
    if ENABLE_DAILY_STOP:
        print(f"[06] Daily stop enabled: max_sl={DAILY_STOP_MAX_SL}, r_limit={DAILY_STOP_R_LIMIT}")
    
    # Daily stop state
    current_day = None
    daily_sl_count = 0
    daily_r = 0.0
    daily_pnl = 0.0
    daily_stopped_count = 0  # Count how many trades were blocked
    
    results = []
    for row in plan.itertuples(index=False):
        ticker = row.ticker
        side = row.side
        entry_time = row.entry_time
        entry_price = row.entry_price
        tp_price = row.tp_price
        sl_price = row.sl_price
        time_stop_bars = int(row.time_stop_bars)
        
        # === DAILY STOP: Reset & Gate ===
        trade_day = entry_time.date()
        
        # Reset daily counters on new day
        if current_day is None or trade_day != current_day:
            current_day = trade_day
            daily_sl_count = 0
            daily_r = 0.0
            daily_pnl = 0.0
        
        # Capture state before trade for audit
        daily_sl_count_at_entry = daily_sl_count
        daily_r_at_entry = daily_r
        
        # Gate: check if daily stop triggered
        if ENABLE_DAILY_STOP:
            if daily_sl_count >= DAILY_STOP_MAX_SL:
                daily_stopped_count += 1
                results.append({
                    'ticker': ticker,
                    'entry_time': entry_time,
                    'side': side,
                    'entry_price': entry_price,
                    'tp_price': tp_price,
                    'sl_price': sl_price,
                    'exit_reason': 'DAILY_STOP_SL',
                    'exit_price': np.nan,
                    'pnl': 0,
                    'pnl_pct': 0,
                    'bars_held': 0,
                    'r_mult': 0,
                    'daily_sl_count_at_entry': daily_sl_count_at_entry,
                    'daily_r_at_entry': daily_r_at_entry
                })
                continue
            
            if daily_r <= DAILY_STOP_R_LIMIT:
                daily_stopped_count += 1
                results.append({
                    'ticker': ticker,
                    'entry_time': entry_time,
                    'side': side,
                    'entry_price': entry_price,
                    'tp_price': tp_price,
                    'sl_price': sl_price,
                    'exit_reason': 'DAILY_STOP_R',
                    'exit_price': np.nan,
                    'pnl': 0,
                    'pnl_pct': 0,
                    'bars_held': 0,
                    'r_mult': 0,
                    'daily_sl_count_at_entry': daily_sl_count_at_entry,
                    'daily_r_at_entry': daily_r_at_entry
                })
                continue
        
        # Obtener barras del ticker
        if ticker not in bars_grouped:
            results.append({
                'ticker': ticker,
                'entry_time': entry_time,
                'side': side,
                'entry_price': entry_price,
                'tp_price': tp_price,
                'sl_price': sl_price,
                'exit_reason': 'NO_DATA',
                'exit_price': np.nan,
                'pnl': 0,
                'pnl_pct': 0,
                'bars_held': 0,
                'r_mult': 0,
                'daily_sl_count_at_entry': daily_sl_count_at_entry,
                'daily_r_at_entry': daily_r_at_entry
            })
            continue
        
        ticker_bars = bars_grouped[ticker]
        
        # Filtrar barras futuras
        future = ticker_bars[ticker_bars['datetime'] > entry_time].head(time_stop_bars)
        
        if future.empty:
            results.append({
                'ticker': ticker,
                'entry_time': entry_time,
                'side': side,
                'entry_price': entry_price,
                'tp_price': tp_price,
                'sl_price': sl_price,
                'exit_reason': 'TIMEOUT',
                'exit_price': entry_price,
                'pnl': 0,
                'pnl_pct': 0,
                'bars_held': 0,
                'r_mult': 0,
                'daily_sl_count_at_entry': daily_sl_count_at_entry,
                'daily_r_at_entry': daily_r_at_entry
            })
            continue
        
        # Evaluar TP/SL
        hit = None
        exit_price = None
        bars_held = 0
        
        for b in future.itertuples(index=False):
            bars_held += 1
            high = b.high
            low = b.low
            
            if side == 'BUY':
                hit_tp = high >= tp_price
                hit_sl = low <= sl_price
            else:  # SELL
                hit_tp = low <= tp_price
                hit_sl = high >= sl_price
            
            # Si toca ambos, conservador → SL
            if hit_sl and hit_tp:
                hit = 'SL'
                exit_price = sl_price
                break
            if hit_tp:
                hit = 'TP'
                exit_price = tp_price
                break
            if hit_sl:
                hit = 'SL'
                exit_price = sl_price
                break
        
        if hit is None:
            hit = 'TIMEOUT'
            exit_price = future.iloc[-1].close
        
        # Calcular PnL
        if side == 'BUY':
            pnl = exit_price - entry_price
        else:
            pnl = entry_price - exit_price
        
        pnl_pct = (pnl / entry_price) * 100
        
        # === CALCULATE R-MULTIPLE ===
        # R = risk = distance from entry to SL
        risk_per_share = abs(entry_price - sl_price)
        shares = 1  # We work in per-share terms; can scale later
        risk_dollars = risk_per_share * shares
        
        # R-multiple: pnl / risk
        r_mult = (pnl / risk_dollars) if risk_dollars > 0 else 0.0
        
        results.append({
            'ticker': ticker,
            'entry_time': entry_time,
            'side': side,
            'entry_price': entry_price,
            'tp_price': tp_price,
            'sl_price': sl_price,
            'exit_reason': hit,
            'exit_price': exit_price,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'bars_held': bars_held,
            'r_mult': r_mult,
            'daily_sl_count_at_entry': daily_sl_count_at_entry,
            'daily_r_at_entry': daily_r_at_entry
        })
        
        # === UPDATE DAILY STATE ===
        # Only update for TP/SL (valid trades), not TIMEOUT
        if hit in ('TP', 'SL'):
            daily_pnl += pnl
            daily_r += r_mult
            
            if hit == 'SL':
                daily_sl_count += 1
    
    trades_df = pd.DataFrame(results)
    
    # === DAILY STOP REPORTING ===
    if ENABLE_DAILY_STOP and daily_stopped_count > 0:
        print(f"\n[06] 🛑 Daily stop blocked {daily_stopped_count} trades")
        stop_breakdown = trades_df[trades_df['exit_reason'].str.contains('DAILY_STOP', na=False)]['exit_reason'].value_counts()
        print(f"[06]   Breakdown: {stop_breakdown.to_dict()}")
    
    # === MÉTRICAS ===
    print(f"\n[06] === MÉTRICAS ===")
    
    # Breakdown exits
    exit_counts = trades_df['exit_reason'].value_counts()
    print(f"[06] Exit breakdown:\n{exit_counts}")
    
    # Excluir NO_DATA/TIMEOUT de métricas
    valid_trades = trades_df[~trades_df['exit_reason'].isin(['NO_DATA', 'TIMEOUT', 'DAILY_STOP_SL', 'DAILY_STOP_R'])].copy()
    print(f"\n[06] Trades válidos (sin TIMEOUT/NO_DATA/DAILY_STOP): {len(valid_trades)}")
    
    if len(valid_trades) == 0:
        print("[06] ⚠️  No hay trades válidos para métricas")
        metrics = {
            'total_trades': len(trades_df),
            'valid_trades': 0,
            'pnl_total': 0,
            'pf': 0,
            'wr': 0,
            'max_dd': 0
        }
    else:
        # PnL
        pnl_total = valid_trades['pnl'].sum()
        pnl_wins = valid_trades[valid_trades['pnl'] > 0]['pnl'].sum()
        pnl_losses = valid_trades[valid_trades['pnl'] < 0]['pnl'].sum()
        
        # PF
        pf = pnl_wins / abs(pnl_losses) if pnl_losses != 0 else np.inf
        
        # WR
        wr = (valid_trades['pnl'] > 0).mean() * 100
        
        # Equity curve
        valid_trades = valid_trades.sort_values('entry_time')
        valid_trades['cum_pnl'] = valid_trades['pnl'].cumsum()
        
        # Max DD
        running_max = valid_trades['cum_pnl'].cummax()
        dd = valid_trades['cum_pnl'] - running_max
        max_dd = dd.min()
        
        print(f"\n[06] PnL Total: ${pnl_total:.2f}")
        print(f"[06] PF: {pf:.2f}")
        print(f"[06] WR: {wr:.1f}%")
        print(f"[06] Max DD: ${max_dd:.2f}")
        
        # Por side
        print(f"\n[06] Métricas por side:")
        for side_val in valid_trades['side'].unique():
            subset = valid_trades[valid_trades['side'] == side_val]
            print(f"[06]   {side_val}: WR {(subset['pnl'] > 0).mean() * 100:.1f}% | PnL ${subset['pnl'].sum():.2f} | Trades {len(subset)}")
        
        # R-multiple stats
        avg_r = valid_trades['r_mult'].mean()
        median_r = valid_trades['r_mult'].median()
        print(f"\n[06] R-multiple: avg {avg_r:.2f}R | median {median_r:.2f}R")
        
        metrics = {
            'total_trades': len(trades_df),
            'valid_trades': len(valid_trades),
            'daily_stopped_trades': daily_stopped_count,
            'pnl_total': float(pnl_total),
            'pnl_wins': float(pnl_wins),
            'pnl_losses': float(pnl_losses),
            'pf': float(pf),
            'wr': float(wr),
            'max_dd': float(max_dd),
            'avg_pnl': float(valid_trades['pnl'].mean()),
            'avg_bars_held': float(valid_trades['bars_held'].mean()),
            'avg_r_mult': float(avg_r),
            'median_r_mult': float(median_r),
            'exit_breakdown': exit_counts.to_dict()
        }
    
    # === GUARDAR ===
    trades_dir = Path(trades_output).parent
    equity_dir = Path(equity_output).parent
    metrics_dir = Path(metrics_output).parent
    
    trades_dir.mkdir(parents=True, exist_ok=True)
    equity_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    
    trades_df.to_csv(trades_output, index=False)
    print(f"\n[06] ✅ Trades guardados en: {trades_output}")
    
    if len(valid_trades) > 0:
        equity_df = valid_trades[['entry_time', 'cum_pnl']].copy()
        equity_df.to_csv(equity_output, index=False)
        print(f"[06] ✅ Equity curve guardada en: {equity_output}")
    
    with open(metrics_output, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"[06] ✅ Métricas guardadas en: {metrics_output}")
    
    return metrics


if __name__ == '__main__':
    PLAN_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_plan_clean.csv'
    INTRADAY_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\data\us\intraday_15m\consolidated_15m.parquet'
    TRADES_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_trades.csv'
    EQUITY_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_equity_curve.csv'
    METRICS_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_metrics.json'
    
    metrics = execute_intraday_backtest(
        PLAN_FILE,
        INTRADAY_FILE,
        TRADES_FILE,
        EQUITY_FILE,
        METRICS_FILE
    )
    
    print(f"\n[06] === RESUMEN ===")
    print(f"[06] Total trades: {metrics['total_trades']}")
    print(f"[06] Valid trades: {metrics['valid_trades']}")
    print(f"[06] PF: {metrics.get('pf', 0):.2f}")
    print(f"[06] WR: {metrics.get('wr', 0):.1f}%")
