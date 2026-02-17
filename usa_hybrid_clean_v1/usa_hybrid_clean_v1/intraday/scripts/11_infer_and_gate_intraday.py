# =============================================
# 11_infer_and_gate_intraday.py
# =============================================
"""
Genera forecast intraday con prob_win para el día actual.

Usa modelo entrenado y aplica gate básico.

Uso:
  python scripts/11_infer_and_gate_intraday.py --date 2025-11-03 --interval 15m
"""

import argparse
import os
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import joblib
import yaml


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="Fecha YYYY-MM-DD")
    ap.add_argument("--features-dir", default="features/intraday", help="Directorio de features")
    ap.add_argument("--model", default="models/clf_intraday_brf_calibrated.joblib", help="Modelo de clasificación")
    ap.add_argument("--scaler", default="", help="Scaler (opcional, si el modelo no incluye preprocesamiento)")
    ap.add_argument("--out-dir", default="reports/intraday", help="Directorio de salida")
    ap.add_argument("--config", default="config/intraday.yaml", help="Archivo de configuración")
    ap.add_argument("--prob-min", type=float, default=0.55, help="Probabilidad mínima")
    return ap.parse_args()


def load_config(config_path):
    """Cargar configuración."""
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def load_features(date_str, features_dir):
    """Cargar features del día."""
    file_path = Path(features_dir) / f"{date_str}.parquet"
    if not file_path.exists():
        print(f"[infer_intraday] ERROR: No existe {file_path}")
        return None
    
    df = pd.read_parquet(file_path)
    print(f"[infer_intraday] Cargadas {len(df)} filas de {file_path}")
    return df


def load_model_and_scaler(model_path, scaler_path):
    """Cargar modelo y scaler (si aplica)."""
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Modelo no encontrado: {model_path}")
    model = joblib.load(model_path)
    print(f"[infer_intraday] Modelo cargado: {model_path}")

    scaler = None
    if scaler_path and os.path.exists(scaler_path):
        scaler = joblib.load(scaler_path)
        print(f"[infer_intraday] Scaler cargado: {scaler_path}")
    else:
        print("[infer_intraday] Scaler: N/A (modelo con preprocesamiento o no provisto)")
    return model, scaler


def get_feature_columns(model_path):
    """Obtener lista de features del metadata (YAML o JSON)."""
    # 1) YAML al lado del modelo (compatibilidad antigua)
    yaml_meta = model_path.replace('.joblib', '_metadata.yaml')
    if os.path.exists(yaml_meta):
        with open(yaml_meta) as f:
            metadata = yaml.safe_load(f)
            cols = metadata.get('feature_names') or metadata.get('features')
            if cols:
                return cols
    # 2) JSON con mismo stem
    json_meta_same = model_path.replace('.joblib', '_metadata.json')
    if os.path.exists(json_meta_same):
        import json
        with open(json_meta_same, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
            cols = metadata.get('features') or metadata.get('feature_names')
            if cols:
                return cols
    # 3) JSON estándar del BRF (clf_intraday_brf_metadata.json)
    from pathlib import Path
    p = Path(model_path)
    json_brf = p.with_name('clf_intraday_brf_metadata.json')
    if json_brf.exists():
        import json
        with open(json_brf, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
            cols = metadata.get('features') or metadata.get('feature_names')
            if cols:
                return cols

    # Fallback: features básicos
    return [
        'RSI_14', 'EMA_9', 'EMA_20', 'EMA_50',
        'MACD', 'MACD_signal', 'MACD_hist',
        'ATR_14', 'ATR_pct', 'BB_width',
        'volume_ratio', 'volume_zscore', 'VWAP_dev',
        'spread_bps', 'turnover_ratio', 'hour', 'minute',
        'dist_to_open', 'dist_to_close', 'is_first_hour', 'is_last_hour'
    ]


def detect_direction(df):
    """
    Detectar dirección de trade (LONG o SHORT) basado en indicadores.
    Debe ser idéntico a la función en 09_make_targets_intraday.py
    """
    direction = pd.Series('LONG', index=df.index)
    
    # Condiciones para SHORT
    short_conditions = (
        (df['close'] < df['EMA_50']) &
        (df['RSI_14'] > 30) &
        (df['MACD'] < 0) &
        (df['close'] < df['BB_upper'])
    )
    
    direction[short_conditions] = 'SHORT'
    
    return direction


def predict_probabilities(df, feature_cols, model, scaler):
    """Predecir probabilidades y dirección.
    Si scaler es None, asumimos que el modelo incluye preprocesamiento (Pipeline).
    """
    # Asegurar 'direction_num' si el modelo lo requiere
    if 'direction_num' in feature_cols and 'direction_num' not in df.columns:
        if 'direction' in df.columns:
            df['direction_num'] = df['direction'].map({'LONG': 1, 'SHORT': 0}).fillna(0)
        else:
            df['direction_num'] = 1  # default LONG si no existe 'direction'

    # Verificar que tenemos todas las features (tras crear direction_num)
    missing = [f for f in feature_cols if f not in df.columns]
    if missing:
        print(f"[infer_intraday] WARN: Features faltantes: {missing}")
        # Agregar con NaN para que el imputer del Pipeline las gestione
        for f in missing:
            df[f] = np.nan

    keep_cols = ['ticker', 'timestamp']
    extras = [c for c in keep_cols if c in df.columns]
    df_pred = df[feature_cols + extras].copy()

    # Si hay scaler externo, forzar filas completas; en Pipeline, el imputer maneja NaNs
    if scaler is not None:
        df_pred = df_pred.dropna(subset=feature_cols)
        if df_pred.empty:
            print("[infer_intraday] WARN: No hay filas con features completas")
            return df
    
    # Preparar X respetando el contrato del modelo
    X_input = df_pred[feature_cols]
    if scaler is not None:
        # Ruta antigua: scaler externo + modelo sin pipeline
        X_arr = scaler.transform(X_input.values)
        proba = model.predict_proba(X_arr)[:, 1]
    else:
        # Ruta nueva: modelo es Pipeline/Calibrated con preprocesamiento
        proba = model.predict_proba(X_input)[:, 1]
    
    # Crear DF de resultados con direction categórica original
    results = pd.DataFrame({
        'ticker': df_pred['ticker'],
        'timestamp': df_pred['timestamp'] if 'timestamp' in df_pred.columns else df.index,
        'prob_win': proba
    })
    # Mantener direction original si existe
    # Merge de vuelta
    df = df.merge(
        results,
        on=[c for c in ['ticker', 'timestamp'] if c in results.columns],
        how='left'
    )
    
    print(f"[infer_intraday] Predicciones: {(~df['prob_win'].isna()).sum()} filas")
    print(f"[infer_intraday]   Prob media: {df['prob_win'].mean():.3f}")
    print(f"[infer_intraday]   Prob mediana: {df['prob_win'].median():.3f}")
    
    # Verificar si direction está presente antes de contar
    if 'direction' in df.columns:
        print(f"[infer_intraday]   LONG: {(df['direction'] == 'LONG').sum()}, SHORT: {(df['direction'] == 'SHORT').sum()}")
    else:
        print("[infer_intraday]   Direction: N/A (columna no presente)")
    
    return df


def dynamic_spread_cap(timestamp, atr_pct, volume_ratio, config):
    """Calcular spread máximo adaptativo según hora y condiciones.
    
    Política:
    - Normal: 8 bps
    - Late session: 12 bps
    - Alta vol + liquidez: 15 bps
    - Extremo (ATR > 1.5% con vol): 25 bps (días especiales)
    """
    from datetime import time
    
    filters = config.get('filters', {})
    base_bps = filters.get('spread_base_bps', 8)
    late_bps = filters.get('spread_late_bps', 12)
    high_vol_bps = filters.get('spread_high_vol_bps', 15)
    
    # Late session (15:00-16:00 NY)
    if time(15, 0) <= timestamp.time() <= time(16, 0):
        cap = late_bps
    else:
        cap = base_bps
    
    # Alta volatilidad con liquidez
    if (atr_pct >= 0.009) and (volume_ratio >= 0.5):
        cap = max(cap, high_vol_bps)
    
    # Extremo: días muy volátiles (ej: elecciones, FOMC)
    if (atr_pct >= 0.015) and (volume_ratio >= 0.4):
        cap = max(cap, 25)  # Permitir hasta 25 bps en días excepcionales
    
    return cap


def apply_basic_gate(df, prob_min, config):
    """Aplicar filtros básicos con spread adaptativo."""
    filters = config.get('filters', {})
    
    # Probabilidad mínima
    df = df[df['prob_win'] >= prob_min].copy()
    print(f"[infer_intraday] Después de prob_win >= {prob_min:.2f}: {len(df)} filas")
    
    # Whitelist de tickers
    ticker_whitelist = filters.get('ticker_whitelist', [])
    if ticker_whitelist and 'ticker' in df.columns:
        df = df[df['ticker'].isin(ticker_whitelist)]
        print(f"[infer_intraday] Después de whitelist {len(ticker_whitelist)} tickers: {len(df)} filas")
    
    # Filtro de dirección (allow_short)
    allow_short = filters.get('allow_short', True)
    if not allow_short and 'direction' in df.columns:
        df = df[df['direction'] == 'LONG']
        print(f"[infer_intraday] Después de LONG only: {len(df)} filas")
    
    # ATR
    atr_min = filters.get('atr15m_min', 0.004)
    atr_max = filters.get('atr15m_max', 0.025)
    if 'ATR_pct' in df.columns:
        df = df[(df['ATR_pct'] >= atr_min) & (df['ATR_pct'] <= atr_max)]
        print(f"[infer_intraday] Después de ATR {atr_min:.3%}-{atr_max:.3%}: {len(df)} filas")
    
    # Spread adaptativo
    if 'spread_bps' in df.columns and 'timestamp' in df.columns:
        # Cálculo robusto por iteración para evitar edge-cases de apply
        atr_series = df['ATR_pct'] if 'ATR_pct' in df.columns else pd.Series(0, index=df.index)
        vol_series = df['volume_ratio'] if 'volume_ratio' in df.columns else pd.Series(0, index=df.index)
        caps = [
            dynamic_spread_cap(ts, float(atr) if pd.notnull(atr) else 0.0, float(vol) if pd.notnull(vol) else 0.0, config)
            for ts, atr, vol in zip(df['timestamp'], atr_series, vol_series)
        ]
        df['spread_cap_bps'] = caps
        base = filters.get('spread_base_bps', 18)
        high = filters.get('spread_high_vol_bps', 35)
        
        # Log spreads antes del filtro (para diagnóstico)
        if len(df) > 0 and len(df) <= 10:
            print(f"[DEBUG] Spreads antes de filtrar (caps): {df[['ticker', 'spread_bps', 'spread_cap_bps']].values.tolist()}")
        
        df = df[df['spread_bps'] <= df['spread_cap_bps']]
        print(f"[infer_intraday] Después de spread adaptativo ({base}-{high} bps): {len(df)} filas")
    
    # Volumen
    vol_min_pct = filters.get('volume_min_percentile', 40) / 100.0
    if 'volume_ratio' in df.columns:
        df = df[df['volume_ratio'] >= vol_min_pct]
        print(f"[infer_intraday] Después de volumen >= {vol_min_pct:.1%}x MA: {len(df)} filas")
    
    return df


def snap(df, name, out_dir):
    """Guardar snapshot intermedio para debugging."""
    p = out_dir / f"forecast_{name}.parquet"
    df.to_parquet(p, index=False)
    print(f"[infer_intraday] Snapshot '{name}': {len(df)} filas -> {p.name}")


def main():
    args = parse_args()
    config = load_config(args.config)
    
    print(f"[infer_intraday] Fecha: {args.date}")
    
    # Crear directorio de salida temprano
    out_dir = Path(args.out_dir) / args.date
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Cargar features
    df = load_features(args.date, args.features_dir)
    if df is None or df.empty:
        print("[infer_intraday] ERROR: No hay features para procesar")
        return
    
    # Cargar modelo
    model, scaler = load_model_and_scaler(args.model, args.scaler)
    
    # Obtener feature columns
    feature_cols = get_feature_columns(args.model)
    print(f"[infer_intraday] Features: {len(feature_cols)}")
    
    # Predecir
    df = predict_probabilities(df, feature_cols, model, scaler)
    snap(df, "after_model", out_dir)  # Snapshot 1: raw predictions
    
    # Filtrar
    prob_min = args.prob_min if args.prob_min else config.get('filters', {}).get('prob_win_min', 0.55)
    df_filtered = apply_basic_gate(df, prob_min, config)
    snap(df_filtered, "after_filters", out_dir)  # Snapshot 2: post-filters
    
    if df_filtered.empty:
        print("[infer_intraday] WARN: No quedan señales después de filtros")
        # Guardar vacío de todas formas
        df_filtered = pd.DataFrame(columns=df.columns)
    
    # Guardar forecast final
    out_file = out_dir / "forecast_intraday.parquet"
    df_filtered.to_parquet(out_file, index=False)
    print(f"\n[infer_intraday] Forecast guardado: {out_file}")
    print(f"[infer_intraday]   Total señales: {len(df_filtered)}")
    print(f"[infer_intraday]   Tickers únicos: {df_filtered['ticker'].nunique()}")


if __name__ == "__main__":
    main()
