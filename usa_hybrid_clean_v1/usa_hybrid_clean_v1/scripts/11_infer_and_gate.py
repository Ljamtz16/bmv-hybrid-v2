"""
Script: 11_infer_and_gate.py
Inferencia con ensemble entrenado, calibración por régimen (temperature + isotonic/platt blend) y gates según política.
"""
import pandas as pd
import numpy as np
import joblib
import json
import os
from pathlib import Path

# Use freshest daily enhanced features (no target drop) for forward-looking inference
FEATURES_PATH = 'data/daily/features_daily_enhanced.parquet'
REGIME_PATH = Path('data/daily/regime_daily.csv')
MODEL_DIR = 'models/direction/'
CALIB_DIR = 'models/calibration/'
POLICY_PATH = 'config/policies.yaml'
OUTPUT_PATH = 'data/daily/signals_with_gates.parquet'
MANIFEST_PATH = 'models/direction/feature_manifest.json'


def load_feature_manifest():
    """Carga el manifiesto de features esperado por los modelos."""
    manifest_file = Path(MANIFEST_PATH)
    if not manifest_file.exists():
        print(f"[WARN] No se encontró {MANIFEST_PATH}, se usará alineación dinámica")
        return None
    
    with open(manifest_file, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    print(f"[INFO] Manifiesto cargado: {manifest['n_features']} features, v{manifest['version']}")
    return manifest


def load_models():
    rf = joblib.load(MODEL_DIR+'rf.joblib')
    xgb = joblib.load(MODEL_DIR+'xgb.joblib')
    cat = joblib.load(MODEL_DIR+'cat.joblib')
    meta = joblib.load(MODEL_DIR+'meta.joblib')
    return rf, xgb, cat, meta

def normalize_date_utc(ts_col):
    """Asegura tz-aware -> UTC -> normaliza a fecha (00:00 UTC)"""
    ts = pd.to_datetime(ts_col, utc=True, errors="coerce")
    return ts.dt.tz_convert("UTC").dt.normalize().dt.date

def load_regime_map():
    """Carga y normaliza mapa de regímenes con fallback robusto."""
    if not REGIME_PATH.exists():
        print(f"[WARN] No regime file at: {REGIME_PATH}")
        return pd.DataFrame(columns=["date","ticker","regime"])
    reg = pd.read_csv(REGIME_PATH)
    
    # Normaliza nombres esperados (case-insensitive)
    col_map = {}
    for col in reg.columns:
        col_lower = col.lower()
        if col_lower in ["date", "timestamp"]:
            col_map[col] = "timestamp"
        elif col_lower == "ticker":
            col_map[col] = "ticker"
        elif col_lower == "regime":
            col_map[col] = "regime"
    reg = reg.rename(columns=col_map)
    
    # Asegurar que tenemos las columnas mínimas
    if "timestamp" not in reg.columns or "ticker" not in reg.columns or "regime" not in reg.columns:
        print(f"[WARN] regime_daily.csv debe tener columnas timestamp/ticker/regime. Encontradas: {list(reg.columns)}")
        return pd.DataFrame(columns=["date","ticker","regime"])
    
    # Tipa y limpia
    reg["date"] = pd.to_datetime(reg["timestamp"], utc=True, errors="coerce").dt.date
    reg["ticker"] = reg["ticker"].astype(str).str.upper()
    reg["regime"] = reg["regime"].astype(str).str.lower()
    
    # Filtra valores válidos y no-nan
    valid_regimes = ["low_vol","med_vol","high_vol"]
    mask = reg["regime"].isin(valid_regimes)
    reg = reg.loc[mask, ["date","ticker","regime"]].drop_duplicates()
    
    return reg

def fallback_regime_from_atr(row, p_low=0.33, p_high=0.66):
    """Si falta régimen, derivarlo del ATR% del propio día (percentiles globales)."""
    atr = row.get("atr_pct", np.nan)
    if not np.isfinite(atr):
        return "med_vol"
    # Percentiles precomputados o dinámicos
    if atr <= row.get("atr_pct_p33", 0.015):  # ~1.5% ejemplo
        return "low_vol"
    if atr >= row.get("atr_pct_p66", 0.03):   # ~3.0% ejemplo
        return "high_vol"
    return "med_vol"

def temperature_scale(p: np.ndarray, T: float = 1.5) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    z = np.log(p / (1 - p))
    p_t = 1 / (1 + np.exp(-z / T))
    return np.clip(p_t, 1e-6, 1 - 1e-6)

def load_calibrators_for_regime(regime: str):
    iso_path = os.path.join(CALIB_DIR, f'calibrator_iso_{regime}.joblib')
    platt_path = os.path.join(CALIB_DIR, f'calibrator_platt_{regime}.joblib')
    iso = joblib.load(iso_path)
    platt = joblib.load(platt_path)
    return iso, platt

def infer_ensemble(X, rf, xgb, cat, meta):
    base_preds = np.column_stack([
        rf.predict_proba(X)[:,1],
        xgb.predict_proba(X)[:,1],
        cat.predict_proba(X)[:,1]
    ])
    return meta.predict_proba(base_preds)[:,1]

def apply_gates(df, prob_col, policy):
    # Aplicar gates dinámicos según régimen
    print(f"[INFO] Aplicando gates por régimen...")
    results = []
    for regime in df['regime'].unique():
        df_regime = df[df['regime'] == regime].copy()
        threshold = policy['thresholds']['prob_threshold'][regime]
        df_filtered = df_regime[df_regime[prob_col] >= threshold]
        print(f"  {regime}: {len(df_filtered)}/{len(df_regime)} señales (threshold={threshold})")
        results.append(df_filtered)
    return pd.concat(results) if results else pd.DataFrame()

def main():
    print("[INFO] Cargando features y régimen...")
    df = pd.read_parquet(FEATURES_PATH)

    # Normaliza fechas y tickers para merge robusto
    df["date"] = normalize_date_utc(df["timestamp"])
    df["ticker"] = df["ticker"].astype(str).str.upper()

    # Carga y merge de regímenes con fallback
    reg = load_regime_map()
    
    if len(reg) > 0:
        df = df.merge(reg, how="left", on=["date","ticker"])
        missing = df["regime"].isna().sum() if "regime" in df.columns else len(df)
    else:
        print("[INFO] No hay regímenes válidos; se usará fallback por ATR% para todas las filas")
        df["regime"] = np.nan
        missing = len(df)

    # Rellena regímenes faltantes usando ATR% del día
    if missing:
        print(f"[INFO] Regímenes faltantes: {missing}. Derivando por ATR%...")
        # Asegurar que la columna regime existe
        if "regime" not in df.columns:
            df["regime"] = np.nan
            
        # Calcular percentiles globales una única vez para fallback estable
        atr_col = 'atr_pct' if 'atr_pct' in df.columns else 'atr_pct_w'
        if atr_col not in df.columns:
            # Si no hay ATR, calcular de atr_14d/prev_close
            if 'atr_14d' in df.columns and 'close' in df.columns:
                df['prev_close'] = df.groupby('ticker')['close'].shift(1)
                df['atr_pct'] = df['atr_14d'] / df['prev_close']
                atr_col = 'atr_pct'
            else:
                print("[WARN] No se puede calcular ATR%; usando régimen 'med_vol' por defecto")
                df['regime'] = df['regime'].fillna('med_vol')
                atr_col = None
        
        if atr_col:
            p33, p66 = np.nanpercentile(df[atr_col].dropna(), [33, 66])
            df["atr_pct_p33"] = p33
            df["atr_pct_p66"] = p66
            # Vectorized regime assignment by percentiles
            df.loc[df["regime"].isna() & (df[atr_col] <= p33), "regime"] = "low_vol"
            df.loc[df["regime"].isna() & (df[atr_col] >= p66), "regime"] = "high_vol"
            df.loc[df["regime"].isna(), "regime"] = "med_vol"
        print(f"[INFO] Regímenes derivados completados.")

    # Limitar a T-1 (NY) para forward-looking
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    today_ny = pd.Timestamp.now(tz=ny).date()
    available_dates = sorted(d for d in df['date'].dropna().unique() if d <= today_ny)
    if not available_dates:
        print("[WARN] No hay fechas disponibles <= hoy en features_daily_enhanced")
        return
    t_minus_1 = available_dates[-1]  # usa la fecha más reciente disponible
    before = len(df)
    df = df[df['date'] == t_minus_1].copy()
    print(f"[INFO] Filtrado a T-1={t_minus_1}: {len(df)}/{before} filas")

    # Sanity check final para valores inválidos
    valid_regimes = ["low_vol","med_vol","high_vol"]
    bad = ~df["regime"].isin(valid_regimes)
    if bad.any():
        nbad = int(bad.sum())
        print(f"[WARN] {nbad} filas con régimen inválido; asignando 'med_vol'")
        df.loc[bad, "regime"] = "med_vol"

    if len(df) == 0:
        print("[WARN] No hay datos tras merge de régimen")
        return

    # Selección de features consistente con entrenamiento
    manifest = load_feature_manifest()
    
    if manifest:
        # Usar manifiesto para alineación determinística
        required_features = manifest['feature_names']
        expected_n = manifest['n_features']
        
        # Identificar features presentes vs faltantes
        available = set(df.columns)
        present = [f for f in required_features if f in available]
        missing = [f for f in required_features if f not in available]
        
        if missing:
            print(f"[WARN] {len(missing)} features faltantes: {missing[:5]}{'...' if len(missing)>5 else ''}")
            # Rellenar con 0 o mediana de la columna (estrategia conservadora)
            for feat in missing:
                df[feat] = 0.0
        
        # Ordenar según manifiesto (critical para consistency)
        feature_cols = required_features
        print(f"[INFO] Features alineadas con manifiesto: {len(feature_cols)}/{expected_n}")
    
    else:
        # Fallback: alineación dinámica tradicional
        exclude_cols = ['timestamp', 'date', 'ticker', 'target', 'target_binary', 'target_ordinal',
                        'open', 'high', 'low', 'close', 'volume', 'close_fwd', 'ret_fwd', 'thr_up', 'thr_dn',
                        'atr_pct_w', 'k', 'regime', 'prev_close', 'hh_20', 'll_20', 'hh_60', 'll_60',
                        'vol_avg_20', 'is_up', 'dow', 'day_of_month', 'atr_pct_p33', 'atr_pct_p66']
        feature_cols = [c for c in df.columns if c not in exclude_cols]
        feature_cols = [c for c in feature_cols if df[c].notna().sum() > len(df) * 0.8]
        feature_cols = [c for c in feature_cols if pd.api.types.is_numeric_dtype(df[c])]
        
        # Alinear columnas a las usadas en entrenamiento
        try:
            df_train_like = pd.read_parquet('data/daily/features_enhanced_binary_targets.parquet')
            exclude_train = set(exclude_cols)
            allowed_train = [c for c in df_train_like.columns if c not in exclude_train and pd.api.types.is_numeric_dtype(df_train_like[c])]
            allowed_train = [c for c in allowed_train if df_train_like[c].notna().sum() > len(df_train_like) * 0.8]
            feature_cols = [c for c in feature_cols if c in set(allowed_train)]
        except Exception:
            pass

    print("[INFO] Cargando modelos...")
    rf, xgb, cat, meta = load_models()
    expected_n = getattr(rf, 'n_features_in_', None)
    if expected_n is not None and len(feature_cols) != expected_n:
        if len(feature_cols) > expected_n:
            # Recortar determinísticamente preservando orden
            feature_cols = feature_cols[:expected_n]
            print(f"[WARN] Ajustando features de {len(df.columns)}→{expected_n} (recorte)")
        else:
            raise ValueError(f"Solo {len(feature_cols)} features disponibles, pero el modelo espera {expected_n}")

    print(f"[INFO] Features seleccionados: {len(feature_cols)}")
    X = df[feature_cols].values

    # Ensemble + calibración por régimen
    print("[INFO] Generando predicciones (ensemble → temperature → iso/platt blend)...")
    df['prob_raw'] = infer_ensemble(X, rf, xgb, cat, meta)
    df['prob_temp'] = temperature_scale(df['prob_raw'].values, T=1.5)

    # Calibración vectorizada por régimen
    prob_final = np.zeros(len(df), dtype=float)
    for regime in df['regime'].unique():
        idx = (df['regime'] == regime)
        p_temp = df.loc[idx, 'prob_temp'].values
        iso, platt = load_calibrators_for_regime(regime)
        # Isotonic: predict directamente sobre p_temp
        p_iso = iso.predict(p_temp)
        # Platt: logistic sobre logit(p_temp)
        logit_temp = np.log(p_temp / (1 - p_temp)).reshape(-1, 1)
        p_platt = platt.predict_proba(logit_temp)[:, 1]
        p_blend = 0.5 * p_iso + 0.5 * p_platt
        prob_final[idx] = np.clip(p_blend, 0.02, 0.98)

    df['prob_win'] = prob_final
    # Alias para planner
    df['prob_win_cal'] = df['prob_win']

    # Cargar política y aplicar gates
    import yaml
    with open(POLICY_PATH) as f:
        policy = yaml.safe_load(f)

    df_filtered = apply_gates(df, 'prob_win', policy)

    print(f"[OK] {len(df_filtered)} señales válidas tras gates")
    
    # Assert: T-1 único en señales (anti-historia-vieja)
    if len(df_filtered) > 0:
        # Usar columna 'date' pre-calculada (misma que se usó en filtro)
        sig_dates = df_filtered['date']
        n_dates = sig_dates.nunique()
        if n_dates != 1:
            raise ValueError(f"signals_with_gates contiene {n_dates} fechas (!= 1). Esperado T-1 único.")
        actual_date = sig_dates.iloc[0]
        if actual_date != t_minus_1:
            raise ValueError(f"signals_with_gates fecha {actual_date} != T-1={t_minus_1}")
        print(f"[VALID] Señales restringidas a T-1={t_minus_1}")
    
    df_filtered.to_parquet(OUTPUT_PATH, index=False, compression='snappy')
    print(f"[OK] Guardado en {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
