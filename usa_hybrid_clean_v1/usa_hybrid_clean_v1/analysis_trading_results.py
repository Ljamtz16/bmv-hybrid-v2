#!/usr/bin/env python
"""
Análisis de Trade Plan vs Resultados Reales
=============================================
Compara predicción de trades (trade_plan.csv) vs equity_curve (resultados reales).

Métricas:
  - Win rate predicho vs real
  - PnL predicho vs real
  - Hit rate en TP/SL
  - Relación R:R
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from datetime import datetime
import warnings

warnings.filterwarnings("ignore")

# Configuración
REPO_ROOT = Path(__file__).resolve().parent
EQUITY_PATH = REPO_ROOT / "outputs" / "equity_curve.csv"
OUTPUTS_DIR = REPO_ROOT / "outputs" / "analysis"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (14, 7)
plt.rcParams["font.size"] = 10


def load_equity_curve(csv_path: Path) -> pd.DataFrame:
    """Cargar equity_curve con manejo robusto de encoding."""
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except:
        try:
            df = pd.read_csv(csv_path, encoding="latin-1")
        except:
            df = pd.read_csv(csv_path, encoding="cp1252")
    
    df["Fecha Cierre"] = pd.to_datetime(df["Fecha Cierre"], errors="coerce")
    df = df.dropna(subset=["Fecha Cierre"])
    df = df.sort_values("Fecha Cierre")
    
    print(f"✓ Equity curve cargada: {len(df)} trades, {df['Ticker'].nunique()} tickers únicos")
    return df


def plot_pnl_timeseries(df: pd.DataFrame):
    """Gráfica: PnL acumulado en el tiempo."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    
    # PnL individual por trade
    colors = ["green" if x > 0 else "red" for x in df["PnL USD"]]
    ax1.bar(range(len(df)), df["PnL USD"], color=colors, alpha=0.7)
    ax1.axhline(0, color="black", linestyle="-", linewidth=0.5)
    ax1.set_xlabel("Trade #")
    ax1.set_ylabel("PnL USD")
    ax1.set_title("PnL por Trade (individual)")
    ax1.grid(True, alpha=0.3, axis="y")
    
    # PnL acumulado
    df_cum = df.copy()
    df_cum["PnL_Acum"] = df["PnL USD"].cumsum()
    ax2.plot(range(len(df_cum)), df_cum["PnL_Acum"], marker="o", linewidth=2, color="steelblue")
    ax2.axhline(0, color="black", linestyle="--", linewidth=1)
    ax2.fill_between(range(len(df_cum)), 0, df_cum["PnL_Acum"], alpha=0.2, color="steelblue")
    ax2.set_xlabel("Trade #")
    ax2.set_ylabel("PnL Acumulado USD")
    ax2.set_title("PnL Acumulado (equity curve)")
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(OUTPUTS_DIR / "06_pnl_timeseries.png", dpi=150, bbox_inches="tight")
    print(f"  ✓ 06_pnl_timeseries.png")
    plt.close()


def plot_pnl_distribution(df: pd.DataFrame):
    """Histograma de distribución de PnL."""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    wins = df[df["PnL USD"] > 0]["PnL USD"]
    losses = df[df["PnL USD"] <= 0]["PnL USD"]
    
    ax.hist(wins, bins=20, alpha=0.7, color="green", label=f"Wins (n={len(wins)})")
    ax.hist(losses, bins=20, alpha=0.7, color="red", label=f"Losses (n={len(losses)})")
    ax.axvline(0, color="black", linestyle="--", linewidth=2)
    ax.set_xlabel("PnL USD")
    ax.set_ylabel("Frecuencia")
    ax.set_title("Distribución de PnL por Trade")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    
    plt.tight_layout()
    plt.savefig(OUTPUTS_DIR / "07_pnl_distribution.png", dpi=150, bbox_inches="tight")
    print(f"  ✓ 07_pnl_distribution.png")
    plt.close()


def plot_pnl_by_ticker(df: pd.DataFrame):
    """PnL acumulado por ticker (box plot + summary)."""
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Box plot
    tickers = sorted(df["Ticker"].unique())
    data_by_ticker = [df[df["Ticker"] == t]["PnL USD"].values for t in tickers]
    
    bp = ax.boxplot(data_by_ticker, labels=tickers, patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_facecolor("lightblue")
    
    ax.axhline(0, color="red", linestyle="--", linewidth=2)
    ax.set_ylabel("PnL USD")
    ax.set_title("Distribución de PnL por Ticker")
    ax.grid(True, alpha=0.3, axis="y")
    
    plt.tight_layout()
    plt.savefig(OUTPUTS_DIR / "08_pnl_by_ticker.png", dpi=150, bbox_inches="tight")
    print(f"  ✓ 08_pnl_by_ticker.png")
    plt.close()


def plot_win_rate_by_ticker(df: pd.DataFrame):
    """Win rate y PnL promedio por ticker."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    tickers = sorted(df["Ticker"].unique())
    win_rates = []
    mean_pnls = []
    trades_per_ticker = []
    
    for t in tickers:
        subset = df[df["Ticker"] == t]
        wr = (subset["PnL USD"] > 0).mean()
        mp = subset["PnL USD"].mean()
        win_rates.append(wr)
        mean_pnls.append(mp)
        trades_per_ticker.append(len(subset))
    
    # Win rate
    colors1 = ["green" if x > 0.5 else "red" for x in win_rates]
    ax1.bar(tickers, win_rates, color=colors1, alpha=0.7)
    ax1.axhline(0.5, color="black", linestyle="--", linewidth=1)
    ax1.set_ylabel("Win Rate")
    ax1.set_title("Win Rate por Ticker")
    ax1.set_ylim([0, 1])
    ax1.grid(True, alpha=0.3, axis="y")
    
    # PnL promedio
    colors2 = ["green" if x > 0 else "red" for x in mean_pnls]
    ax2.bar(tickers, mean_pnls, color=colors2, alpha=0.7)
    ax2.axhline(0, color="black", linestyle="-", linewidth=0.5)
    ax2.set_ylabel("PnL USD promedio")
    ax2.set_title("PnL Promedio por Ticker")
    ax2.grid(True, alpha=0.3, axis="y")
    
    plt.tight_layout()
    plt.savefig(OUTPUTS_DIR / "09_win_rate_by_ticker.png", dpi=150, bbox_inches="tight")
    print(f"  ✓ 09_win_rate_by_ticker.png")
    plt.close()
    
    # Print summary
    print("\n📊 RESUMEN POR TICKER:")
    print("-" * 80)
    for i, t in enumerate(tickers):
        print(f"{t:6s} | Win Rate: {win_rates[i]:6.2%} | Avg PnL: ${mean_pnls[i]:8.2f} | Trades: {trades_per_ticker[i]:3d}")


def print_trading_metrics(df: pd.DataFrame):
    """Imprime métricas de trading."""
    print("\n" + "=" * 100)
    print("MÉTRICAS DE TRADING")
    print("=" * 100)
    
    total_trades = len(df)
    total_pnl = df["PnL USD"].sum()
    total_pnl_pct = df["PnL %"].sum()
    
    wins = (df["PnL USD"] > 0).sum()
    losses = (df["PnL USD"] <= 0).sum()
    win_rate = wins / total_trades if total_trades > 0 else 0
    
    avg_win = df[df["PnL USD"] > 0]["PnL USD"].mean() if wins > 0 else 0
    avg_loss = df[df["PnL USD"] <= 0]["PnL USD"].mean() if losses > 0 else 0
    
    # Profit factor
    profit_factor = (-avg_win * wins) / (avg_loss * losses) if losses > 0 and avg_loss != 0 else 0
    
    print(f"\n📊 GLOBAL:")
    print(f"  Total trades:        {total_trades}")
    print(f"  Wins:                {wins} ({win_rate:.2%})")
    print(f"  Losses:              {losses} ({1 - win_rate:.2%})")
    print(f"  Total PnL:           ${total_pnl:,.2f}")
    print(f"  Total PnL %:         {total_pnl_pct:.2f}%")
    print(f"  Avg Win:             ${avg_win:,.2f}")
    print(f"  Avg Loss:            ${avg_loss:,.2f}")
    print(f"  Profit Factor:       {profit_factor:.2f}")
    
    if total_trades > 0:
        print(f"  Avg PnL per trade:   ${total_pnl / total_trades:,.2f}")
    
    # Por Exit Reason (si existe)
    if "Exit Reason" in df.columns:
        print(f"\n📈 POR EXIT REASON:")
        print("-" * 80)
        for reason in df["Exit Reason"].unique():
            if pd.isna(reason):
                reason_str = "NaN"
            else:
                reason_str = str(reason)
            subset = df[df["Exit Reason"] == reason]
            print(f"  {reason_str:20s} | Trades: {len(subset):3d} | Total PnL: ${subset['PnL USD'].sum():8.2f} | Avg: ${subset['PnL USD'].mean():8.2f}")


def main():
    print("\n" + "=" * 100)
    print("ANÁLISIS TRADES EJECUTADOS - USA HYBRID CLEAN V1")
    print("=" * 100)
    
    if not EQUITY_PATH.exists():
        print(f"❌ No encontrado: {EQUITY_PATH}")
        return
    
    df = load_equity_curve(EQUITY_PATH)
    
    if len(df) == 0:
        print("❌ No hay datos de trades.")
        return
    
    # Métricas
    print_trading_metrics(df)
    
    # Gráficas
    print(f"\n📊 Generando gráficas de trading...")
    plot_pnl_timeseries(df)
    plot_pnl_distribution(df)
    plot_pnl_by_ticker(df)
    plot_win_rate_by_ticker(df)
    
    print(f"\n✅ Análisis completo. Outputs en: {OUTPUTS_DIR}")


if __name__ == "__main__":
    main()
