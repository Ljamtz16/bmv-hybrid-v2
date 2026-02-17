#!/usr/bin/env python
"""
MEJORA 3: Detecci√≥n de R√©gimen + Modelo Dual
==============================================
Tu comparaci√≥n volátil vs normal ya lo demuestra:
- En semana NORMAL (Aug): 50% accuracy
- En semana VOLATIL (Nov): 41.7% accuracy
→ Pérdida de 8.3 puntos con volatilidad

Solución: Detectar en TIEMPO REAL cuál régimen estamos.
Si VOLATIL → bajar expectativas, reducir posiciones
Si NORMAL → usar estrategia normal

INDICADORES DE RÉGIMEN:
1. VIX > 20 → Volatilidad alta
2. ATR relativo > X → Mucho movimiento
3. Gaps > 2% → Desconexiones
4. Histórico reciente (5d) accuracy < 50% → Drift

MODELOS:
- MODELO A (Normal): Usar como está
- MODELO B (Volatil): Usar Conf>=5, reducir posiciones 50%
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from datetime import timedelta
import warnings

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parent
CSV_PATH = REPO_ROOT / "outputs" / "analysis" / "all_signals_with_confidence.csv"
OUTPUTS_DIR = REPO_ROOT / "outputs" / "analysis"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (14, 8)


def load_and_prepare_data(csv_path: Path) -> pd.DataFrame:
    """Cargar y preparar."""
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["y_H3", "y_hat", "close"])
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    
    # Precio predicho
    df["price_pred"] = df["close"] * (1 + df["y_hat"])
    df["price_real"] = df["close"].shift(-3)
    df = df.dropna(subset=["price_real"])
    
    df["direction_correct"] = (np.sign(df["y_hat"]) == np.sign(df["y_H3"])).astype(int)
    
    print(f"✓ Datos preparados: {len(df):,} observaciones")
    return df


def calculate_atr(high, low, close, period=14):
    """Calcular Average True Range."""
    tr = np.maximum(
        high - low,
        np.maximum(
            abs(high - close.shift(1)),
            abs(low - close.shift(1))
        )
    )
    atr = tr.rolling(period).mean()
    return atr


def detect_gap(df: pd.DataFrame, min_pct=0.02) -> pd.Series:
    """Detectar gaps > min_pct."""
    df_sorted = df.sort_values(["ticker", "date"])
    df_sorted["open_prev_close"] = df_sorted.groupby("ticker")["close"].shift(1)
    gap_pct = abs((df_sorted["open"] - df_sorted["open_prev_close"]) / df_sorted["open_prev_close"])
    return gap_pct


def detect_regime(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detectar régimen en cada fecha:
    - NORMAL: VIX bajo, ATR bajo, sin gaps, accuracy reciente OK
    - VOLATILE: VIX alto, ATR alto, gaps, accuracy reciente mala
    """
    
    # Calcular ATR solo con close (simplificado)
    df_sorted = df.sort_values(["ticker", "date"])
    df_sorted["returns"] = df_sorted.groupby("ticker")["close"].pct_change()
    df_sorted["volatility_5d"] = df_sorted.groupby("ticker")["returns"].transform(
        lambda x: x.rolling(5, min_periods=1).std()
    )
    
    df["volatility_5d"] = df_sorted["volatility_5d"]
    
    # Simular VIX (en producción, usar datos reales)
    # Aproximación: volatilidad histórica de SPY
    spy_data = df[df["ticker"] == "SPY"].copy()
    if len(spy_data) > 0:
        spy_data["returns"] = spy_data["close"].pct_change()
        spy_data["volatility"] = spy_data["returns"].rolling(20).std() * np.sqrt(252) * 100
        spy_data["simulated_vix"] = spy_data["volatility"]
        
        # Merge VIX a todo el dataframe
        vix_dict = dict(zip(spy_data["date"], spy_data["simulated_vix"]))
        df["simulated_vix"] = df["date"].map(vix_dict)
    else:
        df["simulated_vix"] = 15  # Default
    
    # Accuracy reciente (5 días)
    df["accuracy_5d"] = df.groupby("ticker")["direction_correct"].transform(
        lambda x: x.rolling(5, min_periods=1).mean()
    )
    
    # REGLA DE DETECCIÓN
    def classify_regime(row):
        """Clasificar un punto de datos en régimen."""
        score = 0
        
        # VIX > 20
        if row["simulated_vix"] > 20:
            score += 2
        
        # Volatilidad > 2%
        if row["volatility_5d"] > 0.02:
            score += 1
        
        # Accuracy reciente < 50%
        if row["accuracy_5d"] < 0.5:
            score += 1
        
        # Clasificar
        if score >= 3:
            return "HIGHLY_VOLATILE"
        elif score >= 2:
            return "VOLATILE"
        else:
            return "NORMAL"
    
    df["regime"] = df.apply(classify_regime, axis=1)
    
    # Estadísticas por régimen
    print("\n[RÉGIMEN DETECTION]")
    regime_counts = df["regime"].value_counts()
    for regime, count in regime_counts.items():
        pct = count / len(df) * 100
        accuracy = df[df["regime"] == regime]["direction_correct"].mean() * 100
        print(f"  {regime:20s}: {count:6,} ({pct:5.1f}%) | Accuracy: {accuracy:5.1f}%")
    
    return df


def get_model_recommendation(regime: str) -> dict:
    """
    Basado en régimen, devolver recomendación de modelo.
    """
    
    if regime == "HIGHLY_VOLATILE":
        return {
            "regime": regime,
            "confidence_threshold": 5,
            "position_size_multiplier": 0.5,  # Reducir a 50%
            "stop_loss": -0.005,  # -0.5% (más cercano)
            "recommendation": "CAUTION - Usar solo si Conf=5, reducir posiciones 50%"
        }
    elif regime == "VOLATILE":
        return {
            "regime": regime,
            "confidence_threshold": 4,
            "position_size_multiplier": 0.75,  # Reducir a 75%
            "stop_loss": -0.01,  # -1%
            "recommendation": "CAREFUL - Usar Conf>=4, reducir posiciones 25%"
        }
    else:  # NORMAL
        return {
            "regime": regime,
            "confidence_threshold": 4,
            "position_size_multiplier": 1.0,  # 100%
            "stop_loss": -0.02,  # -2%
            "recommendation": "NORMAL - Usar estrategia estándar"
        }


def plot_regime_analysis(df: pd.DataFrame):
    """Visualizar análisis de régimen."""
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. Accuracy por régimen (con tamaño = contador)
    ax = axes[0, 0]
    regime_stats = df.groupby("regime").agg({
        "direction_correct": ["mean", "count"],
        "confidence_score": "mean"
    }).round(4)
    
    regimes = regime_stats.index
    accuracies = regime_stats[("direction_correct", "mean")] * 100
    counts = regime_stats[("direction_correct", "count")]
    
    colors = {"NORMAL": "#4ECDC4", "VOLATILE": "#FFE66D", "HIGHLY_VOLATILE": "#FF6B6B"}
    bar_colors = [colors.get(r, "gray") for r in regimes]
    
    bars = ax.bar(regimes, accuracies, color=bar_colors, alpha=0.8)
    ax.set_ylabel("Accuracy (%)")
    ax.set_title("Accuracy por Régimen")
    ax.grid(True, alpha=0.3, axis="y")
    
    for bar, count in zip(bars, counts):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'{height:.1f}%\n(n={int(count):,})',
               ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    # 2. Distribución de regímenes en el tiempo
    ax = axes[0, 1]
    df_daily = df.groupby(["date", "regime"]).size().unstack(fill_value=0)
    df_daily.plot(ax=ax, kind="area", stacked=True, 
                  color=[colors.get(c, "gray") for c in df_daily.columns], alpha=0.7)
    ax.set_xlabel("Fecha")
    ax.set_ylabel("# Observaciones")
    ax.set_title("Distribución de Regímenes en el Tiempo")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # 3. VIX simulado vs régimen
    ax = axes[1, 0]
    for regime in df["regime"].unique():
        subset = df[df["regime"] == regime]
        ax.scatter(subset.index, subset["simulated_vix"], 
                  label=regime, alpha=0.6, s=20)
    ax.axhline(20, color="red", linestyle="--", linewidth=1.5, alpha=0.5, label="VIX=20")
    ax.set_xlabel("Observación")
    ax.set_ylabel("Simulated VIX")
    ax.set_title("VIX Simulado vs Régimen")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # 4. Recomendaciones de modelo
    ax = axes[1, 1]
    ax.axis("off")
    
    recommendations = []
    for regime in sorted(df["regime"].unique()):
        rec = get_model_recommendation(regime)
        recommendations.append(f"""
╔═ {rec['regime']} ═════════════════════
║ Conf Threshold: {rec['confidence_threshold']}
║ Position Size: {rec['position_size_multiplier']*100:.0f}% de normal
║ Stop Loss: {rec['stop_loss']*100:.1f}%
║ → {rec['recommendation']}
╚═══════════════════════════════════════
        """)
    
    text = "\n".join(recommendations)
    ax.text(0.05, 0.95, text, transform=ax.transAxes, fontsize=10,
           verticalalignment='top', fontfamily='monospace',
           bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
    
    plt.suptitle("Análisis de Régimen: NORMAL vs VOLATILE", 
                 fontsize=14, fontweight='bold', y=0.995)
    plt.tight_layout()
    plt.savefig(OUTPUTS_DIR / "13_regime_detection.png", dpi=150, bbox_inches="tight")
    print(f"\n✓ Gráfica: 13_regime_detection.png")
    plt.close()


def main():
    """Flujo principal."""
    df = load_and_prepare_data(CSV_PATH)
    
    df = detect_regime(df)
    
    plot_regime_analysis(df)
    
    # Export
    df.to_csv(OUTPUTS_DIR / "regime_detection.csv", index=False)
    print(f"\n✓ Exportado: regime_detection.csv")
    
    print("\n" + "="*70)
    print("✅ MEJORA 3 COMPLETADA: DETECCIÓN DE RÉGIMEN")
    print("="*70)
    print(f"\nRESUMEN:")
    print(f"  El modelo entiende que hay 2 modos de operación")
    print(f"  Régimen NORMAL: usa estrategia estándar")
    print(f"  Régimen VOLATILE: reduce posiciones 25-50%, exige Conf>=5")
    print(f"\nSiguiente: auto-detectar al inicio de cada día")


if __name__ == "__main__":
    main()
