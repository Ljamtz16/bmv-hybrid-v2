#!/usr/bin/env python
"""
MEJORA 1: Reportar SIEMPRE Global + Operable Slice
==================================================
Métricas Globales (para control):
- Precisión en TODO el dataset

Operable Slice (para trading real):
- Risk <= MEDIUM AND Conf >= 4 AND ticker en whitelist
- Este es el que REALMENTE importa para decisiones

Genera CSV con ambas metricas y visualizacion comparativa.

REFACTORED: Ahora importa operability.py (single source of truth)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings

from operability import operable_mask, get_operability_breakdown, WHITELIST_TICKERS, EXPECTED_OPERABLE_COUNT

warnings.filterwarnings("ignore")

# Configuración
REPO_ROOT = Path(__file__).resolve().parent
CSV_PATH = REPO_ROOT / "outputs" / "analysis" / "all_signals_with_confidence.csv"
OUTPUTS_DIR = REPO_ROOT / "outputs" / "analysis"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (14, 8)

# Calendario de riesgos (simplificado - en producción usar macro_event_alerts.py)
FOMC_DATES = pd.to_datetime([
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-11-05", "2025-12-17"
])

def load_data(csv_path: Path) -> pd.DataFrame:
    """Cargar y preparar datos."""
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["y_H3", "y_hat", "close"])
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    
    # Precio predicho y real
    df["price_pred"] = df["close"] * (1 + df["y_hat"])
    df["price_real"] = df["close"].shift(-3)
    df = df.dropna(subset=["price_real"])
    
    # Error
    df["price_error"] = df["price_real"] - df["price_pred"]
    df["price_error_pct"] = (df["price_error"] / df["price_pred"]) * 100
    df["abs_price_error"] = abs(df["price_error_pct"])
    
    # Dirección
    df["pred_direction"] = np.sign(df["y_hat"])
    df["real_direction"] = np.sign(df["y_H3"])
    df["direction_correct"] = (df["pred_direction"] == df["real_direction"]).astype(int)
    
    print(f"[OK] Datos cargados: {len(df):,} observaciones")
    return df


def calculate_risk_level(date):
    """Calcular nivel de riesgo en una fecha (simplificado)."""
    # FOMC ±2 días
    fomc_proximity = ((FOMC_DATES - date).days).min()
    if abs(fomc_proximity) <= 2:
        return "HIGH"
    
    # Simplificado: el resto es MEDIUM (en producción usar macro_event_alerts.py)
    return "MEDIUM"


def compute_metrics(df: pd.DataFrame, subset_name: str = "Global") -> dict:
    """Calcular todas las métricas para un subconjunto."""
    
    if len(df) == 0:
        return {"subset": subset_name, "count": 0}
    
    metrics = {
        "subset": subset_name,
        "count": len(df),
        "directional_accuracy": df["direction_correct"].mean() * 100,
        "mae": df["abs_price_error"].mean(),
        "rmse": np.sqrt((df["price_error_pct"] ** 2).mean()),
        "mean_error": df["price_error_pct"].mean(),
        "std_error": df["price_error_pct"].std(),
        "median_mae": df["abs_price_error"].median(),
        "max_error": df["abs_price_error"].max(),
        "min_error": df["abs_price_error"].min(),
    }
    
    return metrics


def generate_report(df: pd.DataFrame) -> dict:
    """Generar reporte Global + Operable Slice."""
    
    print("\n" + "="*70)
    print("REPORTE METRICAS: GLOBAL vs OPERABLE SLICE")
    print("="*70)
    
    # 1. GLOBAL
    metrics_global = compute_metrics(df, "GLOBAL")
    
    # 2. Calculate macro_risk before using operability functions
    df["macro_risk"] = df["date"].apply(calculate_risk_level)
    
    # 3. OPERABILITY BREAKDOWN (centralized from operability.py)
    print("\n┌─ OPERABILITY BREAKDOWN")
    breakdown = get_operability_breakdown(df)
    print(f"│  Global observations: {breakdown['global']:,}")
    print(f"│  Conf >= 4: {breakdown['conf_only']:,}")
    print(f"│  + Risk <= MEDIUM: {breakdown['conf_risk']:,}")
    print(f"│  + Whitelist tickers: {breakdown['operable']:,}")
    print(f"└─ Expected operables: {EXPECTED_OPERABLE_COUNT:,}")
    
    # 4. OPERABLE SLICE (using operability.py)
    # Use single source of truth: operable_mask()
    mask_operable = operable_mask(df)
    operable = df[mask_operable].copy()
    metrics_operable = compute_metrics(operable, "OPERABLE SLICE (Conf>=4 + Risk<=MEDIUM + Whitelist)")
    
    # 5. PRINT COMPARISON
    print(f"\n┌─ GLOBAL")
    print(f"│  Observaciones: {metrics_global['count']:,}")
    print(f"│  Directional Accuracy: {metrics_global['directional_accuracy']:.2f}%")
    print(f"│  MAE: {metrics_global['mae']:.2f}%")
    print(f"│  RMSE: {metrics_global['rmse']:.2f}%")
    print(f"│  Mean Error: {metrics_global['mean_error']:.2f}%")
    print(f"└─ (Control: que tan sesgado esta el modelo?)")
    
    print(f"\n┌─ OPERABLE SLICE")
    print(f"│  Observaciones: {metrics_operable['count']:,} ({metrics_operable['count']/metrics_global['count']*100:.1f}% de global)")
    print(f"│  Directional Accuracy: {metrics_operable['directional_accuracy']:.2f}%")
    print(f"│  MAE: {metrics_operable['mae']:.2f}%")
    print(f"│  RMSE: {metrics_operable['rmse']:.2f}%")
    print(f"│  Mean Error: {metrics_operable['mean_error']:.2f}%")
    print(f"└─ (Produccion: esto es lo que REALMENTE ganaremos/perderemos)")
    
    # Mejora
    improvement = metrics_operable['directional_accuracy'] - metrics_global['directional_accuracy']
    print(f"\n[MEJORA] Filtrado: +{improvement:.2f} pts accuracy")
    print(f"         Reduccion: {100 - metrics_operable['count']/metrics_global['count']*100:.1f}% del dataset")
    
    # Validación de conteo (recomendación)
    if len(operable) != EXPECTED_OPERABLE_COUNT:
        print(f"\n[WARN] Operables count: {len(operable):,} (expected: {EXPECTED_OPERABLE_COUNT:,})")
        print(f"       Delta: {len(operable) - EXPECTED_OPERABLE_COUNT}")
    else:
        print(f"\n[OK] Operables validados: {len(operable):,}")
    
    # Export CSV
    report_df = pd.DataFrame([metrics_global, metrics_operable])
    report_df.to_csv(OUTPUTS_DIR / "metrics_global_vs_operable.csv", index=False)
    print(f"\n[OK] Exportado: metrics_global_vs_operable.csv")
    
    return {
        "global": metrics_global,
        "operable": metrics_operable,
        "operable_subset": operable,
        "improvement": improvement,
        "breakdown": breakdown
    }


def plot_comparison(metrics_global: dict, metrics_operable: dict):
    """Visualizar Global vs Operable."""
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    metrics_names = ["directional_accuracy", "mae", "rmse", "mean_error"]
    titles = ["Directional Accuracy (%)", "MAE (%)", "RMSE (%)", "Mean Error (%)"]
    
    global_vals = [metrics_global[m] for m in metrics_names]
    operable_vals = [metrics_operable[m] for m in metrics_names]
    
    x = np.arange(2)
    width = 0.35
    
    for idx, (ax, metric, title) in enumerate(zip(axes.flat, metrics_names, titles)):
        vals = [global_vals[idx], operable_vals[idx]]
        bars = ax.bar(x, vals, width, color=["#FF6B6B", "#4ECDC4"], alpha=0.8)
        ax.set_ylabel(title)
        ax.set_title(title)
        ax.set_xticks(x)
        ax.set_xticklabels(["GLOBAL", "OPERABLE"])
        ax.grid(True, alpha=0.3, axis="y")
        
        # Valores en las barras
        for bar, val in zip(bars, vals):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{val:.2f}',
                   ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    plt.suptitle("Comparacion: Global vs Operable Slice\n(Lo que ves vs Lo que GANAS)", 
                 fontsize=14, fontweight='bold', y=1.00)
    plt.tight_layout()
    plt.savefig(OUTPUTS_DIR / "11_global_vs_operable_comparison.png", dpi=150, bbox_inches="tight")
    print(f"[OK] Grafica: 11_global_vs_operable_comparison.png")
    plt.close()


def main():
    """Flujo principal."""
    df = load_data(CSV_PATH)
    
    results = generate_report(df)
    
    plot_comparison(
        results["global"],
        results["operable"]
    )
    
    print("\n" + "="*70)
    print("MEJORA 1 COMPLETADA")
    print("="*70)
    print("\nProximo paso: usar OPERABLE SLICE para decisiones de trading")
    print("Regla simple: si accuracy_operable >= 55%, operar. Si no, pausar.")


if __name__ == "__main__":
    main()
