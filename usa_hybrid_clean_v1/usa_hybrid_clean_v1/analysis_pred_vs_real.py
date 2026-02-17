#!/usr/bin/env python
"""
Análisis de predicción vs realidad
==================================
Gráficas y métricas: MAE, RMSE, MAPE, directional accuracy, bandas de error.

Usa: forecast_signals.csv (y_hat vs y_H3) y prob_win para calibración.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.calibration import calibration_curve
import warnings

warnings.filterwarnings("ignore")

# Configuración
REPO_ROOT = Path(__file__).resolve().parent
CSV_PATH = REPO_ROOT / "reports" / "forecast" / "2025-11" / "forecast_signals.csv"
OUTPUTS_DIR = REPO_ROOT / "outputs" / "analysis"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Estilo
sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (14, 6)
plt.rcParams["font.size"] = 10


def load_data(csv_path: Path) -> pd.DataFrame:
    """Cargar y limpiar datos."""
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"])
    # Filtrar solo donde tenemos y_H3 (realizado)
    df = df.dropna(subset=["y_H3", "y_hat"])
    print(f"✓ Datos cargados: {len(df)} filas con predicción vs realidad")
    return df


def metrics_regression(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Calcular MAE, RMSE, MAPE."""
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    
    # MAPE con protección
    eps = 1e-9
    mape = (np.abs(y_true - y_pred) / (np.abs(y_true) + eps)).mean() * 100
    
    return {"MAE": mae, "RMSE": rmse, "MAPE": mape}


def directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """% de aciertos en dirección (signo correcto)."""
    signs_match = (np.sign(y_true) == np.sign(y_pred)).astype(int)
    return signs_match.mean()


def plot_pred_vs_real_timeseries(df: pd.DataFrame, ticker: str = None):
    """Gráfica: predicción vs realidad en el tiempo (líneas)."""
    plot_df = df if ticker is None else df[df["ticker"] == ticker].copy()
    plot_df = plot_df.sort_values("date")
    
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(plot_df["date"], plot_df["y_H3"], label="Real (y_H3)", 
            linewidth=2, alpha=0.8, color="steelblue")
    ax.plot(plot_df["date"], plot_df["y_hat"], label="Predicción (y_hat)", 
            linewidth=2, alpha=0.8, color="coral")
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Retorno H3")
    ax.set_title(f"Real vs Predicción - {ticker if ticker else 'Todos los tickers'}")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    
    fname = f"01_pred_vs_real{'_' + ticker if ticker else '_all'}.png"
    plt.savefig(OUTPUTS_DIR / fname, dpi=150, bbox_inches="tight")
    print(f"  ✓ {fname}")
    plt.close()


def plot_error_timeseries(df: pd.DataFrame, ticker: str = None):
    """Gráfica: error absoluto en el tiempo."""
    plot_df = df if ticker is None else df[df["ticker"] == ticker].copy()
    plot_df = plot_df.sort_values("date").copy()
    plot_df["abs_err"] = (plot_df["y_H3"] - plot_df["y_hat"]).abs()
    
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.bar(plot_df["date"], plot_df["abs_err"], alpha=0.7, color="indianred")
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Error Absoluto")
    ax.set_title(f"Error Absoluto en el Tiempo - {ticker if ticker else 'Todos'}")
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    
    fname = f"02_error_timeseries{'_' + ticker if ticker else '_all'}.png"
    plt.savefig(OUTPUTS_DIR / fname, dpi=150, bbox_inches="tight")
    print(f"  ✓ {fname}")
    plt.close()


def plot_error_band(df: pd.DataFrame, ticker: str = None, k: float = 1.0):
    """Gráfica: predicción con banda de error (pred ± k·RMSE)."""
    plot_df = df if ticker is None else df[df["ticker"] == ticker].copy()
    plot_df = plot_df.sort_values("date").copy()
    
    rmse = np.sqrt(mean_squared_error(plot_df["y_H3"], plot_df["y_hat"]))
    band = k * rmse
    
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(plot_df["date"], plot_df["y_H3"], label="Real", linewidth=2, color="steelblue")
    ax.plot(plot_df["date"], plot_df["y_hat"], label="Predicción", linewidth=2, color="coral")
    ax.fill_between(
        plot_df["date"],
        plot_df["y_hat"] - band,
        plot_df["y_hat"] + band,
        alpha=0.2, color="coral", label=f"Banda ±{k:.1f}σ (RMSE={rmse:.6f})"
    )
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Retorno H3")
    ax.set_title(f"Predicción con Banda de Error - {ticker if ticker else 'Todos'}")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    
    fname = f"03_error_band{'_' + ticker if ticker else '_all'}.png"
    plt.savefig(OUTPUTS_DIR / fname, dpi=150, bbox_inches="tight")
    print(f"  ✓ {fname}")
    plt.close()


def plot_scatter_pred_vs_real(df: pd.DataFrame, ticker: str = None):
    """Scatter: qué tan cerca está de la diagonal y=x."""
    plot_df = df if ticker is None else df[df["ticker"] == ticker].copy()
    
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(plot_df["y_H3"], plot_df["y_hat"], alpha=0.6, s=50, color="steelblue")
    
    # Diagonal y=x
    mn = min(plot_df["y_H3"].min(), plot_df["y_hat"].min())
    mx = max(plot_df["y_H3"].max(), plot_df["y_hat"].max())
    ax.plot([mn, mx], [mn, mx], "--", color="red", linewidth=2, label="Ideal (y=x)")
    
    ax.set_xlabel("Real (y_H3)")
    ax.set_ylabel("Predicción (y_hat)")
    ax.set_title(f"Scatter Real vs Pred - {ticker if ticker else 'Todos'}")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    
    fname = f"04_scatter{'_' + ticker if ticker else '_all'}.png"
    plt.savefig(OUTPUTS_DIR / fname, dpi=150, bbox_inches="tight")
    print(f"  ✓ {fname}")
    plt.close()


def plot_calibration_curve(df: pd.DataFrame, ticker: str = None, n_bins: int = 10):
    """Curva de calibración para prob_win."""
    plot_df = df if ticker is None else df[df["ticker"] == ticker].copy()
    plot_df = plot_df.dropna(subset=["prob_win"])
    
    # Crear variable binaria: ¿ganamos? (y_H3 > 0)
    y_true_binary = (plot_df["y_H3"] > 0).astype(int)
    
    if len(plot_df) < 10:
        print(f"  ⚠ No hay datos suficientes para calibración en {ticker}")
        return
    
    try:
        prob_true, prob_pred = calibration_curve(
            y_true_binary, plot_df["prob_win"], n_bins=n_bins, strategy="uniform"
        )
        
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.plot(prob_pred, prob_true, marker="o", linewidth=2, markersize=8, label="Calibración")
        ax.plot([0, 1], [0, 1], "--", color="red", linewidth=2, label="Ideal")
        ax.set_xlabel("Probabilidad predicha (prob_win)")
        ax.set_ylabel("Frecuencia real (% de ganancias)")
        ax.set_title(f"Curva de Calibración - {ticker if ticker else 'Todos'}")
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_xlim([0, 1])
        ax.set_ylim([0, 1])
        plt.tight_layout()
        
        fname = f"05_calibration{'_' + ticker if ticker else '_all'}.png"
        plt.savefig(OUTPUTS_DIR / fname, dpi=150, bbox_inches="tight")
        print(f"  ✓ {fname}")
        plt.close()
    except Exception as e:
        print(f"  ⚠ Error en calibración: {e}")


def print_metrics_table(df: pd.DataFrame):
    """Imprime tabla de métricas por ticker y global."""
    print("\n" + "=" * 100)
    print("MÉTRICAS DE REGRESIÓN (Retorno H3)")
    print("=" * 100)
    
    # Global
    y_true = df["y_H3"].values
    y_pred = df["y_hat"].values
    metrics = metrics_regression(y_true, y_pred)
    dir_acc = directional_accuracy(y_true, y_pred)
    
    print(f"\n📊 GLOBAL (todos los tickers):")
    print(f"  MAE (Mean Absolute Error):  {metrics['MAE']:.8f}")
    print(f"  RMSE (Root Mean Squared):   {metrics['RMSE']:.8f}")
    print(f"  MAPE (Mean Absolute % Err): {metrics['MAPE']:.2f}%")
    print(f"  Directional Accuracy:       {dir_acc:.2%}")
    print(f"  Samples: {len(df)}")
    
    # Por ticker
    print(f"\n📈 POR TICKER:")
    print("-" * 100)
    
    for ticker in sorted(df["ticker"].unique()):
        subset = df[df["ticker"] == ticker]
        y_t = subset["y_H3"].values
        y_p = subset["y_hat"].values
        m = metrics_regression(y_t, y_p)
        da = directional_accuracy(y_t, y_p)
        
        print(f"{ticker:6s} | MAE: {m['MAE']:.8f} | RMSE: {m['RMSE']:.8f} | MAPE: {m['MAPE']:6.2f}% | Dir Acc: {da:6.2%} | N: {len(subset):5d}")


def print_probability_metrics(df: pd.DataFrame):
    """Imprime métricas de probabilidad (Brier score)."""
    print("\n" + "=" * 100)
    print("MÉTRICAS DE PROBABILIDAD (prob_win)")
    print("=" * 100)
    
    df_prob = df.dropna(subset=["prob_win"]).copy()
    df_prob["y_true_binary"] = (df_prob["y_H3"] > 0).astype(int)
    
    # Brier score global
    brier = ((df_prob["prob_win"] - df_prob["y_true_binary"]) ** 2).mean()
    win_rate_actual = df_prob["y_true_binary"].mean()
    win_rate_pred_mean = df_prob["prob_win"].mean()
    
    print(f"\n📊 GLOBAL:")
    print(f"  Brier Score:             {brier:.6f}")
    print(f"  Win rate actual (% H3>0): {win_rate_actual:.2%}")
    print(f"  Prob_win promedio:       {win_rate_pred_mean:.2%}")
    print(f"  Samples: {len(df_prob)}")
    
    # Por ticker
    print(f"\n📈 POR TICKER:")
    print("-" * 100)
    for ticker in sorted(df_prob["ticker"].unique()):
        subset = df_prob[df_prob["ticker"] == ticker]
        b = ((subset["prob_win"] - subset["y_true_binary"]) ** 2).mean()
        wr = subset["y_true_binary"].mean()
        print(f"{ticker:6s} | Brier: {b:.6f} | Win rate: {wr:6.2%} | Prob mean: {subset['prob_win'].mean():6.2%} | N: {len(subset):5d}")


def main():
    print("\n" + "=" * 100)
    print("ANÁLISIS PREDICCIÓN vs REALIDAD - USA HYBRID CLEAN V1")
    print("=" * 100)
    
    # Cargar datos
    if not CSV_PATH.exists():
        print(f"❌ No encontrado: {CSV_PATH}")
        return
    
    df = load_data(CSV_PATH)
    
    # Métricas
    print_metrics_table(df)
    print_probability_metrics(df)
    
    # Gráficas GLOBAL
    print(f"\n📊 Generando gráficas GLOBAL...")
    plot_pred_vs_real_timeseries(df)
    plot_error_timeseries(df)
    plot_error_band(df, k=1.0)
    plot_scatter_pred_vs_real(df)
    plot_calibration_curve(df, n_bins=10)
    
    # Gráficas POR TICKER (seleccionar los top 3 más frecuentes)
    print(f"\n📊 Generando gráficas POR TICKER...")
    top_tickers = df["ticker"].value_counts().head(3).index.tolist()
    
    for ticker in top_tickers:
        print(f"  {ticker}:")
        plot_pred_vs_real_timeseries(df, ticker=ticker)
        plot_error_timeseries(df, ticker=ticker)
        plot_error_band(df, ticker=ticker, k=1.0)
        plot_scatter_pred_vs_real(df, ticker=ticker)
        plot_calibration_curve(df, ticker=ticker, n_bins=8)
    
    print(f"\n✅ Análisis completo. Outputs en: {OUTPUTS_DIR}")


if __name__ == "__main__":
    main()
