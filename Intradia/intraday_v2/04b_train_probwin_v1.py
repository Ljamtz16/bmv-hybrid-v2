# Script 04b — Train ProbWin v1 (walk-forward mensual OOS)
#
# Dataset:
# - artifacts/baseline_v1/trades.csv
# Features en entry:
#   ret1, ret4, vol4, vol_z20, atr_ratio, body_pct, hour_bucket, ticker one-hot
# Label:
#   y=1 si exit_reason==TP; y=0 si exit_reason in [SL, EOD]
#
# Outputs:
# - models/probwin_v1.joblib
# - artifacts/probwin_v1/oos_predictions.csv
# - artifacts/probwin_v1/oos_metrics_by_month.csv
# - artifacts/probwin_v1/coeffs.csv

from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, precision_score, recall_score
import joblib


def _resolve_intraday_path(base_dir: Path) -> Path:
    parquet_path = base_dir.parent / 'data' / 'us' / 'intraday_15m' / 'consolidated_15m.parquet'
    csv_path = base_dir.parent / 'data' / 'us' / 'intraday_15m' / 'consolidated_15m.csv'

    if parquet_path.exists():
        return parquet_path
    if csv_path.exists():
        return csv_path
    raise FileNotFoundError(f"No se encontró consolidated_15m.parquet ni consolidated_15m.csv en {parquet_path.parent}")


def _load_intraday(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == '.parquet':
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _build_bar_features(bars: pd.DataFrame, timezone_target: str) -> pd.DataFrame:
    bars = bars.rename(columns={'timestamp': 'datetime'}).copy()
    bars['datetime'] = pd.to_datetime(bars['datetime'])

    if bars['datetime'].dt.tz is None:
        bars['datetime'] = bars['datetime'].dt.tz_localize('UTC').dt.tz_convert(timezone_target)
    else:
        bars['datetime'] = bars['datetime'].dt.tz_convert(timezone_target)

    bars = bars.sort_values(['ticker', 'datetime']).reset_index(drop=True)

    # ATR14
    bars['prev_close'] = bars.groupby('ticker')['close'].shift(1)
    tr = np.maximum.reduce([
        bars['high'] - bars['low'],
        (bars['high'] - bars['prev_close']).abs(),
        (bars['low'] - bars['prev_close']).abs()
    ])
    bars['tr'] = pd.Series(tr, index=bars.index).fillna(bars['high'] - bars['low'])
    bars['atr14'] = (
        bars.groupby('ticker')['tr']
        .transform(lambda x: x.rolling(14, min_periods=1).mean())
    )

    # Returns
    bars['ret1'] = bars.groupby('ticker')['close'].pct_change()
    bars['ret4'] = bars.groupby('ticker')['close'].pct_change(4)

    # Use previous bars for ret1/ret4/vol/volume z-score
    bars['ret1_prev'] = bars.groupby('ticker')['ret1'].shift(1)
    bars['ret4_prev'] = bars.groupby('ticker')['ret4'].shift(1)

    bars['vol4'] = (
        bars.groupby('ticker')['ret1']
        .transform(lambda x: x.rolling(4, min_periods=4).std())
        .shift(1)
    )

    vol_mean = bars.groupby('ticker')['volume'].transform(lambda x: x.rolling(20, min_periods=20).mean())
    vol_std = bars.groupby('ticker')['volume'].transform(lambda x: x.rolling(20, min_periods=20).std())
    bars['vol_z20'] = ((bars['volume'] - vol_mean) / vol_std).shift(1)

    # Entry-bar features
    bars['atr_ratio'] = (bars['high'] - bars['low']) / bars['atr14'].replace(0, np.nan)
    denom = (bars['high'] - bars['low']).replace(0, np.nan)
    bars['body_pct'] = (bars['close'] - bars['open']).abs() / denom

    return bars[['ticker', 'datetime', 'ret1_prev', 'ret4_prev', 'vol4', 'vol_z20', 'atr_ratio', 'body_pct']].copy()


def train_probwin_v1(
    trades_path: str,
    intraday_path: str | None,
    model_path: str,
    preds_path: str,
    metrics_path: str,
    coeffs_path: str,
    timezone_target: str = 'America/New_York'
) -> dict:
    print(f"[04b] Cargando trades desde {trades_path}...")
    trades = pd.read_csv(trades_path)

    if 'exit_reason' not in trades.columns:
        raise ValueError("trades.csv no contiene exit_reason")

    # Filtrar trades válidos (TP/SL/EOD)
    trades = trades[trades['exit_reason'].isin(['TP', 'SL', 'EOD'])].copy()
    if 'allowed' in trades.columns:
        trades = trades[trades['allowed'] == True].copy()

    # Parse entry_time (with mixed timezones, parse utc then convert)
    trades['entry_time'] = pd.to_datetime(trades['entry_time'], utc=True)
    trades['entry_time'] = trades['entry_time'].dt.tz_convert(timezone_target)

    trades['month'] = trades['entry_time'].dt.to_period('M').astype(str)
    trades['hour_bucket'] = trades['entry_time'].dt.strftime('%H:%M')

    # Label
    trades['y'] = (trades['exit_reason'] == 'TP').astype(int)

    base_dir = Path(__file__).resolve().parent
    data_path = Path(intraday_path) if intraday_path else _resolve_intraday_path(base_dir)

    print(f"[04b] Cargando intradía desde {data_path}...")
    bars = _load_intraday(data_path)

    # Features por barra
    bar_features = _build_bar_features(bars, timezone_target)

    # Merge trades con features
    df = trades.merge(
        bar_features,
        left_on=['ticker', 'entry_time'],
        right_on=['ticker', 'datetime'],
        how='left'
    )

    # Clean
    df = df.drop(columns=['datetime'], errors='ignore')

    # Features
    numeric_cols = ['ret1_prev', 'ret4_prev', 'vol4', 'vol_z20', 'atr_ratio', 'body_pct']

    # Preserve raw fields for outputs  
    df['ticker_raw'] = df['ticker']
    df['hour_bucket_raw'] = df['hour_bucket']

    # One-hot: ticker, hour_bucket
    df = pd.get_dummies(df, columns=['ticker', 'hour_bucket'], prefix=['ticker', 'hour'], dummy_na=False)

    # Feature cols: numeric + one-hot encoded (exclude raw fields)
    one_hot_cols = [c for c in df.columns if (c.startswith('ticker_') or c.startswith('hour_')) and c not in ['ticker_raw', 'hour_bucket_raw']]
    feature_cols = numeric_cols + one_hot_cols

    # Debug
    print(f"[04b] Feature cols ({len(feature_cols)}): {feature_cols[:10]}...")
    print(f"[04b] Feature cols dtypes: {df[feature_cols].dtypes.unique()}")
    
    # Drop NaNs
    before = len(df)
    df = df.dropna(subset=feature_cols + ['y', 'month'])
    after = len(df)
    print(f"[04b] Filas después de drop NaN: {after:,} (antes: {before:,})")

    # Walk-forward mensual
    months = sorted(df['month'].unique())
    oos_rows = []
    metrics_rows = []

    for m in months:
        train = df[df['month'] < m]
        test = df[df['month'] == m]

        if len(train) == 0 or len(test) == 0:
            continue

        X_train = train[feature_cols]
        y_train = train['y']
        X_test = test[feature_cols]
        y_test = test['y']

        model = LogisticRegression(class_weight='balanced', max_iter=2000)
        model.fit(X_train, y_train)

        proba = model.predict_proba(X_test)[:, 1]
        y_pred = (proba >= 0.5).astype(int)

        # Métricas
        if y_test.nunique() == 2:
            auc = roc_auc_score(y_test, proba)
        else:
            auc = np.nan

        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)

        metrics_rows.append({
            'month': m,
            'samples': int(len(test)),
            'pos_rate': float(y_test.mean()),
            'auc': float(auc) if not np.isnan(auc) else np.nan,
            'precision': float(precision),
            'recall': float(recall)
        })

        oos_rows.append(pd.DataFrame({
            'entry_time': test['entry_time'].values,
            'ticker': test['ticker_raw'].values,
            'hour_bucket': test['hour_bucket_raw'].values,
            'y': y_test.values,
            'probwin': proba,
            'month': m
        }))

    oos_df = pd.concat(oos_rows, ignore_index=True) if oos_rows else pd.DataFrame()
    metrics_df = pd.DataFrame(metrics_rows)

    # Train final model
    X_all = df[feature_cols]
    y_all = df['y']

    final_model = LogisticRegression(class_weight='balanced', max_iter=2000)
    final_model.fit(X_all, y_all)

    # Coeffs
    coeffs = pd.DataFrame({
        'feature': feature_cols,
        'coef': final_model.coef_[0]
    }).sort_values('coef', key=abs, ascending=False)

    # Save
    model_dir = Path(model_path).parent
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({'model': final_model, 'feature_cols': feature_cols}, model_path)

    preds_dir = Path(preds_path).parent
    preds_dir.mkdir(parents=True, exist_ok=True)
    oos_df.to_csv(preds_path, index=False)

    metrics_dir = Path(metrics_path).parent
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_df.to_csv(metrics_path, index=False)

    coeffs_dir = Path(coeffs_path).parent
    coeffs_dir.mkdir(parents=True, exist_ok=True)
    coeffs.to_csv(coeffs_path, index=False)

    print(f"[04b] ✅ Modelo guardado en: {model_path}")
    print(f"[04b] ✅ OOS preds guardadas en: {preds_path}")
    print(f"[04b] ✅ OOS métricas guardadas en: {metrics_path}")
    print(f"[04b] ✅ Coeffs guardadas en: {coeffs_path}")

    return {
        'months': len(metrics_df),
        'samples': len(df),
        'feature_cols': feature_cols
    }


if __name__ == '__main__':
    base_dir = Path(__file__).resolve().parent
    trades_path = base_dir / 'artifacts' / 'baseline_v1' / 'trades.csv'
    model_path = base_dir / 'models' / 'probwin_v1.joblib'
    preds_path = base_dir / 'artifacts' / 'probwin_v1' / 'oos_predictions.csv'
    metrics_path = base_dir / 'artifacts' / 'probwin_v1' / 'oos_metrics_by_month.csv'
    coeffs_path = base_dir / 'artifacts' / 'probwin_v1' / 'coeffs.csv'

    train_probwin_v1(
        trades_path=str(trades_path),
        intraday_path=None,
        model_path=str(model_path),
        preds_path=str(preds_path),
        metrics_path=str(metrics_path),
        coeffs_path=str(coeffs_path)
    )
