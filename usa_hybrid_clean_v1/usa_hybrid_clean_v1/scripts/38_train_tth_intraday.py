# =============================================
# 38_train_tth_intraday.py
# =============================================
"""
Entrena modelos TTH (Time-to-Hit) para escala intraday.

Modelos:
- Hazard discreto: RF por día hasta TP/SL
- Regresores mu/sigma: Para Monte Carlo GBM

Adaptado para:
- steps_per_day=26 (15m intervals: 6.5h * 4 = 26)
- Horizonte máximo: 1 día de trading
- Calibración para P(TP≺SL)

Uso:
  python scripts/38_train_tth_intraday.py --start 2025-09-01 --end 2025-10-31
"""

import argparse
import os
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import yaml


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="Fecha inicio YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="Fecha fin YYYY-MM-DD")
    ap.add_argument("--features-dir", default="features/intraday", help="Directorio de features")
    ap.add_argument("--out-dir", default="models", help="Directorio de salida")
    ap.add_argument("--config", default="config/intraday.yaml", help="Configuración")
    ap.add_argument("--max-days", type=int, default=1, help="Horizonte máximo en días")
    ap.add_argument("--min-samples", type=int, default=500, help="Mínimo de muestras")
    return ap.parse_args()


def load_config(config_path):
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def get_date_range(start_str, end_str):
    start = datetime.fromisoformat(start_str)
    end = datetime.fromisoformat(end_str)
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    return dates


def load_training_data(dates, features_dir):
    dfs = []
    for date in dates:
        file_path = Path(features_dir) / f"{date}.parquet"
        if file_path.exists():
            try:
                df = pd.read_parquet(file_path)
                if not df.empty:
                    dfs.append(df)
            except Exception as e:
                print(f"[train_tth_intraday] ERROR leyendo {file_path}: {e}")
    
    if not dfs:
        return None
    
    combined = pd.concat(dfs, ignore_index=True)
    print(f"[train_tth_intraday] Cargadas {len(combined)} filas de {len(dfs)} archivos")
    return combined


def get_feature_columns():
    return [
        'RSI_7', 'RSI_14',
        'EMA_9', 'EMA_20', 'EMA_50',
        'MACD', 'MACD_signal', 'MACD_hist',
        'ATR_14', 'ATR_pct',
        'BB_width',
        'volume_ratio', 'volume_zscore',
        'VWAP_dev',
        'spread_bps', 'turnover_ratio',
        'dist_to_open', 'dist_to_close',
        'is_first_hour', 'is_last_hour'
    ]


def prepare_hazard_data(df, feature_cols, max_days=1):
    """
    Preparar datos para hazard discreto por día.
    Para intraday, "día" = fracción del día de trading.
    """
    # Filtrar registros que tienen hit_type y tte_bars
    df_hits = df[df['hit_type'].isin(['TP', 'SL'])].copy()
    df_hits = df_hits.dropna(subset=['tte_bars'])
    
    if df_hits.empty:
        return None, None
    
    # Convertir tte_bars a días fraccionales
    # 26 barras = 1 día de trading
    df_hits['tte_days'] = df_hits['tte_bars'] / 26.0
    
    # Filtrar por horizonte
    df_hits = df_hits[df_hits['tte_days'] <= max_days]
    
    # Crear datasets por día fraccional (bines de 0.1 días ~= 2.6 barras)
    day_bins = np.arange(0, max_days + 0.1, 0.1)
    hazard_data = []
    
    for day_frac in day_bins[:-1]:
        df_day = df_hits[df_hits['tte_days'] >= day_frac].copy()
        if df_day.empty:
            continue
        
        # Target: hit en este intervalo
        df_day['hit_in_interval'] = ((df_day['tte_days'] >= day_frac) & 
                                      (df_day['tte_days'] < day_frac + 0.1)).astype(int)
        
        df_day['day_frac'] = day_frac
        hazard_data.append(df_day)
    
    if not hazard_data:
        return None, None
    
    combined = pd.concat(hazard_data, ignore_index=True)
    
    # Preparar X, y
    required_cols = feature_cols + ['hit_in_interval']
    combined_clean = combined[required_cols].dropna()
    
    if combined_clean.empty:
        return None, None
    
    X = combined_clean[feature_cols].values
    y = combined_clean['hit_in_interval'].values
    
    return X, y


def train_hazard_models(df, feature_cols, max_days=1):
    """Entrenar modelos de hazard discreto."""
    X, y = prepare_hazard_data(df, feature_cols, max_days)
    
    if X is None or len(X) < 100:
        print("[train_tth_intraday] WARN: Insuficientes datos para hazard")
        return None, None
    
    print(f"[train_tth_intraday] Entrenando hazard con {len(X)} muestras")
    print(f"  Eventos: {y.sum()} ({y.mean():.2%})")
    
    # Escalar
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Entrenar
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=8,
        min_samples_split=50,
        min_samples_leaf=20,
        random_state=42,
        n_jobs=-1,
        class_weight='balanced'
    )
    
    model.fit(X_scaled, y)
    
    print(f"[train_tth_intraday] Hazard entrenado (score: {model.score(X_scaled, y):.3f})")
    
    return model, scaler


def prepare_mc_data(df, feature_cols):
    """Preparar datos para regresores mu/sigma de Monte Carlo."""
    # Usar retornos futuros
    df_mc = df.dropna(subset=['ret_30m', 'ret_60m']).copy()
    
    if df_mc.empty:
        return None, None, None
    
    # Calcular mu y sigma empíricos por registro
    # Para simplificar, usar ret_60m como proxy de drift y volatilidad
    df_mc['mu_empirical'] = df_mc['ret_60m']
    df_mc['sigma_empirical'] = df_mc['ATR_pct'] * np.sqrt(26)  # Anualizar ATR a escala intraday
    
    # Preparar X, y_mu, y_sigma
    required_cols = feature_cols + ['mu_empirical', 'sigma_empirical']
    df_clean = df_mc[required_cols].dropna()
    
    if df_clean.empty:
        return None, None, None
    
    X = df_clean[feature_cols].values
    y_mu = df_clean['mu_empirical'].values
    y_sigma = df_clean['sigma_empirical'].values
    
    return X, y_mu, y_sigma


def train_mc_regressors(df, feature_cols):
    """Entrenar regresores para mu y sigma de Monte Carlo."""
    X, y_mu, y_sigma = prepare_mc_data(df, feature_cols)
    
    if X is None or len(X) < 100:
        print("[train_tth_intraday] WARN: Insuficientes datos para MC")
        return None, None, None
    
    print(f"[train_tth_intraday] Entrenando MC regressors con {len(X)} muestras")
    
    # Escalar
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Entrenar mu
    model_mu = RandomForestRegressor(
        n_estimators=100,
        max_depth=6,
        min_samples_split=50,
        random_state=42,
        n_jobs=-1
    )
    model_mu.fit(X_scaled, y_mu)
    
    # Entrenar sigma
    model_sigma = RandomForestRegressor(
        n_estimators=100,
        max_depth=6,
        min_samples_split=50,
        random_state=42,
        n_jobs=-1
    )
    model_sigma.fit(X_scaled, y_sigma)
    
    print(f"[train_tth_intraday] MC mu score: {model_mu.score(X_scaled, y_mu):.3f}")
    print(f"[train_tth_intraday] MC sigma score: {model_sigma.score(X_scaled, y_sigma):.3f}")
    
    return model_mu, model_sigma, scaler


def main():
    args = parse_args()
    config = load_config(args.config)
    
    print(f"[train_tth_intraday] Periodo: {args.start} a {args.end}")
    
    # Cargar datos
    dates = get_date_range(args.start, args.end)
    df = load_training_data(dates, args.features_dir)
    
    if df is None or df.empty:
        print("[train_tth_intraday] ERROR: No se pudieron cargar datos")
        return
    
    if len(df) < args.min_samples:
        print(f"[train_tth_intraday] ERROR: Insuficientes muestras ({len(df)} < {args.min_samples})")
        return
    
    # Features
    feature_cols = get_feature_columns()
    print(f"[train_tth_intraday] Features: {len(feature_cols)}")
    
    # Entrenar hazard
    print("\n[train_tth_intraday] === Entrenando Hazard Discreto ===")
    hazard_model, hazard_scaler = train_hazard_models(df, feature_cols, args.max_days)
    
    # Entrenar MC
    print("\n[train_tth_intraday] === Entrenando MC Regressors ===")
    mc_mu_model, mc_sigma_model, mc_scaler = train_mc_regressors(df, feature_cols)
    
    # Guardar
    os.makedirs(args.out_dir, exist_ok=True)
    
    if hazard_model is not None:
        joblib.dump(hazard_model, f"{args.out_dir}/tth_hazard_intraday.joblib")
        joblib.dump(hazard_scaler, f"{args.out_dir}/tth_hazard_scaler_intraday.joblib")
        print(f"\n[train_tth_intraday] Hazard guardado: {args.out_dir}/tth_hazard_intraday.joblib")
    
    if mc_mu_model is not None and mc_sigma_model is not None:
        joblib.dump(mc_mu_model, f"{args.out_dir}/tth_mc_mu_intraday.joblib")
        joblib.dump(mc_sigma_model, f"{args.out_dir}/tth_mc_sigma_intraday.joblib")
        joblib.dump(mc_scaler, f"{args.out_dir}/tth_mc_scaler_intraday.joblib")
        print(f"[train_tth_intraday] MC guardado: {args.out_dir}/tth_mc_*_intraday.joblib")
    
    # Metadata
    metadata = {
        'train_start': args.start,
        'train_end': args.end,
        'n_samples': len(df),
        'max_days': args.max_days,
        'steps_per_day': 26,
        'feature_names': feature_cols,
        'has_hazard': hazard_model is not None,
        'has_mc': mc_mu_model is not None
    }
    
    metadata_file = f"{args.out_dir}/tth_intraday_metadata.yaml"
    with open(metadata_file, 'w') as f:
        yaml.dump(metadata, f)
    print(f"[train_tth_intraday] Metadata: {metadata_file}")


if __name__ == "__main__":
    main()
