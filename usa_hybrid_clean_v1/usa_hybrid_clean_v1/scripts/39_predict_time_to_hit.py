# =============================================
# 39_predict_time_to_hit.py
# =============================================
"""
Predice time-to-hit para señales nuevas usando modelos entrenados.

Input: forecast_with_patterns.csv o forecast_signals.csv
Output: Añade columnas p_tp_in_1d, p_tp_in_2d, p_tp_in_3d, etth_tp, etth_sl, etc.
"""

import pandas as pd
import numpy as np
import argparse
import os
import joblib
import json

def predict_hazard_discrete(X, hazard_bundle, scale_tp=1.0, scale_sl=1.0, min_haz=1e-4, max_haz=0.5):
    """
    Predice probabilidades acumuladas usando hazard discreto.
    
    Returns:
        dict con p_tp_in_1d, p_tp_in_2d, p_tp_in_3d, etth_tp, etc.
    """
    models_tp = hazard_bundle['models_tp']
    models_sl = hazard_bundle['models_sl']
    feature_cols = hazard_bundle['feature_cols']
    max_days = hazard_bundle['max_days']
    
    # Detect column suffixes (_x, _y) and map to original feature names
    available_cols = X.columns.tolist()
    mapped_features = {}  # original_name -> column_in_X
    
    for feat in feature_cols:
        if feat in available_cols:
            mapped_features[feat] = feat
        elif f"{feat}_x" in available_cols:
            mapped_features[feat] = f"{feat}_x"
        elif f"{feat}_y" in available_cols:
            mapped_features[feat] = f"{feat}_y"
        else:
            # Feature not found, will be filled with 0
            print(f"[predict_hazard] Warning: feature '{feat}' not found, will use 0")
            mapped_features[feat] = None
    
    # Build X_features with correct column names
    X_features_dict = {}
    for orig_name, col_name in mapped_features.items():
        if col_name is not None:
            X_features_dict[orig_name] = X[col_name].fillna(0)
        else:
            X_features_dict[orig_name] = 0  # Missing feature
    
    X_features = pd.DataFrame(X_features_dict)
    
    results = []
    
    for idx in range(len(X_features)):
        x_row = X_features.iloc[[idx]]
        
        # TP probabilities
        S_tp = 1.0  # Survival function
        cum_tp = []
        
        for k in range(1, max_days + 1):
            if k in models_tp:
                h_k = models_tp[k].predict_proba(x_row)[0, 1]  # P(evento en k)
            else:
                h_k = 0.01  # Default bajo si no hay modelo
            # Calibración y límites de hazard
            h_k = max(min(h_k * scale_tp, max_haz), min_haz)
            
            p_le_k = 1 - S_tp * (1 - h_k)  # P(TP <= k)
            cum_tp.append(p_le_k)
            S_tp *= (1 - h_k)  # Actualizar survival
        
        # SL probabilities
        S_sl = 1.0
        cum_sl = []
        
        for k in range(1, max_days + 1):
            if k in models_sl:
                h_k = models_sl[k].predict_proba(x_row)[0, 1]
            else:
                h_k = 0.01
            # Piso y calibración para SL (evitar 0 días/immediate event)
            h_k = max(min(h_k * scale_sl, max_haz), min_haz)
            
            p_le_k = 1 - S_sl * (1 - h_k)
            cum_sl.append(p_le_k)
            S_sl *= (1 - h_k)
        
        # Expected time-to-hit (condicional al evento en el horizonte)
        # pmf[k] = P(evento en k exactamente)
        pmf_tp = [cum_tp[0]] + [cum_tp[i] - cum_tp[i-1] for i in range(1, len(cum_tp))]
        pmf_sl = [cum_sl[0]] + [cum_sl[i] - cum_sl[i-1] for i in range(1, len(cum_sl))]
        sum_tp = sum(pmf_tp)
        sum_sl = sum(pmf_sl)
        etth_tp = (sum((k+1) * pmf_tp[k] for k in range(len(pmf_tp))) / sum_tp) if sum_tp > 1e-6 else max_days
        etth_sl = (sum((k+1) * pmf_sl[k] for k in range(len(pmf_sl))) / sum_sl) if sum_sl > 1e-6 else max_days
        
        # P(TP antes que SL) aproximado
        # Simplificación: comparar las probabilidades acumuladas finales
        p_tp_final = cum_tp[-1] if cum_tp else 0.0
        p_sl_final = cum_sl[-1] if cum_sl else 0.0
        
        if p_tp_final + p_sl_final > 0:
            p_tp_before_sl = p_tp_final / (p_tp_final + p_sl_final)
        else:
            p_tp_before_sl = 0.5
        
        # ETTH al primer evento (mínimo esperado)
        etth_first = min(etth_tp, etth_sl)
        
        result = {
            'p_tp_in_1d': cum_tp[0] if len(cum_tp) > 0 else 0.0,
            'p_tp_in_2d': cum_tp[1] if len(cum_tp) > 1 else 0.0,
            'p_tp_in_3d': cum_tp[2] if len(cum_tp) > 2 else 0.0,
            'p_sl_in_1d': cum_sl[0] if len(cum_sl) > 0 else 0.0,
            'p_sl_in_2d': cum_sl[1] if len(cum_sl) > 1 else 0.0,
            'p_sl_in_3d': cum_sl[2] if len(cum_sl) > 2 else 0.0,
            'etth_tp': etth_tp,
            'etth_sl': etth_sl,
            'etth_first_event': etth_first,
            'p_tp_before_sl': p_tp_before_sl,
        }
        results.append(result)
    
    return pd.DataFrame(results)

def simulate_monte_carlo_tth(X, mc_bundle, n_sims=1000, steps_per_day=1):
    """
    Simula TTH usando Monte Carlo con GBM.
    """
    mu_model = mc_bundle['mu_model']
    sigma_model = mc_bundle['sigma_model']
    feature_cols = mc_bundle['feature_cols']
    
    # Map features with suffix handling
    available_cols = X.columns.tolist()
    mapped_features = {}
    
    for feat in feature_cols:
        if feat in available_cols:
            mapped_features[feat] = feat
        elif f"{feat}_x" in available_cols:
            mapped_features[feat] = f"{feat}_x"
        elif f"{feat}_y" in available_cols:
            mapped_features[feat] = f"{feat}_y"
        else:
            mapped_features[feat] = None
    
    X_features_dict = {}
    for orig_name, col_name in mapped_features.items():
        if col_name is not None:
            X_features_dict[orig_name] = X[col_name].fillna(0)
        else:
            if orig_name == 'horizon_days':
                X_features_dict[orig_name] = 3  # Default horizon
            else:
                X_features_dict[orig_name] = 0
    
    X_features = pd.DataFrame(X_features_dict)
    
    # Predecir mu y sigma
    mu = mu_model.predict(X_features)
    sigma = sigma_model.predict(X_features)
    
    results = []
    
    for idx in range(len(X)):
        row = X.iloc[idx]
        px0 = 100.0  # Precio normalizado
        tp_target = px0 * (1 + row.get('tp_pct', 0.06))
        sl_target = px0 * (1 - row.get('sl_pct', 0.01))
        H = row.get('horizon_days', 3)
        
        mu_i = mu[idx]
        sigma_i = max(sigma[idx], 0.005)  # Mínimo sigma
        
        tp_hits = 0
        sl_hits = 0
        ttp_list = []
        tsl_list = []
        
        for _ in range(n_sims):
            px = px0
            dt = 1.0 / steps_per_day
            
            for s in range(int(H * steps_per_day)):
                # GBM step
                z = np.random.randn()
                px *= np.exp((mu_i - 0.5 * sigma_i**2) * dt + sigma_i * np.sqrt(dt) * z)
                
                if px >= tp_target:
                    tp_hits += 1
                    ttp_list.append((s + 1) / steps_per_day)
                    break
                elif px <= sl_target:
                    sl_hits += 1
                    tsl_list.append((s + 1) / steps_per_day)
                    break
        
        p_tp = tp_hits / n_sims
        p_sl = sl_hits / n_sims
        
        etth_tp_mc = np.mean(ttp_list) if ttp_list else H
        etth_sl_mc = np.mean(tsl_list) if tsl_list else H
        etth_first_mc = np.mean(ttp_list + tsl_list) if (ttp_list or tsl_list) else H
        
        p_tp_before_sl_mc = p_tp / (p_tp + p_sl) if (p_tp + p_sl) > 0 else 0.5
        
        result = {
            'p_tp_mc': p_tp,
            'p_sl_mc': p_sl,
            'etth_tp_mc': etth_tp_mc,
            'etth_sl_mc': etth_sl_mc,
            'etth_first_mc': etth_first_mc,
            'p_tp_before_sl_mc': p_tp_before_sl_mc,
        }
        results.append(result)
    
    return pd.DataFrame(results)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="forecast_with_patterns.csv")
    ap.add_argument("--output", default="", help="Output file, default: input con _tth.csv")
    ap.add_argument("--hazard-model", default="models/tth_hazard_discrete.joblib")
    ap.add_argument("--mc-model", default="models/tth_monte_carlo.joblib")
    ap.add_argument("--use-mc", action="store_true", help="Añadir predicciones Monte Carlo")
    ap.add_argument("--mc-sims", type=int, default=1000, help="# de simulaciones MC")
    ap.add_argument("--steps-per-day", type=int, default=1, help="Pasos por día en MC (1=diario, intradía usar 26, 78, etc.)")
    args = ap.parse_args()
    
    print(f"[predict_tth] Cargando {args.input}...")
    df = pd.read_csv(args.input)
    print(f"[predict_tth] {len(df)} señales")
    
    # Create missing features if not present
    if 'abs_y_hat' not in df.columns:
        y_hat_col = 'y_hat' if 'y_hat' in df.columns else 'y_hat_x' if 'y_hat_x' in df.columns else None
        if y_hat_col:
            df['abs_y_hat'] = df[y_hat_col].abs()
        else:
            df['abs_y_hat'] = 0.0
    
    if 'tp_pct' not in df.columns:
        df['tp_pct'] = 0.04  # Default 4% TP
    
    if 'sl_pct' not in df.columns:
        df['sl_pct'] = 0.02  # Default 2% SL
    
    print(f"[predict_tth] Features creados: abs_y_hat, tp_pct, sl_pct")
    
    # Cargar modelo hazard discreto
    if not os.path.exists(args.hazard_model):
        print(f"[predict_tth] ERROR: {args.hazard_model} no existe")
        print("[predict_tth] Ejecuta: python scripts/37_label_time_to_event.py")
        print("[predict_tth]          python scripts/38_train_time_to_hit.py")
        return
    
    hazard_bundle = joblib.load(args.hazard_model)
    print(f"[predict_tth] Modelo hazard cargado: {len(hazard_bundle['models_tp'])} días TP, "
          f"{len(hazard_bundle['models_sl'])} días SL")

    # Calibración opcional de hazards (scale_tp, scale_sl)
    scale_tp = 1.0
    scale_sl = 1.0
    calib_path = os.path.join('data', 'trading', 'tth_calibration.json')
    if os.path.exists(calib_path):
        try:
            with open(calib_path, 'r', encoding='utf-8') as f:
                j = json.load(f)
                scale_tp = float(j.get('scale_tp', 1.0))
                scale_sl = float(j.get('scale_sl', 1.0))
            print(f"[predict_tth] Calibración: scale_tp={scale_tp}, scale_sl={scale_sl}")
        except Exception as e:
            print(f"[predict_tth] WARN: No se pudo leer calibración {calib_path}: {e}")
    
    # Predecir con hazard discreto
    print("[predict_tth] Prediciendo con hazard discreto...")
    tth_hazard = predict_hazard_discrete(df, hazard_bundle, scale_tp=scale_tp, scale_sl=scale_sl)
    
    # Merge con df original
    for col in tth_hazard.columns:
        df[col] = tth_hazard[col]
    
    # Monte Carlo (opcional)
    if args.use_mc and os.path.exists(args.mc_model):
        print(f"[predict_tth] Prediciendo con Monte Carlo ({args.mc_sims} sims)...")
        mc_bundle = joblib.load(args.mc_model)
        tth_mc = simulate_monte_carlo_tth(df, mc_bundle, n_sims=args.mc_sims, steps_per_day=args.steps_per_day)
        
        for col in tth_mc.columns:
            df[col] = tth_mc[col]
    
    # Guardar
    if not args.output:
        args.output = args.input.replace('.csv', '_tth.csv')
    
    df.to_csv(args.output, index=False)
    print(f"[predict_tth] Guardado → {args.output}")
    
    # Estadísticas
    print(f"\n[predict_tth] === ESTADÍSTICAS ===")
    print(f"ETTH promedio (primer evento): {df['etth_first_event'].mean():.2f} días")
    print(f"P(TP antes que SL) promedio: {df['p_tp_before_sl'].mean():.2%}")
    print(f"\nSeñales rápidas (ETTH ≤ 2d): {(df['etth_first_event'] <= 2).sum()}")
    print(f"Señales de alta calidad (P(TP≺SL) ≥ 0.65): {(df['p_tp_before_sl'] >= 0.65).sum()}")

if __name__ == "__main__":
    main()
