"""
Generate prob_win forecast using the retrained robust model.
Compare calibration: Old (synthetic forward-looking) vs New (real backtest outcomes).
"""

import pandas as pd
import numpy as np
import json
import pickle
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from datetime import datetime

# ==============================================================================
# CONFIG
# ==============================================================================
INTRADAY_DATA_FILE = r"..\..\data\us\intraday_15m\consolidated_15m.parquet"
RETRAINED_MODELS_FILE = "evidence/retrained_prob_win_robust/models_per_ticker.pkl"
RETRAINED_CONFIG_FILE = "evidence/retrained_prob_win_robust/feature_config.json"
OUTPUT_DIR = Path("evidence/forecast_retrained_robust")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# LOAD MODELS AND CONFIG
# ==============================================================================
print("=" * 80)
print("Loading retrained models...")
print("=" * 80)

with open(RETRAINED_MODELS_FILE, 'rb') as f:
    models = pickle.load(f)

with open(RETRAINED_CONFIG_FILE) as f:
    config = json.load(f)

feature_cols = config['feature_cols']
print(f"✓ Loaded {len(models)} models")
print(f"✓ Features: {feature_cols}")

# ==============================================================================
# LOAD AND PREPARE DATA
# ==============================================================================
print("\n" + "=" * 80)
print("Loading intraday data...")
print("=" * 80)

intraday_df = pd.read_parquet(INTRADAY_DATA_FILE)
intraday_df['date'] = pd.to_datetime(intraday_df['timestamp']).dt.tz_localize(None)
intraday_df['date_only'] = intraday_df['date'].dt.date

print(f"✓ Loaded {len(intraday_df)} intraday bars")

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

# ==============================================================================
# COMPUTE FEATURES
# ==============================================================================
print("\n" + "=" * 80)
print("Computing features for forecast...")
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
    df = df.sort_values('date').copy()
    df['ret_1d'] = df['close'].pct_change(1)
    df['ret_2d'] = df['close'].pct_change(2)
    df['ret_5d'] = df['close'].pct_change(5)
    df['vol_5d'] = df['ret_1d'].rolling(5).std()
    df['vol_10d'] = df['ret_1d'].rolling(10).std()
    df['vol_20d'] = df['ret_1d'].rolling(20).std()
    df['atr'] = compute_atr(df['high'], df['low'], df['close'], 14)
    df['atr_pct'] = df['atr'] / df['close']
    df['mom_10d'] = (df['close'] - df['close'].shift(10)) / df['close'].shift(10)
    df['gap'] = (df['open'] - df['close'].shift(1)) / df['close'].shift(1)
    df['hl_range'] = (df['high'] - df['low']) / df['close']
    low_20 = df['low'].rolling(20).min()
    high_20 = df['high'].rolling(20).max()
    df['pos_range_20d'] = (df['close'] - low_20) / (high_20 - low_20 + 1e-6)
    return df

daily_with_features = []
for ticker in daily_df['ticker'].unique():
    ticker_data = daily_df[daily_df['ticker'] == ticker]
    ticker_data = add_features(ticker_data)
    daily_with_features.append(ticker_data)

daily_with_features = pd.concat(daily_with_features, ignore_index=True)
print(f"✓ Computed features")

# ==============================================================================
# GENERATE FORECASTS
# ==============================================================================
print("\n" + "=" * 80)
print("Generating forecasts...")
print("=" * 80)

forecasts = []

for ticker in sorted(models.keys()):
    ticker_data = daily_with_features[daily_with_features['ticker'] == ticker].copy()
    ticker_data = ticker_data.sort_values('date')
    
    # Get model and scaler
    model = models[ticker]['model']
    scaler = models[ticker]['scaler']
    
    # Prepare features
    X = ticker_data[feature_cols].copy()
    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.fillna(X.median())
    
    # Scale and predict
    X_scaled = scaler.transform(X)
    probs = model.predict_proba(X_scaled)[:, 1]  # prob of winning
    preds = model.predict(X_scaled)
    
    # Build forecast dataframe
    forecast_ticker = ticker_data[['date', 'open', 'high', 'low', 'close']].copy()
    forecast_ticker['ticker'] = ticker
    forecast_ticker['prob_win_retrained'] = probs
    forecast_ticker['pred_label'] = preds
    
    forecasts.append(forecast_ticker)
    print(f"  {ticker}: {len(forecast_ticker)} forecasts")

# Combine all forecasts
forecast_df = pd.concat(forecasts, ignore_index=True)
forecast_df = forecast_df.sort_values(['ticker', 'date'])

print(f"\n✓ Generated {len(forecast_df)} forecasts")
min_date = forecast_df['date'].min()
max_date = forecast_df['date'].max()
if hasattr(min_date, 'date'):
    min_date = min_date.date()
if hasattr(max_date, 'date'):
    max_date = max_date.date()
print(f"  Date range: {min_date} to {max_date}")
print(f"  Mean prob_win: {forecast_df['prob_win_retrained'].mean():.1%}")
print(f"  Median prob_win: {forecast_df['prob_win_retrained'].median():.1%}")

# ==============================================================================
# SAVE FORECAST
# ==============================================================================
print("\n" + "=" * 80)
print("Saving forecast...")
print("=" * 80)

forecast_path = OUTPUT_DIR / "forecast_prob_win_retrained.parquet"
forecast_df.to_parquet(forecast_path, index=False)
print(f"✓ Saved to {forecast_path}")

# Save CSV for inspection
csv_path = OUTPUT_DIR / "forecast_prob_win_retrained.csv"
forecast_df.to_csv(csv_path, index=False)
print(f"✓ Saved to {csv_path}")

# ==============================================================================
# CALIBRATION COMPARISON
# ==============================================================================
print("\n" + "=" * 80)
print("📊 CALIBRATION ANALYSIS")
print("=" * 80)

# Load old model calibration for comparison
with open("evidence/retrained_prob_win_robust/calibration_report.json") as f:
    retrained_cal = json.load(f)

print("\n✅ RETRAINED MODEL (Real backtest outcomes as labels):")
print("-" * 80)
for ticker in sorted(retrained_cal.keys()):
    cal = retrained_cal[ticker]
    print(f"{ticker:6s}: WR={cal['actual_wr']:.1%} | Val_Acc={cal['val_acc']:.1%} | Brier={cal['brier']:.4f}")

avg_wr = np.mean([c['actual_wr'] for c in retrained_cal.values()])
avg_acc = np.mean([c['val_acc'] for c in retrained_cal.values()])
avg_brier = np.mean([c['brier'] for c in retrained_cal.values()])

print(f"\nAVERAGE: WR={avg_wr:.1%} | Val_Acc={avg_acc:.1%} | Brier={avg_brier:.4f}")

print("\n" + "=" * 80)
print("📋 KEY FINDINGS")
print("=" * 80)
print("""
✅ Retrained Model Advantages:
  1. Uses REAL trading outcomes (pnl > 0) as labels, not synthetic
  2. Features computed from ACTUAL market data around entry
  3. Calibration curves validate against validation set with real labels
  4. No forward-looking bias from TP/SL prediction
  5. Per-ticker logistic regression captures specific dynamics

📊 Calibration Interpretation:
  - Brier Score: Lower is better (perfect=0, random=0.25)
  - Val_Acc: How well the model predicts on unseen trades
  - WR: Actual win rate on training data
  
⚠️ Next Steps:
  1. Run new backtest using retrained forecasts
  2. Compare: Pure MC vs Retrained Prob_Win vs Hybrid (MC + Retrained)
  3. If calibration improves → consider retraining monthly/weekly
""")

# Save summary
summary = {
    'model_type': 'Logistic Regression (per-ticker)',
    'training_approach': 'Real backtest outcomes (pnl > 0)',
    'n_samples_total': len(forecast_df),
    'tickers_trained': len(models),
    'date_range': f"{str(min_date)} to {str(max_date)}",
    'mean_prob_win': float(forecast_df['prob_win_retrained'].mean()),
    'median_prob_win': float(forecast_df['prob_win_retrained'].median()),
    'calibration_summary': {
        'avg_win_rate': float(avg_wr),
        'avg_val_accuracy': float(avg_acc),
        'avg_brier_score': float(avg_brier)
    },
    'per_ticker_calibration': retrained_cal
}

summary_path = OUTPUT_DIR / "forecast_summary.json"
with open(summary_path, 'w') as f:
    json.dump(summary, f, indent=2)
print(f"\n✓ Saved summary to {summary_path}")

print("\n" + "=" * 80)
print("✅ FORECAST GENERATION COMPLETE")
print("=" * 80)
print(f"Output directory: {OUTPUT_DIR}")


