"""
Retrain prob_win model using REAL backtest outcomes.

Strategy:
1. Load trades from backtest (entry_date, ticker, pnl)
2. Load intraday data and aggregate to daily
3. Compute robust features: volatility, momentum, ATR, gap, range
4. Use pnl > 0 as label (Win=1, Loss=0)
5. Train logistic regression per ticker
6. Save models and calibration curves
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import warnings
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import brier_score_loss
from sklearn.calibration import calibration_curve
import pickle
import matplotlib.pyplot as plt
from datetime import datetime

warnings.filterwarnings('ignore')

# ==============================================================================
# CONFIG
# ==============================================================================
BACKTEST_TRADES_FILE = "evidence/backtest_mc_weekly_2024_2025/trades.csv"
INTRADAY_DATA_FILE = r"C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\data\us\intraday_15m\consolidated_15m.parquet"
OUTPUT_DIR = Path("evidence/retrained_prob_win_robust")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# STEP 1: Load backtest trades
# ==============================================================================
print("=" * 80)
print("STEP 1: Loading backtest trades...")
print("=" * 80)

trades_df = pd.read_csv(BACKTEST_TRADES_FILE)
trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
trades_df['pnl'] = pd.to_numeric(trades_df['pnl'], errors='coerce')
trades_df['label'] = (trades_df['pnl'] > 0).astype(int)

print(f"✓ Loaded {len(trades_df)} trades")
print(f"  Win rate: {trades_df['label'].mean():.1%}")
print(f"  Date range: {trades_df['entry_date'].min().date()} to {trades_df['entry_date'].max().date()}")
print(f"  Tickers: {sorted(trades_df['ticker'].unique())}")

# ==============================================================================
# STEP 2: Load and aggregate intraday data
# ==============================================================================
print("\n" + "=" * 80)
print("STEP 2: Loading and aggregating intraday data...")
print("=" * 80)

intraday_df = pd.read_parquet(INTRADAY_DATA_FILE)
intraday_df['date'] = pd.to_datetime(intraday_df['timestamp']).dt.tz_localize(None)
intraday_df['date_only'] = intraday_df['date'].dt.date

# Aggregate to daily
daily_df = intraday_df.groupby(['ticker', 'date_only']).agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum'
}).reset_index()

daily_df['date'] = daily_df['date_only']
daily_df = daily_df.drop('date_only', axis=1)
daily_df = daily_df.sort_values(['ticker', 'date'])

print(f"✓ Aggregated to {len(daily_df)} daily bars")
print(f"  Tickers: {daily_df['ticker'].nunique()}")

# ==============================================================================
# STEP 3: Compute features per ticker
# ==============================================================================
print("\n" + "=" * 80)
print("STEP 3: Computing features...")
print("=" * 80)

def compute_atr(high, low, close, period=14):
    tr = np.maximum(
        high - low,
        np.maximum(
            np.abs(high - close.shift(1)),
            np.abs(low - close.shift(1))
        )
    )
    return tr.rolling(period).mean()

def add_features(df):
    """Add features to daily data"""
    df = df.sort_values('date').copy()
    
    # Returns
    df['ret_1d'] = df['close'].pct_change(1)
    df['ret_2d'] = df['close'].pct_change(2)
    df['ret_5d'] = df['close'].pct_change(5)
    
    # Volatility
    df['vol_5d'] = df['ret_1d'].rolling(5).std()
    df['vol_10d'] = df['ret_1d'].rolling(10).std()
    df['vol_20d'] = df['ret_1d'].rolling(20).std()
    
    # ATR
    df['atr'] = compute_atr(df['high'], df['low'], df['close'], 14)
    df['atr_pct'] = df['atr'] / df['close']
    
    # Momentum
    df['mom_10d'] = (df['close'] - df['close'].shift(10)) / df['close'].shift(10)
    
    # Gap
    df['gap'] = (df['open'] - df['close'].shift(1)) / df['close'].shift(1)
    
    # High-Low range
    df['hl_range'] = (df['high'] - df['low']) / df['close']
    
    # Price position in 20-day range
    low_20 = df['low'].rolling(20).min()
    high_20 = df['high'].rolling(20).max()
    df['pos_range_20d'] = (df['close'] - low_20) / (high_20 - low_20 + 1e-6)
    
    return df

# Add features for all tickers
daily_with_features = []
for ticker in daily_df['ticker'].unique():
    ticker_data = daily_df[daily_df['ticker'] == ticker]
    ticker_data = add_features(ticker_data)
    daily_with_features.append(ticker_data)

daily_with_features = pd.concat(daily_with_features, ignore_index=True)
print(f"✓ Computed features")

# ==============================================================================
# STEP 4: Merge trades with features
# ==============================================================================
print("\n" + "=" * 80)
print("STEP 4: Merging trades with features...")
print("=" * 80)

trades_df['entry_date_only'] = trades_df['entry_date'].dt.date

merged = trades_df.merge(
    daily_with_features,
    left_on=['ticker', 'entry_date_only'],
    right_on=['ticker', 'date'],
    how='left'
)

feature_cols = ['ret_1d', 'ret_2d', 'ret_5d', 'vol_5d', 'vol_10d', 'vol_20d', 
                'atr_pct', 'mom_10d', 'gap', 'hl_range', 'pos_range_20d']

# Clean
merged_clean = merged.dropna(subset=feature_cols + ['label'])
print(f"✓ Merged {len(merged)} trades")
print(f"  With features: {len(merged_clean)}")

if len(merged_clean) == 0:
    print("ERROR: No trades with features!")
    exit(1)

# ==============================================================================
# STEP 5: Train per-ticker models
# ==============================================================================
print("\n" + "=" * 80)
print("STEP 5: Training models per ticker...")
print("=" * 80)

models = {}
calibration_results = {}

for ticker in sorted(merged_clean['ticker'].unique()):
    ticker_data = merged_clean[merged_clean['ticker'] == ticker]
    
    X = ticker_data[feature_cols].copy()
    y = ticker_data['label'].copy()
    
    if len(X) < 20:
        print(f"  {ticker}: SKIPPED (n={len(X)})")
        continue
    
    # Clean values
    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.fillna(X.median())
    
    # Split
    try:
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
    except:
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
    
    # Scale
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    
    # Train
    model = LogisticRegression(max_iter=1000, random_state=42, class_weight='balanced')
    model.fit(X_train_scaled, y_train)
    
    # Evaluate
    train_acc = model.score(X_train_scaled, y_train)
    val_acc = model.score(X_val_scaled, y_val)
    val_probs = model.predict_proba(X_val_scaled)[:, 1]
    brier = brier_score_loss(y_val, val_probs)
    
    # Calibration
    frac_pos, mean_pred = calibration_curve(y_val, val_probs, n_bins=5)
    
    # Store
    models[ticker] = {'model': model, 'scaler': scaler}
    calibration_results[ticker] = {
        'n_samples': len(X),
        'n_train': len(X_train),
        'n_val': len(X_val),
        'train_acc': float(train_acc),
        'val_acc': float(val_acc),
        'brier': float(brier),
        'actual_wr': float(y.mean()),
        'frac_pos': frac_pos.tolist(),
        'mean_pred': mean_pred.tolist()
    }
    
    print(f"  {ticker:6s}: n={len(X):3d} | train={train_acc:.1%} | val={val_acc:.1%} | brier={brier:.4f} | actual_WR={y.mean():.1%}")

# ==============================================================================
# STEP 6: Save models and calibration
# ==============================================================================
print("\n" + "=" * 80)
print("STEP 6: Saving models...")
print("=" * 80)

# Save models
model_path = OUTPUT_DIR / "models_per_ticker.pkl"
with open(model_path, 'wb') as f:
    pickle.dump(models, f)
print(f"✓ Saved to {model_path}")

# Save calibration
cal_path = OUTPUT_DIR / "calibration_report.json"
with open(cal_path, 'w') as f:
    json.dump(calibration_results, f, indent=2)
print(f"✓ Saved to {cal_path}")

# Save config
config = {
    'feature_cols': feature_cols,
    'n_total_samples': len(merged_clean),
    'n_tickers_trained': len(models),
    'training_period': f"{merged_clean['entry_date'].min().date()} to {merged_clean['entry_date'].max().date()}",
    'training_date': datetime.now().isoformat()
}

config_path = OUTPUT_DIR / "feature_config.json"
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
print(f"✓ Saved to {config_path}")

# ==============================================================================
# FINAL SUMMARY
# ==============================================================================
print("\n" + "=" * 80)
print("✅ RETRAINING COMPLETE")
print("=" * 80)
print(f"\nCalibration Summary (first 5 tickers):")
for ticker in sorted(calibration_results.keys())[:5]:
    cal = calibration_results[ticker]
    print(f"  {ticker}: WR={cal['actual_wr']:.1%} | Val_Acc={cal['val_acc']:.1%} | Brier={cal['brier']:.4f}")

print(f"\nOutput directory: {OUTPUT_DIR}")
print(f"  - models_per_ticker.pkl")
print(f"  - calibration_report.json")
print(f"  - feature_config.json")
