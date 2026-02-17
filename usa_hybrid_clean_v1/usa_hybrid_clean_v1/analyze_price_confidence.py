#!/usr/bin/env python
"""
Mapear Precio Real vs Predicho + Reglas de Confianza
=====================================================
Responde:
  1. ¿El modelo entiende la dinámica del precio? (gráficas de precio)
  2. ¿Cuándo confiar en el modelo? (reglas automáticas)
  3. ¿Cuáles son buenas señales de trading? (filtros)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings

warnings.filterwarnings("ignore")

# Configuración
REPO_ROOT = Path(__file__).resolve().parent
CSV_PATH = REPO_ROOT / "reports" / "forecast" / "2025-11" / "forecast_signals.csv"
OUTPUTS_DIR = REPO_ROOT / "outputs" / "analysis"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (14, 6)
plt.rcParams["font.size"] = 10


def load_and_prepare_data(csv_path: Path) -> pd.DataFrame:
    """Cargar datos y preparar columnas de precio."""
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["y_H3", "y_hat", "close"])
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    
    # CLAVE: Construir precio predicho del retorno
    # Si y_hat es retorno a 3 días, el precio predicho es:
    df["price_pred"] = df["close"] * (1 + df["y_hat"])
    df["price_real"] = df["close"].shift(-3)  # Precio real 3 días después
    
    # Eliminar NaN que introdujimos con shift
    df = df.dropna(subset=["price_real"])
    
    # Error de precio
    df["price_error"] = df["price_real"] - df["price_pred"]
    df["price_error_pct"] = (df["price_error"] / df["price_pred"]) * 100
    
    print(f"✓ Datos preparados: {len(df):,} observaciones")
    print(f"  Tickers: {df['ticker'].nunique()}")
    print(f"  Período: {df['date'].min().date()} a {df['date'].max().date()}")
    
    return df


def plot_price_timeseries(df: pd.DataFrame, ticker: str = None):
    """Gráfica 1: Precio real vs predicho en el tiempo (líneas)."""
    plot_df = df if ticker is None else df[df["ticker"] == ticker].copy()
    plot_df = plot_df.sort_values("date")
    
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(plot_df["date"], plot_df["close"], label="Precio actual", 
            linewidth=2, alpha=0.7, color="gray", linestyle="--")
    ax.plot(plot_df["date"], plot_df["price_real"], label="Precio real (real)", 
            linewidth=2.5, alpha=0.8, color="steelblue")
    ax.plot(plot_df["date"], plot_df["price_pred"], label="Precio predicho", 
            linewidth=2.5, alpha=0.8, color="coral")
    ax.fill_between(plot_df["date"], plot_df["price_real"], plot_df["price_pred"], 
                    alpha=0.15, color="purple", label="Error")
    
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Precio ($)")
    ax.set_title(f"Precio Real vs Predicho - {ticker if ticker else 'Global'}")
    ax.legend(fontsize=10, loc="best")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    
    fname = f"10_price_timeseries{'_' + ticker if ticker else '_all'}.png"
    plt.savefig(OUTPUTS_DIR / fname, dpi=150, bbox_inches="tight")
    print(f"  ✓ {fname}")
    plt.close()


def plot_price_error(df: pd.DataFrame, ticker: str = None):
    """Gráfica 2: Error de precio ($)."""
    plot_df = df if ticker is None else df[df["ticker"] == ticker].copy()
    plot_df = plot_df.sort_values("date")
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    
    # Error en dólares
    colors1 = ["red" if x > 0 else "green" for x in plot_df["price_error"]]
    ax1.bar(plot_df["date"], plot_df["price_error"], color=colors1, alpha=0.7)
    ax1.axhline(0, color="black", linestyle="-", linewidth=0.8)
    ax1.set_ylabel("Error en $ (Real - Predicho)")
    ax1.set_title(f"Error de Precio (Dinero) - {ticker if ticker else 'Global'}")
    ax1.grid(True, alpha=0.3, axis="y")
    
    # Error en porcentaje
    colors2 = ["red" if x > 0 else "green" for x in plot_df["price_error_pct"]]
    ax2.bar(plot_df["date"], plot_df["price_error_pct"], color=colors2, alpha=0.7)
    ax2.axhline(0, color="black", linestyle="-", linewidth=0.8)
    ax2.set_ylabel("Error en % del precio predicho")
    ax2.set_xlabel("Fecha")
    ax2.set_title(f"Error de Precio (%) - {ticker if ticker else 'Global'}")
    ax2.grid(True, alpha=0.3, axis="y")
    
    plt.tight_layout()
    fname = f"11_price_error{'_' + ticker if ticker else '_all'}.png"
    plt.savefig(OUTPUTS_DIR / fname, dpi=150, bbox_inches="tight")
    print(f"  ✓ {fname}")
    plt.close()


def plot_price_scatter(df: pd.DataFrame, ticker: str = None):
    """Gráfica 3: Scatter precio real vs predicho."""
    plot_df = df if ticker is None else df[df["ticker"] == ticker].copy()
    
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.scatter(plot_df["price_pred"], plot_df["price_real"], alpha=0.6, s=50, color="steelblue")
    
    # Diagonal perfecta
    mn = min(plot_df["price_pred"].min(), plot_df["price_real"].min())
    mx = max(plot_df["price_pred"].max(), plot_df["price_real"].max())
    ax.plot([mn, mx], [mn, mx], "--", color="red", linewidth=2.5, label="Perfecto (y=x)")
    
    ax.set_xlabel("Precio Predicho ($)")
    ax.set_ylabel("Precio Real ($)")
    ax.set_title(f"Scatter: Precio Real vs Predicho - {ticker if ticker else 'Global'}")
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    
    fname = f"12_price_scatter{'_' + ticker if ticker else '_all'}.png"
    plt.savefig(OUTPUTS_DIR / fname, dpi=150, bbox_inches="tight")
    print(f"  ✓ {fname}")
    plt.close()


def plot_price_error_distribution(df: pd.DataFrame, ticker: str = None):
    """Gráfica 4: Distribución del error de precio."""
    plot_df = df if ticker is None else df[df["ticker"] == ticker].copy()
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    
    # Histograma error $
    ax1.hist(plot_df["price_error"], bins=40, alpha=0.7, color="steelblue", edgecolor="black")
    ax1.axvline(0, color="red", linestyle="--", linewidth=2, label="Sin sesgo")
    ax1.axvline(plot_df["price_error"].mean(), color="orange", linestyle="--", linewidth=2, 
                label=f"Media={plot_df['price_error'].mean():.2f}")
    ax1.set_xlabel("Error en $ (Real - Predicho)")
    ax1.set_ylabel("Frecuencia")
    ax1.set_title(f"Distribución Error $ - {ticker if ticker else 'Global'}")
    ax1.legend()
    ax1.grid(True, alpha=0.3, axis="y")
    
    # Histograma error %
    ax2.hist(plot_df["price_error_pct"], bins=40, alpha=0.7, color="coral", edgecolor="black")
    ax2.axvline(0, color="red", linestyle="--", linewidth=2, label="Sin sesgo")
    ax2.axvline(plot_df["price_error_pct"].mean(), color="orange", linestyle="--", linewidth=2,
                label=f"Media={plot_df['price_error_pct'].mean():.2f}%")
    ax2.set_xlabel("Error en % del precio predicho")
    ax2.set_ylabel("Frecuencia")
    ax2.set_title(f"Distribución Error % - {ticker if ticker else 'Global'}")
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis="y")
    
    plt.tight_layout()
    fname = f"13_price_error_dist{'_' + ticker if ticker else '_all'}.png"
    plt.savefig(OUTPUTS_DIR / fname, dpi=150, bbox_inches="tight")
    print(f"  ✓ {fname}")
    plt.close()


def define_confidence_rules(df: pd.DataFrame) -> pd.DataFrame:
    """
    Definir reglas automáticas de confianza.
    
    CUÁNDO CONFIAR EN EL MODELO:
    1. Probabilidad extrema (>0.65 o <0.35)
    2. Predicción y tendencia van juntas
    3. Error histórico bajo para ese ticker
    4. Precio cae dentro de banda de error
    5. No hay eventos de alto impacto
    """
    df = df.copy()
    
    # ===== REGLA 1: Probabilidad extrema =====
    df["conf_1_prob_extreme"] = (df["prob_win"] >= 0.65) | (df["prob_win"] <= 0.35)
    
    # ===== REGLA 2: Predicción y tendencia van juntas =====
    # Tendencia: comparar con media móvil
    df["sma_10"] = df.groupby("ticker")["close"].transform(lambda x: x.rolling(10).mean())
    df["conf_2_above_sma"] = df["close"] > df["sma_10"]
    df["pred_bullish"] = df["y_hat"] > 0
    
    # Confía si ambos están de acuerdo
    df["conf_2_trend_aligned"] = (df["conf_2_above_sma"] & df["pred_bullish"]) | \
                                  (~df["conf_2_above_sma"] & ~df["pred_bullish"])
    
    # ===== REGLA 3: Error histórico bajo para ese ticker =====
    ticker_mae = df.groupby("ticker")["price_error_pct"].transform(lambda x: x.abs().mean())
    global_mae = df["price_error_pct"].abs().mean()
    df["conf_3_low_error"] = ticker_mae < global_mae
    
    # ===== REGLA 4: Precio cae dentro de banda =====
    ticker_std = df.groupby("ticker")["price_error"].transform(lambda x: x.std())
    df["within_band"] = df["price_error"].abs() <= ticker_std
    df["conf_4_within_band"] = df["within_band"]
    
    # ===== REGLA 5: Nota simple: sin eventos (simplificado) =====
    # En producción, verificarías calendario económico
    df["conf_5_no_event"] = True  # Placeholder
    
    # ===== CONFIDENCE SCORE: contar cuántas reglas se cumplen =====
    df["confidence_score"] = (
        df["conf_1_prob_extreme"].astype(int) +
        df["conf_2_trend_aligned"].astype(int) +
        df["conf_3_low_error"].astype(int) +
        df["conf_4_within_band"].astype(int) +
        df["conf_5_no_event"].astype(int)
    )
    
    # Categoría de confianza
    df["confidence_level"] = pd.cut(df["confidence_score"], 
                                     bins=[-1, 1, 2, 3, 5],
                                     labels=["❌ Baja", "⚠️ Media", "✓ Alta", "✅ Muy Alta"])
    
    return df


def define_trading_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Define señales automáticas de trading basadas en confianza."""
    df = df.copy()
    
    # Señal básica: probabilidad y dirección
    df["signal_direction"] = "NEUTRAL"
    df.loc[(df["prob_win"] >= 0.55) & (df["y_hat"] > 0), "signal_direction"] = "BULLISH"
    df.loc[(df["prob_win"] >= 0.55) & (df["y_hat"] <= 0), "signal_direction"] = "BEARISH"
    
    # Filtro de confianza
    df["tradeable"] = df["confidence_score"] >= 3  # Al menos 3 condiciones
    
    # Señal final: combina dirección + confianza
    df["trading_signal"] = "NO_TRADE"
    df.loc[(df["tradeable"]) & (df["signal_direction"] == "BULLISH"), "trading_signal"] = "BUY"
    df.loc[(df["tradeable"]) & (df["signal_direction"] == "BEARISH"), "trading_signal"] = "SELL"
    
    return df


def print_confidence_analysis(df: pd.DataFrame):
    """Imprime análisis de confianza."""
    print("\n" + "=" * 100)
    print("ANÁLISIS DE CONFIANZA - REGLAS AUTOMÁTICAS")
    print("=" * 100)
    
    # Global
    print("\n📊 GLOBAL:")
    print(f"  Señales BUY totales:    {(df['trading_signal'] == 'BUY').sum():5d} ({(df['trading_signal'] == 'BUY').mean():.2%})")
    print(f"  Señales SELL totales:   {(df['trading_signal'] == 'SELL').sum():5d} ({(df['trading_signal'] == 'SELL').mean():.2%})")
    print(f"  Señales NO_TRADE:       {(df['trading_signal'] == 'NO_TRADE').sum():5d} ({(df['trading_signal'] == 'NO_TRADE').mean():.2%})")
    print(f"\n  Confianza promedio (0-5): {df['confidence_score'].mean():.2f}")
    
    # Por nivel
    print("\n📈 DISTRIBUCIÓN POR NIVEL DE CONFIANZA:")
    conf_dist = df["confidence_level"].value_counts().sort_index(ascending=False)
    for level, count in conf_dist.items():
        print(f"  {level:15s}: {count:5d} ({count/len(df):.2%})")
    
    # Por ticker
    print("\n📍 POR TICKER (Top 5):")
    print("-" * 100)
    top_tickers = df["ticker"].value_counts().head(5).index
    for ticker in top_tickers:
        subset = df[df["ticker"] == ticker]
        buys = (subset["trading_signal"] == "BUY").sum()
        sells = (subset["trading_signal"] == "SELL").sum()
        avg_conf = subset["confidence_score"].mean()
        price_err = subset["price_error_pct"].abs().mean()
        
        print(f"{ticker:6s} | BUY: {buys:3d} | SELL: {sells:3d} | Conf: {avg_conf:.2f}/5 | Error%: {price_err:6.2f}%")
    
    # Reglas que más se cumplen
    print("\n🎯 REGLAS MÁS FRECUENTES:")
    print(f"  1. Prob extreme:        {df['conf_1_prob_extreme'].mean():.2%}")
    print(f"  2. Trend aligned:       {df['conf_2_trend_aligned'].mean():.2%}")
    print(f"  3. Low error:           {df['conf_3_low_error'].mean():.2%}")
    print(f"  4. Within band:         {df['conf_4_within_band'].mean():.2%}")
    print(f"  5. No event:            {df['conf_5_no_event'].mean():.2%}")
    
    # Éxito de las señales
    print("\n✅ VALIDACIÓN HISTÓRICA (señales vs resultado real):")
    for signal in ["BUY", "SELL"]:
        subset = df[df["trading_signal"] == signal]
        if len(subset) > 0:
            # ¿Ganó?
            if signal == "BUY":
                win = (subset["y_H3"] > 0).mean()
            else:  # SELL
                win = (subset["y_H3"] < 0).mean()
            
            print(f"  {signal:5s}: {len(subset):5d} señales, {win:.2%} correctas")


def plot_confidence_heatmap(df: pd.DataFrame):
    """Gráfica 5: Heatmap de confianza por ticker y tiempo."""
    # Agrupar por ticker y crear bins de tiempo
    df_sorted = df.sort_values("date").copy()
    df_sorted["time_bin"] = pd.qcut(df_sorted.index, q=15, duplicates="drop")
    
    df_pivot = df_sorted.pivot_table(values="confidence_score", 
                                      index="ticker",
                                      columns="time_bin",
                                      aggfunc="mean")
    
    fig, ax = plt.subplots(figsize=(14, 6))
    sns.heatmap(df_pivot, cmap="RdYlGn", center=2.5, vmin=0, vmax=5,
                cbar_kws={"label": "Confidence Score (0-5)"}, ax=ax)
    ax.set_title("Confidence Score por Ticker en el Tiempo")
    ax.set_xlabel("Período")
    ax.set_ylabel("Ticker")
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    plt.savefig(OUTPUTS_DIR / "14_confidence_heatmap.png", dpi=150, bbox_inches="tight")
    print(f"  ✓ 14_confidence_heatmap.png")
    plt.close()


def plot_signal_distribution(df: pd.DataFrame):
    """Gráfica 6: Distribución de señales de trading."""
    signal_counts = df["trading_signal"].value_counts()
    colors = {"BUY": "green", "SELL": "red", "NO_TRADE": "gray"}
    
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(signal_counts.index, signal_counts.values, 
                  color=[colors.get(x, "blue") for x in signal_counts.index],
                  alpha=0.7, edgecolor="black", linewidth=2)
    
    # Agregar valores en las barras
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}\n({height/len(df):.1%})',
                ha='center', va='bottom', fontsize=11, fontweight='bold')
    
    ax.set_ylabel("Cantidad")
    ax.set_title("Distribución de Señales de Trading (Reglas de Confianza)")
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    
    plt.savefig(OUTPUTS_DIR / "15_signal_distribution.png", dpi=150, bbox_inches="tight")
    print(f"  ✓ 15_signal_distribution.png")
    plt.close()


def export_trading_rules(df: pd.DataFrame):
    """Exportar reglas a CSV para usar en trading."""
    export_df = df[[
        "date", "ticker", "close", "price_pred", "price_real", "price_error", "price_error_pct",
        "prob_win", "y_hat", "y_H3",
        "confidence_score", "confidence_level", "signal_direction", "tradeable", "trading_signal"
    ]].copy()
    
    # Filtrar solo señales (BUY/SELL)
    signals_df = export_df[export_df["trading_signal"] != "NO_TRADE"].copy()
    
    # Guardar
    export_df.to_csv(OUTPUTS_DIR / "all_signals_with_confidence.csv", index=False)
    signals_df.to_csv(OUTPUTS_DIR / "trading_signals_only.csv", index=False)
    
    print(f"\n✓ Exportados:")
    print(f"  - all_signals_with_confidence.csv ({len(export_df)} filas)")
    print(f"  - trading_signals_only.csv ({len(signals_df)} BUY/SELL)")


def main():
    print("\n" + "=" * 100)
    print("MAPEO PRECIO REAL VS PREDICHO + REGLAS DE CONFIANZA")
    print("=" * 100)
    
    # Cargar datos
    if not CSV_PATH.exists():
        print(f"❌ No encontrado: {CSV_PATH}")
        return
    
    df = load_and_prepare_data(CSV_PATH)
    
    # Definir reglas
    df = define_confidence_rules(df)
    df = define_trading_signals(df)
    
    # Análisis
    print_confidence_analysis(df)
    
    # Gráficas
    print(f"\n📊 Generando gráficas...")
    
    # Global
    plot_price_timeseries(df)
    plot_price_error(df)
    plot_price_scatter(df)
    plot_price_error_distribution(df)
    plot_confidence_heatmap(df)
    plot_signal_distribution(df)
    
    # Por ticker top
    print(f"\n📊 Generando gráficas por ticker...")
    top_tickers = df["ticker"].value_counts().head(3).index
    for ticker in top_tickers:
        print(f"  {ticker}:")
        plot_price_timeseries(df, ticker=ticker)
        plot_price_error(df, ticker=ticker)
        plot_price_scatter(df, ticker=ticker)
        plot_price_error_distribution(df, ticker=ticker)
    
    # Exportar
    export_trading_rules(df)
    
    print(f"\n✅ Análisis completado. Outputs en: {OUTPUTS_DIR}")


if __name__ == "__main__":
    main()
