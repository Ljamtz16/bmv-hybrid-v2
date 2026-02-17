# =============================================
# 39_predict_tth_intraday.py
# =============================================
"""
Predice Time-to-Hit (TTH) para forecast intraday usando modelos entrenados.

Genera:
- ETTH (Expected Time To Hit) en días fraccionales
- P(TP≺SL) vía simulación Monte Carlo
- Calibración opcional

Uso:
  python scripts/39_predict_tth_intraday.py --date 2025-11-03
  python scripts/39_predict_tth_intraday.py --date 2025-11-03 --steps-per-day 26 --sims 500
"""

import argparse
import os
from pathlib import Path
import pandas as pd
import numpy as np
import joblib
import yaml
from scipy import stats


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="Fecha YYYY-MM-DD")
    ap.add_argument("--forecast-dir", default="reports/intraday", help="Directorio de forecast")
    ap.add_argument("--models-dir", default="models", help="Directorio de modelos")
    ap.add_argument("--config", default="config/intraday.yaml", help="Configuración")
    ap.add_argument("--calibration", default="data/trading/tth_calibration_intraday.json", help="Archivo de calibración")
    ap.add_argument("--steps-per-day", type=int, default=26, help="Steps por día (26 para 15m)")
    ap.add_argument("--sims", type=int, default=500, help="Simulaciones Monte Carlo")
    ap.add_argument("--use-hazard", action="store_true", help="Usar hazard discreto")
    ap.add_argument("--use-mc", action="store_true", default=True, help="Usar Monte Carlo (default)")
    return ap.parse_args()


def load_config(config_path):
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def load_calibration(calib_file):
    """Cargar escalas de calibración (anti-BOM)."""
    from pathlib import Path
    import json
    
    cal_path = Path(calib_file)
    scale_tp = 1.0
    scale_sl = 1.0
    
    if cal_path.exists():
        try:
            # Leer con encoding UTF-8 y quitar BOM si existe
            raw = cal_path.read_text(encoding='utf-8')
            raw = raw.lstrip('\ufeff')  # Remove BOM
            
            cfg = json.loads(raw)
            scale_tp = float(cfg.get('scale_tp', 1.0))
            scale_sl = float(cfg.get('scale_sl', 1.0))
            print(f"[tth_intraday] Calibración cargada: scale_tp={scale_tp}, scale_sl={scale_sl}")
        except Exception as e:
            print(f"[tth_intraday] WARN: Error al cargar calibración ({e}). Usando defaults 1.0/1.0")
    else:
        print(f"[tth_intraday] INFO: Sin calibración en {calib_file}. Usando defaults 1.0/1.0")
    
    return {'scale_tp': scale_tp, 'scale_sl': scale_sl}


def load_forecast(date_str, forecast_dir):
    file_path = Path(forecast_dir) / date_str / "forecast_intraday.parquet"
    if not file_path.exists():
        print(f"[tth_intraday] ERROR: No existe {file_path}")
        return None
    
    df = pd.read_parquet(file_path)
    print(f"[tth_intraday] Cargado forecast: {len(df)} señales")
    return df


def load_models(models_dir, use_hazard, use_mc):
    """Cargar modelos TTH."""
    models = {}
    
    if use_hazard:
        hazard_path = Path(models_dir) / "tth_hazard_intraday.joblib"
        scaler_path = Path(models_dir) / "tth_hazard_scaler_intraday.joblib"
        
        if hazard_path.exists() and scaler_path.exists():
            models['hazard'] = joblib.load(hazard_path)
            models['hazard_scaler'] = joblib.load(scaler_path)
            print("[tth_intraday] Hazard cargado")
        else:
            print("[tth_intraday] WARN: Modelos hazard no encontrados")
    
    if use_mc:
        mu_path = Path(models_dir) / "tth_mc_mu_intraday.joblib"
        sigma_path = Path(models_dir) / "tth_mc_sigma_intraday.joblib"
        scaler_path = Path(models_dir) / "tth_mc_scaler_intraday.joblib"
        
        if mu_path.exists() and sigma_path.exists() and scaler_path.exists():
            models['mc_mu'] = joblib.load(mu_path)
            models['mc_sigma'] = joblib.load(sigma_path)
            models['mc_scaler'] = joblib.load(scaler_path)
            print("[tth_intraday] MC regressors cargados")
        else:
            print("[tth_intraday] WARN: Modelos MC no encontrados")
    
    return models


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


def simulate_monte_carlo_tth(df, models, feature_cols, tp_pct, sl_pct, steps_per_day, n_sims, calibration):
    """
    Simular TTH con Monte Carlo GBM.
    
    Para intraday: steps_per_day=26 (15m intervals)
    """
    if 'mc_mu' not in models or 'mc_sigma' not in models:
        print("[tth_intraday] ERROR: Modelos MC no disponibles")
        return df
    
    # Preparar features
    missing = [f for f in feature_cols if f not in df.columns]
    if missing:
        print(f"[tth_intraday] WARN: Features faltantes: {missing}")
        for f in missing:
            df[f] = 0.0
    
    # Mantener timestamp para merges exactos por fila
    keep_cols = ['ticker', 'timestamp', 'close']
    keep_cols = [c for c in keep_cols if c in df.columns]
    df_pred = df[feature_cols + keep_cols].copy()
    df_pred = df_pred.dropna(subset=feature_cols)
    
    if df_pred.empty:
        return df
    
    # Predecir mu y sigma
    X = df_pred[feature_cols].values
    X_scaled = models['mc_scaler'].transform(X)
    
    mu_pred = models['mc_mu'].predict(X_scaled)
    sigma_pred = models['mc_sigma'].predict(X_scaled)
    
    # Bounds
    mu_pred = np.clip(mu_pred, -0.05, 0.05)
    sigma_pred = np.clip(sigma_pred, 0.005, 0.05)
    
    # Aplicar calibración
    scale_tp = calibration.get('scale_tp', 1.0)
    scale_sl = calibration.get('scale_sl', 1.0)
    
    tp_pct_cal = tp_pct * scale_tp
    sl_pct_cal = sl_pct * scale_sl
    
    # Simular
    results = []
    for idx, row in df_pred.iterrows():
        S0 = row['close']
        mu = mu_pred[idx - df_pred.index[0]]
        sigma = sigma_pred[idx - df_pred.index[0]]
        
        tp_price = S0 * (1 + tp_pct_cal)
        sl_price = S0 * (1 - sl_pct_cal)
        
        # MC simulation
        dt = 1.0 / steps_per_day  # Fracción de día por step
        max_steps = steps_per_day  # 1 día máximo
        
        tp_hits = 0
        sl_hits = 0
        tte_tp_sum = 0
        tte_sl_sum = 0
        
        for _ in range(n_sims):
            S = S0
            for step in range(max_steps):
                # GBM
                dW = np.random.normal(0, np.sqrt(dt))
                S = S * np.exp((mu - 0.5 * sigma**2) * dt + sigma * dW)
                
                # Check hits
                if S >= tp_price:
                    tp_hits += 1
                    tte_tp_sum += (step + 1) * dt
                    break
                if S <= sl_price:
                    sl_hits += 1
                    tte_sl_sum += (step + 1) * dt
                    break
        
        # Métricas
        p_tp = tp_hits / n_sims
        p_sl = sl_hits / n_sims
        p_tp_before_sl = p_tp / (p_tp + p_sl + 1e-10)
        
        etth_tp = (tte_tp_sum / tp_hits) if tp_hits > 0 else 1.0
        etth_sl = (tte_sl_sum / sl_hits) if sl_hits > 0 else 1.0
        etth = p_tp * etth_tp + p_sl * etth_sl
        
        rec = {
            'ticker': row['ticker'],
            'ETTH': etth,
            'p_tp_before_sl': p_tp_before_sl,
            'p_tp': p_tp,
            'p_sl': p_sl,
            'mu_pred': mu,
            'sigma_pred': sigma
        }
        if 'timestamp' in row:
            rec['timestamp'] = row['timestamp']
        results.append(rec)
    
    df_tth = pd.DataFrame(results)
    
    # Limpiar columnas TTH existentes si las hay (para permitir re-ejecución)
    tth_cols = ['ETTH', 'p_tp_before_sl', 'p_tp', 'p_sl', 'mu_pred', 'sigma_pred']
    for col in tth_cols:
        if col in df.columns:
            df = df.drop(columns=[col])
    
    # Merge
    # Merge por (ticker,timestamp) si está disponible; si no, por ticker
    on_cols = ['ticker', 'timestamp'] if 'timestamp' in df_tth.columns and 'timestamp' in df.columns else ['ticker']
    df = df.merge(df_tth, on=on_cols, how='left')
    
    print(f"[tth_intraday] TTH predicho para {len(df_tth)} senales")
    if 'ETTH' in df.columns and 'p_tp_before_sl' in df.columns:
        print(f"  ETTH medio: {df['ETTH'].mean():.3f} dias")
        print(f"  P(TP<SL) medio: {df['p_tp_before_sl'].mean():.2%}")
    
    return df


def main():
    args = parse_args()
    config = load_config(args.config)
    
    print(f"[tth_intraday] Fecha: {args.date}")
    print(f"[tth_intraday] Steps/día: {args.steps_per_day}, Sims: {args.sims}")
    
    # Cargar forecast
    df = load_forecast(args.date, args.forecast_dir)
    if df is None or df.empty:
        print("[tth_intraday] ERROR: No hay forecast")
        return
    
    # Cargar modelos
    models = load_models(args.models_dir, args.use_hazard, args.use_mc)
    if not models:
        print("[tth_intraday] ERROR: No hay modelos disponibles")
        return
    
    # Cargar calibración
    calibration = load_calibration(args.calibration)
    print(f"[tth_intraday] Calibración: scale_tp={calibration.get('scale_tp', 1.0)}, scale_sl={calibration.get('scale_sl', 1.0)}")
    
    # Features
    feature_cols = get_feature_columns()
    
    # Parámetros
    tp_pct = config.get('risk', {}).get('tp_pct', 0.028)
    sl_pct = config.get('risk', {}).get('sl_pct', 0.005)
    
    # Predecir TTH
    if args.use_mc and 'mc_mu' in models:
        df = simulate_monte_carlo_tth(
            df, models, feature_cols, 
            tp_pct, sl_pct, 
            args.steps_per_day, args.sims,
            calibration
        )
    
    # Guardar
    out_dir = Path(args.forecast_dir) / args.date
    out_file = out_dir / "forecast_intraday_with_tth.parquet"
    df.to_parquet(out_file, index=False)
    
    print(f"\n[tth_intraday] Forecast con TTH guardado: {out_file}")
    
    # Actualizar el forecast original para el plan
    forecast_file = out_dir / "forecast_intraday.parquet"
    df.to_parquet(forecast_file, index=False)
    print(f"[tth_intraday] Forecast actualizado: {forecast_file}")


if __name__ == "__main__":
    main()
