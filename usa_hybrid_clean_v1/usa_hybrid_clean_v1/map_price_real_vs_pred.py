#!/usr/bin/env python
"""
MEJORA 4: Mapeo de Precio Real vs Predicho
===========================================
NO es suficiente con retornos. Necesitas VER curvas:

Para cada predicción:
  price_pred = close * (1 + y_pred)
  price_real = close * (1 + y_real)

Interpretación de gráficas:

✅ Si se mueven parecido (misma forma):
   → El modelo ENTIENDE la dinámica (aunque falla en el frame exacto)

❌ Si se cruzan todo el tiempo:
   → El modelo NO capta movimiento; genera números al azar

¿Qué dice el error en $?

  abs_price_error = |price_real - price_pred|

- Estable y bajo → Usable para trading
- Picos grandes → Drift / eventos / ticker ruidoso

CASOS ESPERADOS:
- CVX, XOM: curvas suaves, bajo error → USAR
- Tickers ruidosos: saltos grandes → EVITAR
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from matplotlib.gridspec import GridSpec
import warnings

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parent
CSV_PATH = REPO_ROOT / "outputs" / "analysis" / "all_signals_with_confidence.csv"
OUTPUTS_DIR = REPO_ROOT / "outputs" / "analysis"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (15, 9)


def load_and_prepare_data(csv_path: Path) -> pd.DataFrame:
    """Cargar y preparar."""
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["y_H3", "y_hat", "close"])
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    
    # CRUCIAL: Precio predicho vs real
    df["price_pred"] = df["close"] * (1 + df["y_hat"])  # Desde hoy
    df["price_real"] = df["close"].shift(-3) * (1 + df["y_H3"])  # 3 días adelante
    
    # Manejo alternativo (si y_H3 es el retorno a 3 días)
    df["price_real_alt"] = df["close"].shift(-3)
    
    # Error en precio absoluto ($)
    df["price_error"] = df["price_real"] - df["price_pred"]
    df["abs_price_error_usd"] = abs(df["price_error"])
    
    # Error en porcentaje
    df["price_error_pct"] = (df["price_error"] / df["price_pred"]) * 100
    df["abs_price_error_pct"] = abs(df["price_error_pct"])
    
    # Dirección
    df["pred_direction"] = np.sign(df["y_hat"])
    df["real_direction"] = np.sign(df["y_H3"])
    df["direction_correct"] = (df["pred_direction"] == df["real_direction"]).astype(int)
    
    print(f"✓ Datos preparados: {len(df):,} observaciones")
    print(f"✓ Precio pred medio: ${df['price_pred'].mean():.2f}")
    print(f"✓ Precio real medio: ${df['price_real'].mean():.2f}")
    print(f"✓ Error en $ medio: ${df['abs_price_error_usd'].mean():.2f}")
    
    return df


def plot_price_mapping_global(df: pd.DataFrame):
    """
    FIGURA 1: Curva global de precio predicho vs real.
    Muestra si el modelo entiende la dinámica general.
    """
    
    df_sorted = df.sort_values("date")
    
    fig, axes = plt.subplots(3, 1, figsize=(14, 12))
    
    # 1. Precios superpuestos
    ax = axes[0]
    ax.plot(df_sorted.index, df_sorted["close"], label="Precio entrada", 
            linewidth=1.5, alpha=0.5, color="gray", linestyle=":")
    ax.plot(df_sorted.index, df_sorted["price_real"], label="Precio real (H3)", 
            linewidth=2, alpha=0.8, color="steelblue")
    ax.plot(df_sorted.index, df_sorted["price_pred"], label="Precio predicho", 
            linewidth=2, alpha=0.8, color="coral")
    ax.fill_between(df_sorted.index, df_sorted["price_real"], df_sorted["price_pred"],
                    alpha=0.2, color="purple")
    ax.set_ylabel("Precio ($)")
    ax.set_title("Mapeo Global: Precio Real vs Predicho\n(¿El modelo entiende la dinámica?)")
    ax.legend(fontsize=10, loc="best")
    ax.grid(True, alpha=0.3)
    
    # 2. Error en dólares
    ax = axes[1]
    colors = ["red" if x > 0 else "green" for x in df_sorted["price_error"]]
    ax.bar(df_sorted.index, df_sorted["price_error"], color=colors, alpha=0.6, width=1)
    ax.axhline(0, color="black", linestyle="-", linewidth=0.8)
    ax.axhline(df_sorted["price_error"].mean(), color="navy", linestyle="--", 
               linewidth=1.5, label=f"Media: ${df_sorted['price_error'].mean():.2f}")
    ax.set_ylabel("Error ($)")
    ax.set_title("Error de Precio en Dólares (Real - Predicho)")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    
    # 3. Error en porcentaje con distribución
    ax = axes[2]
    ax.hist(df_sorted["abs_price_error_pct"], bins=50, color="steelblue", 
            alpha=0.7, edgecolor="black")
    ax.axvline(df_sorted["abs_price_error_pct"].mean(), color="red", 
               linestyle="--", linewidth=2, label=f"Media: {df_sorted['abs_price_error_pct'].mean():.2f}%")
    ax.axvline(df_sorted["abs_price_error_pct"].median(), color="green", 
               linestyle="--", linewidth=2, label=f"Mediana: {df_sorted['abs_price_error_pct'].median():.2f}%")
    ax.set_xlabel("Error Absoluto (%)")
    ax.set_ylabel("Frecuencia")
    ax.set_title("Distribución de Errores")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    
    plt.tight_layout()
    plt.savefig(OUTPUTS_DIR / "14a_price_mapping_global.png", dpi=150, bbox_inches="tight")
    print(f"✓ Gráfica: 14a_price_mapping_global.png")
    plt.close()


def plot_price_mapping_by_ticker(df: pd.DataFrame, top_n: int = 6):
    """
    FIGURA 2: Zoom por ticker.
    Identifica cuáles tickers el modelo entiende bien vs mal.
    """
    
    # Seleccionar top tickers por volumen
    top_tickers = df["ticker"].value_counts().head(top_n).index.tolist()
    
    fig, axes = plt.subplots(top_n, 1, figsize=(14, 12))
    if top_n == 1:
        axes = [axes]
    
    for ax, ticker in zip(axes, top_tickers):
        df_tick = df[df["ticker"] == ticker].sort_values("date")
        
        mae = df_tick["abs_price_error_pct"].mean()
        accuracy = df_tick["direction_correct"].mean() * 100
        
        ax.plot(df_tick.index, df_tick["price_real"], label="Real", 
                linewidth=2, alpha=0.8, color="steelblue")
        ax.plot(df_tick.index, df_tick["price_pred"], label="Predicho", 
                linewidth=2, alpha=0.8, color="coral", linestyle="--")
        ax.fill_between(df_tick.index, df_tick["price_real"], df_tick["price_pred"],
                       alpha=0.15, color="purple")
        
        ax.set_ylabel(f"{ticker} Precio ($)")
        ax.set_title(f"{ticker}: MAE={mae:.2f}%, Accuracy={accuracy:.1f}%")
        ax.legend(fontsize=9, loc="best")
        ax.grid(True, alpha=0.3)
    
    plt.suptitle("Mapeo por Ticker: ¿Cuáles entiende bien el modelo?", 
                 fontsize=14, fontweight='bold', y=0.995)
    plt.tight_layout()
    plt.savefig(OUTPUTS_DIR / "14b_price_mapping_by_ticker.png", dpi=150, bbox_inches="tight")
    print(f"✓ Gráfica: 14b_price_mapping_by_ticker.png")
    plt.close()


def plot_error_analysis(df: pd.DataFrame):
    """
    FIGURA 3: Análisis detallado de errores.
    ¿Dónde se rompe el modelo?
    """
    
    fig = plt.figure(figsize=(14, 10))
    gs = GridSpec(3, 2, figure=fig)
    
    # 1. Error por ticker (box plot)
    ax1 = fig.add_subplot(gs[0, :])
    ticker_errors = [df[df["ticker"] == t]["abs_price_error_pct"].values 
                     for t in df["ticker"].unique()]
    bp = ax1.boxplot(ticker_errors, labels=df["ticker"].unique(), patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_facecolor("#4ECDC4")
    ax1.set_ylabel("Error Absoluto (%)")
    ax1.set_title("Distribución de Errores por Ticker")
    ax1.grid(True, alpha=0.3, axis="y")
    
    # 2. Error vs confidence
    ax2 = fig.add_subplot(gs[1, 0])
    for conf in sorted(df["confidence_score"].unique()):
        subset = df[df["confidence_score"] == conf]
        ax2.scatter(subset["confidence_score"], subset["abs_price_error_pct"], 
                   alpha=0.5, s=30, label=f"Conf {conf}")
    ax2.set_xlabel("Confidence Score")
    ax2.set_ylabel("Error Absoluto (%)")
    ax2.set_title("Error vs Confianza\n(¿Confianza predice error?)")
    ax2.legend(fontsize=8, loc="best")
    ax2.grid(True, alpha=0.3)
    
    # 3. Error vs magnitud del movimiento
    ax3 = fig.add_subplot(gs[1, 1])
    movement_magnitude = abs(df["y_H3"])
    ax3.scatter(movement_magnitude, df["abs_price_error_pct"], 
               alpha=0.5, s=30, color="coral")
    ax3.set_xlabel("Magnitud del Movimiento Real (%)")
    ax3.set_ylabel("Error Absoluto (%)")
    ax3.set_title("Error vs Magnitud\n(¿Falla en movimientos grandes?)")
    ax3.grid(True, alpha=0.3)
    
    # 4. Error rolling (5 días)
    ax4 = fig.add_subplot(gs[2, :])
    df_sorted = df.sort_values("date")
    error_rolling = df_sorted["abs_price_error_pct"].rolling(20, min_periods=1).mean()
    ax4.plot(df_sorted.index, error_rolling, linewidth=2, color="steelblue", label="MAE (rolling 20)")
    ax4.fill_between(df_sorted.index, error_rolling, alpha=0.3, color="steelblue")
    ax4.axhline(df["abs_price_error_pct"].mean(), color="red", linestyle="--", 
               linewidth=2, label=f"MAE global: {df['abs_price_error_pct'].mean():.2f}%")
    ax4.set_xlabel("Observación")
    ax4.set_ylabel("MAE (%)")
    ax4.set_title("Error Rolling: ¿Hay Drift?")
    ax4.legend(fontsize=9)
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(OUTPUTS_DIR / "14c_error_analysis.png", dpi=150, bbox_inches="tight")
    print(f"✓ Gráfica: 14c_error_analysis.png")
    plt.close()


def generate_summary_table(df: pd.DataFrame):
    """Tabla resumen por ticker."""
    
    summary = df.groupby("ticker").agg({
        "abs_price_error_pct": ["mean", "median", "std", "max"],
        "direction_correct": "mean",
        "confidence_score": "mean",
        "price_pred": "count"
    }).round(2)
    
    summary.columns = ["MAE (%)", "Median Error (%)", "Std Dev", "Max Error (%)", 
                      "Accuracy", "Avg Conf", "Señales"]
    summary = summary.sort_values("MAE (%)")
    
    print("\n[RESUMEN POR TICKER]")
    print(summary.to_string())
    
    summary.to_csv(OUTPUTS_DIR / "14_price_mapping_summary.csv")
    print(f"\n✓ Exportado: 14_price_mapping_summary.csv")


def main():
    """Flujo principal."""
    df = load_and_prepare_data(CSV_PATH)
    
    plot_price_mapping_global(df)
    plot_price_mapping_by_ticker(df, top_n=6)
    plot_error_analysis(df)
    generate_summary_table(df)
    
    print("\n" + "="*70)
    print("✅ MEJORA 4 COMPLETADA: MAPEO DE PRECIO REAL VS PREDICHO")
    print("="*70)
    print(f"\nINTERPRETACIÓN:")
    print(f"  ✅ Si curvas se mueven parecido → Modelo entiende dinámica")
    print(f"  ❌ Si se cruzan siempre → Solo genera números")
    print(f"  → MAE bajo + curvas suave = USAR")
    print(f"  → MAE alto + saltos grandes = EVITAR")


if __name__ == "__main__":
    main()
