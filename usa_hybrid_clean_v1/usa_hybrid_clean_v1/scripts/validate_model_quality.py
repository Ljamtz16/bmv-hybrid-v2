# Script: validate_model_quality.py
# Validación crítica de calidad del modelo: Brier, reliability, lift, AUC por régimen
import pandas as pd
import numpy as np
import joblib
import matplotlib.pyplot as plt
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, precision_recall_curve, auc
import os

MODEL_DIR = 'models/direction/'
CALIB_DIR = 'models/calibration/'
FEATURES_PATH = 'data/daily/features_enhanced_binary_targets.parquet'
REGIME_PATH = 'data/daily/regime_daily.csv'
OUTPUT_DIR = 'reports/validation/'
VAL_PRED_PATH = 'val/oos_predictions.parquet'
VAL_PRED_CALIBRATED_PATH = 'val/oos_predictions_calibrated.parquet'


def load_oos_predictions():
    """Carga predicciones OOS; prioriza calibradas si existen."""
    # Priorizar calibradas
    if os.path.exists(VAL_PRED_CALIBRATED_PATH):
        print(f"[INFO] Cargando OOS predictions CALIBRADAS desde {VAL_PRED_CALIBRATED_PATH} ...")
        pred = pd.read_parquet(VAL_PRED_CALIBRATED_PATH)
        pred['timestamp'] = pd.to_datetime(pred['timestamp'])
        # Ya tiene prob_calibrated y regime
        return pred
    
    # Fallback a sin calibrar
    if os.path.exists(VAL_PRED_PATH):
        print(f"[INFO] Cargando OOS predictions (sin calibrar) desde {VAL_PRED_PATH} ...")
        pred = pd.read_parquet(VAL_PRED_PATH)
        pred['timestamp'] = pd.to_datetime(pred['timestamp'])
        pred = pred.rename(columns={'prob_pred': 'prob_raw', 'y_true': 'target'})
        # Si viene con tz, removerla
        if getattr(pred['timestamp'].dt, 'tz', None) is not None:
            pred['timestamp'] = pred['timestamp'].dt.tz_convert(None)
        regime_df = pd.read_csv(REGIME_PATH)
        regime_df['timestamp'] = pd.to_datetime(regime_df['timestamp'])
        # Hacer merge por fecha para evitar problemas de zona horaria
        pred['date'] = pred['timestamp'].dt.date
        regime_df['date'] = regime_df['timestamp'].dt.date
        pred = pred.merge(regime_df[['date', 'ticker', 'regime']], on=['date', 'ticker'], how='left')
        # Sin calibración adicional aún
        pred['prob_calibrated'] = pred['prob_raw']
        return pred
    
    return None

def load_data_and_predict():
    """Carga datos OOS si existen; si no, aborta para evitar leakage en evaluación."""
    oos = load_oos_predictions()
    if oos is not None:
        return oos
    raise RuntimeError("No se encontraron predicciones OOS (val/oos_predictions.parquet). Ejecute el script walk-forward primero.")

def compute_baseline_brier(y_true):
    """Brier de predictor constante (media de targets)"""
    p_constant = y_true.mean()
    return brier_score_loss(y_true, np.full(len(y_true), p_constant))

def plot_reliability_diagram(y_true, prob_pred, n_bins=10, title="Reliability Diagram", save_path=None):
    """Diagrama de confiabilidad con 10 buckets"""
    fraction_of_positives, mean_predicted_value = calibration_curve(
        y_true, prob_pred, n_bins=n_bins, strategy='uniform'
    )
    
    plt.figure(figsize=(10, 6))
    plt.plot(mean_predicted_value, fraction_of_positives, 's-', label='Model')
    plt.plot([0, 1], [0, 1], 'k--', label='Perfect Calibration')
    plt.xlabel('Mean Predicted Probability')
    plt.ylabel('Fraction of Positives')
    plt.title(title)
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"[OK] Guardado: {save_path}")
    plt.close()

def compute_lift_by_decile(df):
    """Lift y hit-rate por deciles de prob_calibrated"""
    df = df.copy()
    df['decile'] = pd.qcut(df['prob_calibrated'], q=10, labels=False, duplicates='drop')
    
    results = []
    baseline_rate = df['target'].mean()
    
    for dec in sorted(df['decile'].unique()):
        subset = df[df['decile'] == dec]
        hit_rate = subset['target'].mean()
        lift = hit_rate / baseline_rate if baseline_rate > 0 else 1.0
        
        results.append({
            'decile': dec,
            'count': len(subset),
            'hit_rate': hit_rate,
            'lift': lift,
            'mean_prob': subset['prob_calibrated'].mean()
        })
    
    return pd.DataFrame(results)

def plot_lift_curve(lift_df, save_path=None):
    """Gráfico de lift por deciles"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    
    # Hit rate por decil
    ax1.bar(lift_df['decile'], lift_df['hit_rate'], color='steelblue', alpha=0.7)
    ax1.axhline(y=lift_df['hit_rate'].mean(), color='red', linestyle='--', label='Baseline')
    ax1.set_xlabel('Decile')
    ax1.set_ylabel('Hit Rate')
    ax1.set_title('Hit Rate by Decile')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Lift
    ax2.bar(lift_df['decile'], lift_df['lift'], color='forestgreen', alpha=0.7)
    ax2.axhline(y=1.0, color='red', linestyle='--', label='No Lift')
    ax2.set_xlabel('Decile')
    ax2.set_ylabel('Lift')
    ax2.set_title('Lift by Decile')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"[OK] Guardado: {save_path}")
    plt.close()

def metrics_by_regime(df):
    """Métricas por régimen de volatilidad"""
    results = []
    
    for regime in ['low_vol', 'med_vol', 'high_vol']:
        subset = df[df['regime'] == regime]
        if len(subset) < 10:
            continue
        
        y_true = subset['target']
        prob_pred = subset['prob_calibrated']
        
        brier = brier_score_loss(y_true, prob_pred)
        logloss = log_loss(y_true, prob_pred)
        auc_roc = roc_auc_score(y_true, prob_pred)
        
        # PR-AUC
        precision, recall, _ = precision_recall_curve(y_true, prob_pred)
        auc_pr = auc(recall, precision)
        
        results.append({
            'regime': regime,
            'samples': len(subset),
            'target_mean': y_true.mean(),
            'brier': brier,
            'logloss': logloss,
            'auc_roc': auc_roc,
            'auc_pr': auc_pr
        })
    
    return pd.DataFrame(results)

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("="*60)
    print("VALIDACIÓN DE CALIDAD DEL MODELO - USA HYBRID CLEAN V2")
    print("="*60)
    
    # Cargar y predecir
    df = load_data_and_predict()
    
    y_true = df['target']
    prob_raw = df['prob_raw']
    prob_cal = df['prob_calibrated']
    
    print("\n" + "="*60)
    print("1. MÉTRICAS GLOBALES")
    print("="*60)
    
    # Brier
    brier_raw = brier_score_loss(y_true, prob_raw)
    brier_cal = brier_score_loss(y_true, prob_cal)
    brier_baseline = compute_baseline_brier(y_true)
    
    print(f"\nBrier Score:")
    print(f"  Baseline (constant p={y_true.mean():.3f}): {brier_baseline:.4f}")
    print(f"  Raw ensemble:                              {brier_raw:.4f}")
    print(f"  Calibrated:                                {brier_cal:.4f} ✅")
    print(f"  Mejora vs baseline:                        {(1 - brier_cal/brier_baseline)*100:.1f}%")
    
    # LogLoss
    logloss_raw = log_loss(y_true, prob_raw)
    logloss_cal = log_loss(y_true, prob_cal)
    
    print(f"\nLog Loss:")
    print(f"  Raw ensemble:  {logloss_raw:.4f}")
    print(f"  Calibrated:    {logloss_cal:.4f}")
    
    # AUC
    auc_raw = roc_auc_score(y_true, prob_raw)
    auc_cal = roc_auc_score(y_true, prob_cal)
    
    print(f"\nROC-AUC:")
    print(f"  Raw ensemble:  {auc_raw:.4f}")
    print(f"  Calibrated:    {auc_cal:.4f}")
    
    print("\n" + "="*60)
    print("2. RELIABILITY DIAGRAM")
    print("="*60)
    
    plot_reliability_diagram(
        y_true, prob_cal, n_bins=10,
        title="Reliability Diagram - Calibrated Probabilities",
        save_path=os.path.join(OUTPUT_DIR, 'reliability_diagram_10bins.png')
    )
    
    # Expected Calibration Error (ECE)
    fraction_of_positives, mean_predicted_value = calibration_curve(y_true, prob_cal, n_bins=10, strategy='uniform')
    ece = np.mean(np.abs(fraction_of_positives - mean_predicted_value))
    print(f"\nExpected Calibration Error (ECE): {ece:.4f}")
    if ece <= 0.05:
        print("  ✅ ECE ≤ 0.05 (Excelente)")
    elif ece <= 0.10:
        print("  ⚠️  ECE > 0.05 (Aceptable)")
    else:
        print("  ❌ ECE > 0.10 (Revisar calibración)")
    
    print("\n" + "="*60)
    print("3. LIFT & HIT-RATE POR DECILES")
    print("="*60)
    
    lift_df = compute_lift_by_decile(df)
    print("\n", lift_df.to_string(index=False))
    
    plot_lift_curve(lift_df, save_path=os.path.join(OUTPUT_DIR, 'lift_by_decile.png'))
    
    # Top-decile lift
    top_decile = lift_df[lift_df['decile'] == lift_df['decile'].max()].iloc[0]
    print(f"\n📊 Top-Decile Performance:")
    print(f"  Hit Rate: {top_decile['hit_rate']:.3f}")
    print(f"  Lift:     {top_decile['lift']:.2f}x")
    
    print("\n" + "="*60)
    print("4. MÉTRICAS POR RÉGIMEN")
    print("="*60)
    
    regime_metrics = metrics_by_regime(df)
    print("\n", regime_metrics.to_string(index=False))
    
    # Alertas por régimen
    print("\n🔍 Diagnóstico por régimen:")
    for _, row in regime_metrics.iterrows():
        regime = row['regime']
        auc = row['auc_roc']
        brier = row['brier']
        
        status = "✅" if auc > 0.60 and brier < 0.15 else "⚠️"
        print(f"  {status} {regime:10s} - AUC: {auc:.4f}, Brier: {brier:.4f}")
    
    print("\n" + "="*60)
    print("5. WARNINGS & RECOMENDACIONES")
    print("="*60)
    
    warnings = []
    
    # Check 1: Brier demasiado bueno
    if brier_cal < 0.10:
        warnings.append("⚠️  Brier < 0.10 es inusual con AUC ~0.68. VERIFICAR:")
        warnings.append("    - ¿Probabilidades están en todo el rango [0,1]?")
        warnings.append("    - ¿Calibrador se entrenó en mismo set que ensemble?")
        warnings.append("    - ¿Hay walk-forward/purged validation implementada?")
    
    # Check 2: Lift top-decile
    if top_decile['lift'] < 1.3:
        warnings.append("⚠️  Lift top-decile < 1.3x → Poder predictivo limitado")
    
    # Check 3: Varianza entre regímenes
    auc_std = regime_metrics['auc_roc'].std()
    if auc_std > 0.05:
        warnings.append(f"⚠️  Varianza AUC entre regímenes alta ({auc_std:.3f})")
        warnings.append("    → Considerar calibración separada por régimen")
    
    if warnings:
        for w in warnings:
            print(w)
    else:
        print("✅ No se detectaron issues críticos")
    
    print("\n" + "="*60)
    print("6. RESUMEN EJECUTIVO")
    print("="*60)
    
    print(f"""
Dataset:        {len(df):,} samples, {df['ticker'].nunique()} tickers
Target Balance: {y_true.mean():.1%} wins

Métricas Clave:
  Brier (cal):  {brier_cal:.4f} {'✅' if brier_cal < 0.15 else '❌'}
  ECE:          {ece:.4f} {'✅' if ece <= 0.05 else '⚠️'}
  ROC-AUC:      {auc_cal:.4f} {'✅' if auc_cal > 0.60 else '❌'}
  Top-Decile:   {top_decile['hit_rate']:.1%} ({top_decile['lift']:.2f}x lift)

Estado: {"APTO PARA PRODUCCIÓN" if (brier_cal < 0.15 and ece <= 0.10 and auc_cal > 0.60) else "REQUIERE REVISIÓN"}
""")
    
    # Guardar reporte
    report_path = os.path.join(OUTPUT_DIR, 'model_quality_report.txt')
    with open(report_path, 'w') as f:
        f.write(f"Model Quality Report - {pd.Timestamp.now()}\n")
        f.write("="*60 + "\n\n")
        f.write(f"Brier (calibrated): {brier_cal:.4f}\n")
        f.write(f"ECE: {ece:.4f}\n")
        f.write(f"ROC-AUC: {auc_cal:.4f}\n")
        f.write(f"Top-Decile Lift: {top_decile['lift']:.2f}x\n\n")
        f.write("Regime Metrics:\n")
        f.write(regime_metrics.to_string(index=False))
    
    print(f"\n[OK] Reporte completo guardado en: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
