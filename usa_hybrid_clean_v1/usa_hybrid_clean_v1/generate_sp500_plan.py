#!/usr/bin/env python3
"""
Generate daily trading plans for S&P 500 universe (96 tickers)
Dynamic ranking: top 10-15 tickers by score each day
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

def generate_sp500_plan(asof_date, intraday_df, top_n=15):
    """
    Generate plan for S&P 500 universe
    - Score all tickers by price action
    - Take top N by score
    - Generate plan with top N tickers
    
    Args:
        asof_date: str, "2025-12-01" format
        intraday_df: DataFrame with 15m data (long format)
        top_n: int, number of tickers to trade (10-15 recommended)
    
    Returns:
        DataFrame with plan (signals to execute tomorrow)
    """
    
    # Parse date
    asof_dt = pd.to_datetime(asof_date)
    
    # Get unique tickers in data
    all_tickers = sorted(intraday_df['ticker'].unique())
    print(f"[{asof_date}] Universe: {len(all_tickers)} tickers")
    
    # Score each ticker
    ticker_scores = []
    
    for ticker in all_tickers:
        ticker_data = intraday_df[intraday_df['ticker'] == ticker].copy()
        
        if ticker_data.empty or len(ticker_data) < 10:
            continue
        
        ticker_data = ticker_data.sort_values('datetime')
        
        # Simple scoring: momentum (price change over last 10 candles)
        # + volatility (std of returns)
        # + trend (close > SMA)
        
        recent = ticker_data.tail(10)
        
        # Momentum: % change over last 10 candles
        first_price = recent.iloc[0]['close']
        last_price = recent.iloc[-1]['close']
        momentum = (last_price - first_price) / first_price * 100
        
        # Volatility (standard deviation of 15m returns)
        returns = ticker_data['close'].pct_change().tail(20)
        volatility = returns.std() * 100
        
        # Trend (close above 20-candle SMA)
        sma20 = ticker_data['close'].tail(20).mean()
        trend_score = 1.0 if last_price > sma20 else -1.0
        
        # Combined score (momentum + trend, weighted by volatility)
        score = momentum * trend_score + volatility * 0.5
        
        ticker_scores.append({
            'ticker': ticker,
            'score': score,
            'momentum': momentum,
            'volatility': volatility,
            'trend': 'UP' if trend_score > 0 else 'DN',
            'price': last_price
        })
    
    # Rank by score
    scores_df = pd.DataFrame(ticker_scores)
    scores_df = scores_df.sort_values('score', ascending=False)
    
    print(f"  Top {top_n} by score:")
    top_tickers = scores_df.head(top_n)
    for idx, row in top_tickers.iterrows():
        print(f"    {row['ticker']}: score={row['score']:.2f}, "
              f"momentum={row['momentum']:.2f}%, trend={row['trend']}")
    
    # Generate plan for top tickers
    plan_data = []
    
    for ticker in top_tickers['ticker'].values:
        # Simple entry: next day open (we'll use actual open in simulator)
        # TP: 2%, SL: 1.2% (already optimized)
        
        plan_data.append({
            'ticker': ticker,
            'side': 'BUY',  # Always BUY for simplicity
            'entry_price': 0.0,  # Will be replaced with actual open
            'tp_price': 0.0,  # Will be calculated as 2% above entry
            'sl_price': 0.0,  # Will be calculated as 1.2% below entry
            'max_hold_days': 2,
        })
    
    plan_df = pd.DataFrame(plan_data)
    return plan_df, scores_df

def main():
    # Determine date range
    if len(sys.argv) > 1:
        month_str = sys.argv[1]  # e.g., "2025-12"
    else:
        month_str = "2025-12"
    
    # Load intraday data
    intraday_file = f'data/intraday_15m_sp500/{month_str}.parquet'
    
    if not os.path.exists(intraday_file):
        print(f"ERROR: {intraday_file} not found")
        sys.exit(1)
    
    print(f"Loading intraday data from {intraday_file}...")
    intraday_df = pd.read_parquet(intraday_file)
    
    # Handle wide format (multi-level columns)
    if isinstance(intraday_df.columns, pd.MultiIndex):
        # This is wide format from yfinance
        # Reshape from wide to long
        # Get Datetime from first column
        datetime_col = intraday_df[('Datetime', '')].copy()
        
        # Extract price data for each ticker
        rows = []
        for ticker in intraday_df.columns.get_level_values('Ticker').unique():
            if ticker == '':  # Skip empty ticker (Datetime column)
                continue
            
            ticker_data = intraday_df.xs(ticker, level='Ticker', axis=1)
            ticker_data['Datetime'] = datetime_col
            ticker_data['ticker'] = ticker
            rows.append(ticker_data)
        
        intraday_df = pd.concat(rows, ignore_index=True)
    
    # Standardize column names (to lowercase)
    intraday_df.columns = [col.lower() for col in intraday_df.columns]
    
    # Convert Datetime column
    if 'datetime' in intraday_df.columns:
        intraday_df['datetime'] = pd.to_datetime(intraday_df['datetime'])
        # Remove timezone if present
        if intraday_df['datetime'].dt.tz is not None:
            intraday_df['datetime'] = intraday_df['datetime'].dt.tz_localize(None)
    
    # Standardize column names for pricing columns
    intraday_df.columns = intraday_df.columns.str.lower()
    
    # Make sure we have the right columns
    print(f"Columns: {list(intraday_df.columns)}")
    
    print(f"Loaded {len(intraday_df)} rows, {len(intraday_df['ticker'].unique())} tickers")
    
    # Get all trading days in month
    year, month = map(int, month_str.split('-'))
    first_day = datetime(year, month, 1)
    
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)
    
    # Get unique dates in data
    trading_dates = sorted(intraday_df['datetime'].dt.date.unique())
    trading_dates = [d for d in trading_dates if first_day.date() <= d <= last_day.date()]
    
    print(f"\nGenerating daily plans for {len(trading_dates)} trading days")
    print(f"Date range: {trading_dates[0]} to {trading_dates[-1]}\n")
    
    # Generate plan for each day
    all_plans = []
    scores_history = []
    
    for asof_date in trading_dates:
        # Get data up to end of this day
        data_cutoff = pd.to_datetime(asof_date) + timedelta(days=1)
        hist_data = intraday_df[intraday_df['datetime'] < data_cutoff].copy()
        
        # Generate plan
        plan_df, scores_df = generate_sp500_plan(
            asof_date.strftime('%Y-%m-%d'),
            hist_data,
            top_n=15
        )
        
        plan_df['asof_date'] = asof_date
        all_plans.append(plan_df)
        
        scores_df['asof_date'] = asof_date
        scores_history.append(scores_df)
    
    # Combine all plans
    combined_plan = pd.concat(all_plans, ignore_index=True)
    combined_scores = pd.concat(scores_history, ignore_index=True)
    
    # Save
    plan_file = f'forecast/sp500_plan_{month_str}.csv'
    scores_file = f'forecast/sp500_scores_{month_str}.csv'
    
    os.makedirs('forecast', exist_ok=True)
    
    combined_plan.to_csv(plan_file, index=False)
    combined_scores.to_csv(scores_file, index=False)
    
    print(f"\n{'='*80}")
    print(f"PLAN GENERATED")
    print(f"{'='*80}")
    print(f"Total trading days: {len(trading_dates)}")
    print(f"Total tickers traded: {combined_plan['ticker'].nunique()}")
    print(f"Total trades planned: {len(combined_plan)}")
    print(f"Avg trades/day: {len(combined_plan) / len(trading_dates):.1f}")
    
    # Show sample
    print(f"\nSample (first 3 days):")
    sample = combined_plan[combined_plan['asof_date'] <= combined_plan['asof_date'].unique()[2]]
    for date in sample['asof_date'].unique():
        day_trades = sample[sample['asof_date'] == date]
        print(f"  {date}: {len(day_trades)} trades - {', '.join(day_trades['ticker'].values)}")
    
    print(f"\nFiles saved:")
    print(f"  Plan: {plan_file}")
    print(f"  Scores: {scores_file}")
    print(f"\nNext: Run walk-forward with this plan")
    print(f"  python paper/wf_paper_month_sp500.py --month {month_str}")
    print(f"{'='*80}\n")

if __name__ == '__main__':
    main()
