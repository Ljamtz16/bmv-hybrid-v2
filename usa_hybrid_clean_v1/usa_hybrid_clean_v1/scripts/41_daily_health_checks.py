"""
Script: 41_daily_health_checks.py
Valida calidad de predicciones, cobertura, distribución de regímenes y detecta drift.
Output: reports/health/daily_health_YYYY-MM-DD.json con alertas.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json

# Paths
SIGNALS_PATH = Path("data/daily/signals_with_gates.parquet")
FEATURES_PATH = Path("data/daily/features_enhanced_binary_targets.parquet")
HEALTH_DIR = Path("reports/health")
HEALTH_DIR.mkdir(parents=True, exist_ok=True)

# Thresholds
THRESHOLDS = {
    "brier_max": 0.14,
    "ece_max": 0.05,
    "coverage_min": 0.15,
    "coverage_max": 0.35,
    "psi_max": 0.2,
    "min_signals": 10
}

def compute_brier_score(y_true, y_prob):
    """Brier score = mean((y_prob - y_true)^2)"""
    return np.mean((y_prob - y_true) ** 2)

def compute_ece(y_true, y_prob, n_bins=10):
    """Expected Calibration Error"""
    bins = np.linspace(0, 1, n_bins + 1)
    bin_indices = np.digitize(y_prob, bins) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)
    
    ece = 0.0
    for i in range(n_bins):
        mask = bin_indices == i
        if mask.sum() > 0:
            bin_prob = y_prob[mask].mean()
            bin_true = y_true[mask].mean()
            bin_weight = mask.sum() / len(y_true)
            ece += bin_weight * abs(bin_prob - bin_true)
    return ece

def compute_psi(expected, actual, bins=10):
    """Population Stability Index para detectar drift"""
    def scale_range(x):
        return (x - x.min()) / (x.max() - x.min() + 1e-10)
    
    expected_scaled = scale_range(expected)
    actual_scaled = scale_range(actual)
    
    exp_hist, _ = np.histogram(expected_scaled, bins=bins)
    act_hist, _ = np.histogram(actual_scaled, bins=bins)
    
    exp_pct = (exp_hist + 1) / (exp_hist.sum() + bins)
    act_pct = (act_hist + 1) / (act_hist.sum() + bins)
    
    psi = np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct))
    return psi

def check_quality_metrics(df):
    """Valida Brier y ECE si hay targets disponibles"""
    alerts = []
    metrics = {}
    
    if "target_binary" not in df.columns or df["target_binary"].isna().all():
        metrics["brier"] = None
        metrics["ece"] = None
        alerts.append({
            "level": "info",
            "message": "No targets available for quality metrics (forward-looking mode)"
        })
        return metrics, alerts
    
    mask = df["target_binary"].notna()
    if mask.sum() < 10:
        metrics["brier"] = None
        metrics["ece"] = None
        return metrics, alerts
    
    y_true = df.loc[mask, "target_binary"].values
    y_prob = df.loc[mask, "prob_win_cal"].values
    
    brier = compute_brier_score(y_true, y_prob)
    ece = compute_ece(y_true, y_prob)
    
    metrics["brier"] = float(brier)
    metrics["ece"] = float(ece)
    
    if brier > THRESHOLDS["brier_max"]:
        alerts.append({
            "level": "warning",
            "message": f"Brier score {brier:.4f} > {THRESHOLDS['brier_max']} - Consider recalibration"
        })
    
    if ece > THRESHOLDS["ece_max"]:
        alerts.append({
            "level": "warning",
            "message": f"ECE {ece:.4f} > {THRESHOLDS['ece_max']} - Probabilities poorly calibrated"
        })
    
    return metrics, alerts

def check_coverage(df, total_features):
    """Valida cobertura de señales post-gates"""
    alerts = []
    coverage = len(df) / max(1, total_features)
    
    metrics = {
        "signals_count": int(len(df)),
        "total_features": int(total_features),
        "coverage_pct": float(coverage * 100)
    }
    
    if len(df) < THRESHOLDS["min_signals"]:
        alerts.append({
            "level": "error",
            "message": f"Only {len(df)} signals - below minimum {THRESHOLDS['min_signals']}"
        })
    
    if coverage < THRESHOLDS["coverage_min"]:
        alerts.append({
            "level": "warning",
            "message": f"Coverage {coverage:.1%} < {THRESHOLDS['coverage_min']:.0%} - Too restrictive gates"
        })
    elif coverage > THRESHOLDS["coverage_max"]:
        alerts.append({
            "level": "warning",
            "message": f"Coverage {coverage:.1%} > {THRESHOLDS['coverage_max']:.0%} - Too permissive gates"
        })
    
    return metrics, alerts

def check_regime_distribution(df):
    """Valida distribución de regímenes"""
    alerts = []
    regime_counts = df["regime"].value_counts()
    regime_pct = (regime_counts / len(df) * 100).to_dict()
    
    metrics = {
        "regime_distribution": {k: float(v) for k, v in regime_pct.items()},
        "regime_counts": {k: int(v) for k, v in regime_counts.to_dict().items()}
    }
    
    # Detectar sesgo extremo (>60% en un solo régimen)
    if max(regime_pct.values()) > 60:
        dominant = max(regime_pct, key=regime_pct.get)
        alerts.append({
            "level": "warning",
            "message": f"Regime bias: {dominant} represents {regime_pct[dominant]:.1f}% of signals"
        })
    
    return metrics, alerts

def check_ticker_concentration(df):
    """Detecta concentración excesiva por ticker"""
    alerts = []
    ticker_counts = df["ticker"].value_counts()
    top5 = ticker_counts.head(5)
    top5_pct = (top5.sum() / len(df)) * 100
    
    metrics = {
        "unique_tickers": int(df["ticker"].nunique()),
        "top5_concentration_pct": float(top5_pct),
        "top5_tickers": {k: int(v) for k, v in top5.to_dict().items()}
    }
    
    if top5_pct > 50:
        alerts.append({
            "level": "warning",
            "message": f"Top 5 tickers represent {top5_pct:.1f}% of signals - High concentration risk"
        })
    
    return metrics, alerts

def check_feature_drift(signals_df, features_df):
    """Detecta drift en features clave usando PSI"""
    alerts = []
    drift_metrics = {}
    
    # Features clave para monitoreo
    key_features = ["ret_1d", "vol_20d", "atr_14d", "pos_in_range_20d"]
    
    for feat in key_features:
        if feat not in signals_df.columns or feat not in features_df.columns:
            continue
        
        # Usar últimos 30 días como "expected", hoy como "actual"
        today = signals_df["timestamp"].max()
        last_30d = today - pd.Timedelta(days=30)
        
        expected = features_df.loc[
            (features_df["timestamp"] >= last_30d) & (features_df["timestamp"] < today),
            feat
        ].dropna()
        
        actual = signals_df[feat].dropna()
        
        if len(expected) < 100 or len(actual) < 10:
            continue
        
        psi = compute_psi(expected.values, actual.values)
        drift_metrics[feat] = float(psi)
        
        if psi > THRESHOLDS["psi_max"]:
            alerts.append({
                "level": "warning",
                "message": f"Feature drift in {feat}: PSI={psi:.3f} > {THRESHOLDS['psi_max']}"
            })
    
    return {"feature_drift": drift_metrics}, alerts

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    output_file = HEALTH_DIR / f"daily_health_{today}.json"
    
    print(f"[INFO] Running daily health checks for {today}...")
    
    # Load data
    if not SIGNALS_PATH.exists():
        print(f"[ERROR] No signals file found at {SIGNALS_PATH}")
        return
    
    signals = pd.read_parquet(SIGNALS_PATH)
    
    # Initialize report
    report = {
        "date": today,
        "timestamp": datetime.now().isoformat(),
        "metrics": {},
        "alerts": []
    }
    
    # 1. Quality metrics
    quality_metrics, quality_alerts = check_quality_metrics(signals)
    report["metrics"]["quality"] = quality_metrics
    report["alerts"].extend(quality_alerts)
    
    # 2. Coverage
    if FEATURES_PATH.exists():
        features = pd.read_parquet(FEATURES_PATH)
        total_features = len(features)
    else:
        total_features = len(signals) * 2  # Rough estimate
    
    coverage_metrics, coverage_alerts = check_coverage(signals, total_features)
    report["metrics"]["coverage"] = coverage_metrics
    report["alerts"].extend(coverage_alerts)
    
    # 3. Regime distribution
    regime_metrics, regime_alerts = check_regime_distribution(signals)
    report["metrics"]["regime"] = regime_metrics
    report["alerts"].extend(regime_alerts)
    
    # 4. Ticker concentration
    ticker_metrics, ticker_alerts = check_ticker_concentration(signals)
    report["metrics"]["concentration"] = ticker_metrics
    report["alerts"].extend(ticker_alerts)
    
    # 5. Feature drift
    if FEATURES_PATH.exists():
        drift_metrics, drift_alerts = check_feature_drift(signals, features)
        report["metrics"]["drift"] = drift_metrics
        report["alerts"].extend(drift_alerts)
    
    # Summary
    report["summary"] = {
        "total_alerts": len(report["alerts"]),
        "errors": sum(1 for a in report["alerts"] if a["level"] == "error"),
        "warnings": sum(1 for a in report["alerts"] if a["level"] == "warning"),
        "status": "FAIL" if any(a["level"] == "error" for a in report["alerts"]) else "PASS"
    }
    
    # Save report
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"HEALTH CHECK SUMMARY - {today}")
    print(f"{'='*60}")
    print(f"Status: {report['summary']['status']}")
    print(f"Total Alerts: {report['summary']['total_alerts']} "
          f"(Errors: {report['summary']['errors']}, Warnings: {report['summary']['warnings']})")
    
    if report["alerts"]:
        print(f"\nAlerts:")
        for alert in report["alerts"]:
            icon = "❌" if alert["level"] == "error" else "⚠️"
            print(f"  {icon} [{alert['level'].upper()}] {alert['message']}")
    else:
        print("\n✅ No alerts - All checks passed")
    
    print(f"\nFull report: {output_file}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
