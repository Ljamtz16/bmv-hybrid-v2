# Script 05 — Generate Intraday Plan
# Genera plan intradía basado en modelo + gates de régimen
#
# Inputs:
# - artifacts/intraday_windows.parquet
# - artifacts/regime_table.parquet
# - models/intraday_probwin_model.pkl
# - models/intraday_feature_columns.json
#
# Output:
# - artifacts/intraday_plan.csv

import pandas as pd
import numpy as np
import json
import joblib
from pathlib import Path


def _parse_time_to_minutes(t: str) -> int:
    hh, mm = t.split(':')
    return int(hh) * 60 + int(mm)


def _combine_date_time(date_ts: pd.Timestamp, time_str: str) -> pd.Timestamp:
    minutes = _parse_time_to_minutes(time_str)
    return date_ts + pd.Timedelta(minutes=minutes)


def _detect_split_tickers(daily_path: str, pct_change_threshold: float = 0.5) -> set:
    daily = pd.read_parquet(daily_path).sort_values(['ticker', 'date'])
    daily['pct_change'] = daily.groupby('ticker')['close'].pct_change().abs()
    splits = daily[daily['pct_change'] > pct_change_threshold]
    return set(splits['ticker'].unique())


def generate_intraday_plan(
    windows_path: str,
    regime_path: str,
    model_path: str,
    features_path: str,
    output_path: str,
    threshold: float = 0.70,
    tp_mult: float = 0.8,
    sl_mult: float = 0.6,
    time_stop_bars: int = 16,
    max_trades_per_ticker_per_day: int = 1,
    max_trades_per_day: int = 6,
    daily_bars_path: str | None = None,
    output_clean_path: str | None = None,
    exclude_splits: bool = True
) -> pd.DataFrame:
    """
    Genera plan intradía con gates de régimen + modelo.
    
    Returns:
        DataFrame con plan de trades
    """
    print(f"[05] Cargando ventanas desde {windows_path}...")
    windows = pd.read_parquet(windows_path)
    
    print(f"[05] Cargando régimen desde {regime_path}...")
    regime = pd.read_parquet(regime_path)
    
    print(f"[05] Cargando modelo desde {model_path}...")
    model = joblib.load(model_path)
    
    print(f"[05] Cargando features desde {features_path}...")
    with open(features_path, 'r') as f:
        feature_cols = json.load(f)
    
    print(f"[05] Features esperadas: {feature_cols}")
    
    # Date key para joins
    windows['date_key'] = pd.to_datetime(windows['date']).dt.date
    regime['date_key'] = pd.to_datetime(regime['date']).dt.date
    
    # Usar columnas PREV para anti-leakage
    regime_features = [
        'ticker', 'date_key',
        'atr14_prev', 'ema20_prev', 'daily_range_pct_prev',
        'is_high_vol_prev', 'is_wide_range_prev', 'is_directional_prev',
        'side_prev'
    ]
    
    regime_use = regime[regime_features].copy()
    
    # Join
    df = windows.merge(regime_use, on=['ticker', 'date_key'], how='left')
    
    # Drop sin régimen prev
    before = len(df)
    df = df.dropna(subset=['atr14_prev', 'ema20_prev', 'side_prev'])
    after = len(df)
    print(f"[05] Filas después de drop prev: {after:,} (antes: {before:,})")
    
    # Renombrar para match con features
    df = df.rename(columns={
        'atr14_prev': 'atr14',
        'ema20_prev': 'ema20',
        'daily_range_pct_prev': 'daily_range_pct',
        'is_high_vol_prev': 'is_high_vol',
        'is_wide_range_prev': 'is_wide_range',
        'is_directional_prev': 'is_directional',
        'side_prev': 'side'
    })
    
    # === Construir features ===
    df['window_range'] = (df['w_high'] - df['w_low']) / df['w_open']
    df['window_return'] = (df['w_close'] - df['w_open']) / df['w_open']
    df['window_body'] = (df['w_close'] - df['w_open']).abs() / df['w_open']
    df['w_close_vs_ema'] = (df['w_close'] - df['ema20']) / df['ema20']
    df['range_to_atr'] = (df['w_high'] - df['w_low']) / df['atr14']
    df['body_to_atr'] = (df['w_close'] - df['w_open']).abs() / df['atr14']
    df['side_numeric'] = (df['side'] == 'BUY').astype(int)
    df['window_OPEN'] = (df['window'] == 'OPEN').astype(int)
    df['window_CLOSE'] = (df['window'] == 'CLOSE').astype(int)
    
    # === Features adicionales (matching 03_build_intraday_dataset.py) ===
    # Merge with regime to get prev_close and other previous values
    regime_for_features = regime[['ticker', 'date_key', 'close']].copy()
    regime_for_features = regime_for_features.sort_values(['ticker', 'date_key'])
    regime_for_features['close_prev'] = regime_for_features.groupby('ticker')['close'].shift(1)
    df = df.merge(regime_for_features[['ticker', 'date_key', 'close_prev']], 
                  on=['ticker', 'date_key'], how='left')
    
    # gap_atr: overnight gap normalized by ATR
    df['gap_atr'] = (df['w_open'] - df['close_prev']) / df['atr14']
    
    # overnight_ret: overnight return
    df['overnight_ret'] = (df['w_open'] - df['close_prev']) / df['close_prev']
    
    # rvol: relative volume (no precomputed, approximate with volume only)
    df['rvol'] = 1.0  # Default; would need rolling window stats for proper calc
    
    # vwap_dist: distance to window VWAP (approximate with close for plan generation)
    df['vwap_dist'] = 0.0  # Cannot compute VWAP without bars; use neutral value
    
    # Interaction features
    df['body_to_atr_x_high_vol'] = df['body_to_atr'] * df['is_high_vol']
    df['range_to_atr_x_directional'] = df['range_to_atr'] * df['is_directional']
    
    # Validar features
    missing = set(feature_cols) - set(df.columns)
    if missing:
        raise ValueError(f"Features faltantes: {missing}")
    
    X = df[feature_cols].copy()
    
    # Drop NaN en features
    valid = ~X.isna().any(axis=1)
    df = df[valid].copy()
    X = X[valid].copy()
    
    print(f"[05] Filas válidas para predict: {len(df):,}")
    
    # === Predecir ===
    df['prob_win_intraday'] = model.predict_proba(X)[:, 1]
    
    print(f"\n[05] === GATES ===")
    
    # Gate 1: Régimen ON (prev)
    gate_regime = (
        df['is_high_vol'] &
        df['is_wide_range'] &
        df['is_directional']
    )
    print(f"[05] Gate régimen (prev): {gate_regime.sum():,} / {len(df):,}")
    
    # Gate 2: Modelo
    gate_model = df['prob_win_intraday'] >= threshold
    print(f"[05] Gate modelo (>={threshold}): {gate_model.sum():,} / {len(df):,}")
    
    # Combinado
    df_plan = df[gate_regime & gate_model].copy()
    print(f"[05] Trades después de gates combinados: {len(df_plan):,}")
    
    # === BUY-ONLY FILTER ===
    # Model was trained on BUY-only dataset
    before_buy_filter = len(df_plan)
    df_plan = df_plan[df_plan['side'] == 'BUY'].copy()
    print(f"[05] Trades después de filtrar BUY-only: {len(df_plan):,} (excluidos {before_buy_filter - len(df_plan):,} SELL)")
    
    if len(df_plan) == 0:
        print(f"[05] ⚠️  No hay trades BUY que pasen gates. Generando plan vacío.")
        df_plan.to_csv(output_path, index=False)
        return df_plan
    
    # Gate 3: Max 1 trade por ticker/día (prioridad por prob)
    df_plan = (
        df_plan
        .sort_values(['ticker', 'date_key', 'prob_win_intraday'], ascending=[True, True, False])
        .groupby(['ticker', 'date_key'])
        .first()
        .reset_index()
    )
    print(f"[05] Trades después de 1/ticker/día: {len(df_plan):,}")
    
    # Gate 4: Max N trades por día (top prob)
    df_plan['date_only'] = pd.to_datetime(df_plan['date']).dt.date
    df_plan = (
        df_plan
        .sort_values(['date_only', 'prob_win_intraday'], ascending=[True, False])
        .groupby('date_only')
        .head(max_trades_per_day)
        .reset_index(drop=True)
    )
    print(f"[05] Trades después de cap diario ({max_trades_per_day}/día): {len(df_plan):,}")
    
    # === Calcular TP/SL ===
    df_plan['entry_price'] = df_plan['w_open']
    df_plan['entry_time'] = df_plan.apply(
        lambda row: _combine_date_time(pd.Timestamp(row['date']), row['start_time']),
        axis=1
    )
    
    # TP/SL por side
    df_plan['tp_mult'] = tp_mult
    df_plan['sl_mult'] = sl_mult
    df_plan['time_stop_bars'] = time_stop_bars
    
    buy_mask = df_plan['side'] == 'BUY'
    
    df_plan.loc[buy_mask, 'tp_price'] = (
        df_plan.loc[buy_mask, 'entry_price'] + 
        df_plan.loc[buy_mask, 'tp_mult'] * df_plan.loc[buy_mask, 'atr14']
    )
    df_plan.loc[buy_mask, 'sl_price'] = (
        df_plan.loc[buy_mask, 'entry_price'] - 
        df_plan.loc[buy_mask, 'sl_mult'] * df_plan.loc[buy_mask, 'atr14']
    )
    
    sell_mask = ~buy_mask
    df_plan.loc[sell_mask, 'tp_price'] = (
        df_plan.loc[sell_mask, 'entry_price'] - 
        df_plan.loc[sell_mask, 'tp_mult'] * df_plan.loc[sell_mask, 'atr14']
    )
    df_plan.loc[sell_mask, 'sl_price'] = (
        df_plan.loc[sell_mask, 'entry_price'] + 
        df_plan.loc[sell_mask, 'sl_mult'] * df_plan.loc[sell_mask, 'atr14']
    )
    
    # === Validaciones ===
    print(f"\n[05] === VALIDACIONES ===")
    print(f"[05] Trades totales en plan: {len(df_plan):,}")
    
    # Trades por día
    trades_per_day = df_plan.groupby('date_only').size()
    print(f"[05] Trades/día | mean: {trades_per_day.mean():.2f} | p50: {trades_per_day.median():.1f} | p90: {trades_per_day.quantile(0.9):.1f}")
    
    # Por window
    window_dist = df_plan['window'].value_counts()
    print(f"[05] Distribución por window:\n{window_dist}")
    
    # Prob distribution
    prob_stats = df_plan['prob_win_intraday'].describe(percentiles=[0.1, 0.5, 0.9])
    print(f"[05] Distribución prob_win_intraday:\n{prob_stats}")
    
    # Top tickers
    top_tickers = df_plan['ticker'].value_counts().head(10)
    print(f"[05] Top 10 tickers:\n{top_tickers}")
    
    # Side distribution
    side_dist = df_plan['side'].value_counts()
    print(f"[05] Side distribution:\n{side_dist}")
    
    # === Guardar ===
    cols_output = [
        'ticker', 'date', 'window', 'side',
        'prob_win_intraday',
        'entry_time', 'entry_price',
        'tp_mult', 'sl_mult', 'time_stop_bars',
        'tp_price', 'sl_price',
        'atr14', 'ema20'
    ]
    
    df_plan_export = df_plan[cols_output].copy()
    
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    df_plan_export.to_csv(output_path, index=False)
    print(f"\n[05] ✅ Plan guardado en: {output_path}")
    
    # Plan limpio (excluir splits)
    if exclude_splits and daily_bars_path and output_clean_path:
        split_tickers = _detect_split_tickers(daily_bars_path, pct_change_threshold=0.5)
        if split_tickers:
            print(f"[05] Excluyendo splits: {sorted(split_tickers)}")
        df_plan_clean = df_plan_export[~df_plan_export['ticker'].isin(split_tickers)].copy()
        df_plan_clean.to_csv(output_clean_path, index=False)
        print(f"[05] ✅ Plan limpio guardado en: {output_clean_path}")
        return df_plan_clean
    
    return df_plan_export


if __name__ == '__main__':
    WINDOWS_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_windows.parquet'
    REGIME_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\regime_table.parquet'
    MODEL_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\models\intraday_probwin_model.pkl'
    FEATURES_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\models\intraday_feature_columns.json'
    OUTPUT_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_plan.csv'
    OUTPUT_CLEAN_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\intraday_plan_clean.csv'
    DAILY_FILE = r'C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\Intradia\intraday_v2\artifacts\daily_bars.parquet'
    
    plan = generate_intraday_plan(
        WINDOWS_FILE,
        REGIME_FILE,
        MODEL_FILE,
        FEATURES_FILE,
        OUTPUT_FILE,
        threshold=0.70,
        tp_mult=0.8,
        sl_mult=0.6,
        time_stop_bars=16,
        max_trades_per_ticker_per_day=1,
        max_trades_per_day=6,
        daily_bars_path=DAILY_FILE,
        output_clean_path=OUTPUT_CLEAN_FILE,
        exclude_splits=True
    )
    
    print(f"\n[05] === MUESTRA ===")
    print(plan.head(10))
