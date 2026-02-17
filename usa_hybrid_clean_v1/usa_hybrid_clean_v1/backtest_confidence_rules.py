"""
BACKTEST CON REGLAS DE CONFIANZA
Simula operaciones desde fecha histórica usando confidence rules
Valida confiabilidad y precisión vs datos reales

Uso:
    python backtest_confidence_rules.py
    → Abre selector interactivo para fecha inicial
    
    python backtest_confidence_rules.py --date 2024-06-01
    → Inicia backtest desde 1 Junio 2024
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import sys
import os

# ============================================================================
# CONSTANTES GLOBALES (SINCRONIZADAS CON production_orchestrator.py)
# ============================================================================

CONF_THRESHOLD = 4
RISK_THRESHOLD = "MEDIUM"  # No operar si HIGH/CRITICAL
WHITELIST_TICKERS = ["CVX", "XOM", "WMT", "MSFT", "SPY"]

# Calendario de riesgos (simplificado)
FOMC_DATES = pd.to_datetime([
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-11-05", "2025-12-17"
])

# ============================================================================
# CARGAR Y PREPARAR DATOS
# ============================================================================

def load_confidence_data():
    """Carga datos con confidence scores."""
    filepath = "outputs/analysis/all_signals_with_confidence.csv"
    if not os.path.exists(filepath):
        print(f"❌ ERROR: {filepath} no existe")
        print("   Ejecuta primero: python analyze_price_confidence.py")
        sys.exit(1)
    
    df = pd.read_csv(filepath)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    print(f"✓ Datos cargados: {len(df)} observaciones")
    print(f"  Rango: {df['date'].min().date()} → {df['date'].max().date()}")
    
    return df


def calculate_macro_risk_level(date: pd.Timestamp, vix: float = None, gap_pct: float = None) -> str:
    """
    Calcular nivel de riesgo macro con overlays.
    
    Gates:
    1. FOMC ±2 días = HIGH
    2. VIX > 30 = HIGH (si disponible)
    3. Gap > 2% = HIGH (si disponible)
    
    Args:
        date: Fecha a evaluar
        vix: VIX opcional (si None, no se evalúa)
        gap_pct: Gap% opcional (si None, no se evalúa)
    
    Returns:
        "HIGH" si algún gate dispara, "MEDIUM" si no
    """
    # Gate 1: FOMC proximity
    fomc_proximity = ((FOMC_DATES - date).days).min()
    if abs(fomc_proximity) <= 2:
        return "HIGH"
    
    # Gate 2: VIX overlay (si está disponible)
    if vix is not None and vix > 30:
        return "HIGH"
    
    # Gate 3: Gap overlay (si está disponible)
    if gap_pct is not None and abs(gap_pct) > 2.0:
        return "HIGH"
    
    return "MEDIUM"

# ============================================================================
# SELECCIONAR FECHA INICIAL
# ============================================================================

def select_start_date(df):
    """Permite elegir fecha inicial para backtest."""
    min_date = df["date"].min()
    max_date = df["date"].max()
    
    print("\n" + "="*70)
    print("SELECCIONA FECHA INICIAL PARA BACKTEST")
    print("="*70)
    print(f"Rango disponible: {min_date.date()} → {max_date.date()}")
    print("\nOpciones:")
    print("  1) 6 meses atrás (2024-07-12)")
    print("  2) 3 meses atrás (2024-10-12)")
    print("  3) 2 meses atrás (2024-11-12)")
    print("  4) 1 mes atrás (2024-12-12)")
    print("  5) Manual (escribe fecha YYYY-MM-DD)")
    
    choice = input("\nOpción [1-5]: ").strip()
    
    if choice == "1":
        start_date = min_date + timedelta(days=190)  # ~6 meses
    elif choice == "2":
        start_date = min_date + timedelta(days=280)  # ~9 meses
    elif choice == "3":
        start_date = min_date + timedelta(days=315)  # ~10 meses
    elif choice == "4":
        start_date = min_date + timedelta(days=345)  # ~11 meses
    elif choice == "5":
        date_str = input("Escribe fecha (YYYY-MM-DD): ").strip()
        try:
            start_date = pd.to_datetime(date_str)
        except:
            print("❌ Formato inválido. Usando 6 meses atrás.")
            start_date = min_date + timedelta(days=190)
    else:
        start_date = min_date + timedelta(days=190)
    
    if start_date < min_date:
        start_date = min_date
    if start_date > max_date:
        start_date = max_date - timedelta(days=30)
    
    print(f"\n✓ Fecha inicial: {start_date.date()}")
    return start_date

# ============================================================================
# SIMULAR OPERACIONES
# ============================================================================

def run_backtest(df, start_date, 
                 confidence_threshold=3,
                 position_size=1,
                 take_profit_pct=1.5,
                 stop_loss_pct=1.0):
    """
    Simula operaciones usando confidence rules.
    
    Parámetros:
        confidence_threshold: mínima confianza para operar (0-5)
        position_size: cantidad de acciones por operación
        take_profit_pct: ganancia target (%)
        stop_loss_pct: pérdida máxima (%)
    """
    
    # Filtrar datos desde fecha inicial
    df_backtest = df[df["date"] >= start_date].copy().reset_index(drop=True)
    
    print(f"\n{'='*70}")
    print(f"BACKTEST: {start_date.date()} → {df_backtest['date'].max().date()}")
    print(f"{'='*70}")
    print(f"Días de trading: {df_backtest['date'].nunique()}")
    print(f"Observaciones totales: {len(df_backtest)}")
    print(f"Confianza mínima: {confidence_threshold}/5")
    print(f"Take Profit: {take_profit_pct}% | Stop Loss: {stop_loss_pct}%")
    
    # Preparar columnas de operaciones
    # DEFINICIÓN CONSISTENTE: Conf >= threshold AND Risk <= MEDIUM AND Ticker en Whitelist
    df_backtest["macro_risk"] = df_backtest["date"].apply(calculate_macro_risk_level)
    
    risk_ok = df_backtest["macro_risk"].isin(["LOW", "MEDIUM"])
    conf_ok = df_backtest["confidence_score"] >= confidence_threshold
    ticker_ok = df_backtest["ticker"].isin(WHITELIST_TICKERS)
    trading_ok = df_backtest["trading_signal"].isin(["BUY", "SELL"])
    
    df_backtest["operable"] = risk_ok & conf_ok & ticker_ok & trading_ok
    
    # Estadísticas operables
    operable_count = df_backtest["operable"].sum()
    operable_pct = (operable_count / len(df_backtest)) * 100
    
    print(f"\n📊 Señales operables (conf ≥ {confidence_threshold}):")
    print(f"  Total: {operable_count} ({operable_pct:.1f}%)")
    print(f"  BUY: {df_backtest[(df_backtest['operable']) & (df_backtest['trading_signal']=='BUY')].shape[0]}")
    print(f"  SELL: {df_backtest[(df_backtest['operable']) & (df_backtest['trading_signal']=='SELL')].shape[0]}")
    
    # Simular operaciones
    trades = []
    position_entry_price = None
    position_ticker = None
    position_signal = None
    position_confidence = None
    position_entry_date = None
    
    for idx, row in df_backtest.iterrows():
        # Si no hay posición abierta
        if position_entry_price is None:
            if row["operable"]:
                # Abrir nueva posición
                position_entry_price = row["close"]
                position_ticker = row["ticker"]
                position_signal = row["trading_signal"]
                position_confidence = row["confidence_score"]
                position_entry_date = row["date"]
        
        # Si hay posición abierta
        else:
            current_price = row["close"]
            pnl_pct = ((current_price - position_entry_price) / position_entry_price) * 100
            
            # Evaluar salida
            close_reason = None
            
            # Take profit
            if position_signal == "BUY" and pnl_pct >= take_profit_pct:
                close_reason = f"TP (+{take_profit_pct}%)"
            elif position_signal == "SELL" and pnl_pct <= -take_profit_pct:
                close_reason = f"TP (-{take_profit_pct}%)"
            
            # Stop loss
            elif position_signal == "BUY" and pnl_pct <= -stop_loss_pct:
                close_reason = f"SL (-{stop_loss_pct}%)"
            elif position_signal == "SELL" and pnl_pct >= stop_loss_pct:
                close_reason = f"SL (+{stop_loss_pct}%)"
            
            # Cierre de semana o cambio de señal confiable
            elif row["date"].weekday() == 4 and row["date"].hour >= 15:  # Viernes cerca de cierre
                close_reason = "Cierre semana"
            elif row["operable"] and row["trading_signal"] != position_signal:
                close_reason = "Señal opuesta"
            
            # Registrar trade si hay razón de cierre
            if close_reason:
                trades.append({
                    "ticker": position_ticker,
                    "signal": position_signal,
                    "entry_date": position_entry_date,
                    "entry_price": position_entry_price,
                    "entry_confidence": position_confidence,
                    "exit_date": row["date"],
                    "exit_price": current_price,
                    "pnl_pct": pnl_pct,
                    "close_reason": close_reason,
                    "days_held": (row["date"] - position_entry_date).days
                })
                
                # Reset posición
                position_entry_price = None
                position_ticker = None
                position_signal = None
                position_confidence = None
                position_entry_date = None
    
    # Convertir trades a DataFrame
    trades_df = pd.DataFrame(trades)
    
    if len(trades_df) == 0:
        print("\n❌ Sin trades generados. Baja confianza o pocos días.")
        return None, df_backtest
    
    return trades_df, df_backtest

# ============================================================================
# CALCULAR MÉTRICAS DE BACKTEST
# ============================================================================

def calculate_backtest_metrics(trades_df, initial_capital=10000):
    """Calcula métricas de desempeño del backtest."""
    
    if trades_df is None or len(trades_df) == 0:
        return None
    
    metrics = {}
    
    # Operaciones básicas
    metrics["total_trades"] = len(trades_df)
    metrics["buys"] = len(trades_df[trades_df["signal"] == "BUY"])
    metrics["sells"] = len(trades_df[trades_df["signal"] == "SELL"])
    
    # Ganancias y pérdidas
    winning_trades = trades_df[trades_df["pnl_pct"] > 0]
    losing_trades = trades_df[trades_df["pnl_pct"] <= 0]
    
    metrics["winning_trades"] = len(winning_trades)
    metrics["losing_trades"] = len(losing_trades)
    metrics["win_rate"] = (len(winning_trades) / len(trades_df)) * 100 if len(trades_df) > 0 else 0
    
    # Retornos
    metrics["total_pnl_pct"] = trades_df["pnl_pct"].sum()
    metrics["avg_pnl_pct"] = trades_df["pnl_pct"].mean()
    metrics["max_win"] = trades_df["pnl_pct"].max()
    metrics["max_loss"] = trades_df["pnl_pct"].min()
    
    # Ratio de ganancias
    if len(winning_trades) > 0 and len(losing_trades) > 0:
        avg_win = winning_trades["pnl_pct"].mean()
        avg_loss = abs(losing_trades["pnl_pct"].mean())
        metrics["profit_factor"] = avg_win / avg_loss if avg_loss > 0 else 0
    else:
        metrics["profit_factor"] = 0
    
    # Duración de trades
    metrics["avg_days_held"] = trades_df["days_held"].mean()
    
    # Equity curve
    cumulative_pnl = trades_df["pnl_pct"].cumsum()
    metrics["final_equity"] = initial_capital * (1 + metrics["total_pnl_pct"] / 100)
    metrics["max_drawdown"] = cumulative_pnl.min()
    
    return metrics, trades_df

# ============================================================================
# VALIDAR CONFIABILIDAD
# ============================================================================

def validate_confidence_accuracy(trades_df):
    """Valida si confidence score predice win rate."""
    
    if trades_df is None or len(trades_df) == 0:
        return None
    
    # Agrupar por confidence
    trades_df["conf_level"] = pd.cut(
        trades_df["entry_confidence"],
        bins=[0, 1, 2, 3, 4, 5],
        labels=["Baja", "Media", "Alta", "Muy Alta", "Máxima"]
    )
    
    validation = trades_df.groupby("conf_level", observed=True).agg({
        "pnl_pct": ["count", "mean", lambda x: (x > 0).sum()],
    }).round(2)
    
    validation.columns = ["Count", "Avg PnL%", "Winning"]
    validation["Win Rate%"] = (validation["Winning"] / validation["Count"] * 100).round(1)
    
    return validation

# ============================================================================
# GENERAR GRÁFICAS
# ============================================================================

def plot_backtest_results(trades_df, metrics, start_date):
    """Genera gráficas del backtest."""
    
    if trades_df is None or len(trades_df) == 0:
        print("\n❌ Sin trades para visualizar")
        return
    
    os.makedirs("outputs/backtest", exist_ok=True)
    
    fig = plt.figure(figsize=(16, 12))
    
    # 1. Equity Curve
    ax1 = plt.subplot(3, 3, 1)
    cumulative_pnl = trades_df["pnl_pct"].cumsum()
    ax1.plot(cumulative_pnl.values, linewidth=2, color="#2E86AB", label="Equity")
    ax1.fill_between(range(len(cumulative_pnl)), cumulative_pnl, alpha=0.3, color="#2E86AB")
    ax1.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
    ax1.set_title("1. Equity Curve", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Trade #")
    ax1.set_ylabel("Cumulative PnL %")
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    
    # 2. Win Rate Distribution
    ax2 = plt.subplot(3, 3, 2)
    win_loss = [metrics["winning_trades"], metrics["losing_trades"]]
    colors = ["#06A77D", "#D62828"]
    ax2.pie(win_loss, labels=[f"Win\n{metrics['winning_trades']}", f"Loss\n{metrics['losing_trades']}"],
            autopct="%1.1f%%", colors=colors, startangle=90)
    ax2.set_title(f"2. Win Rate: {metrics['win_rate']:.1f}%", fontsize=12, fontweight="bold")
    
    # 3. PnL Distribution
    ax3 = plt.subplot(3, 3, 3)
    ax3.hist(trades_df["pnl_pct"], bins=20, color="#A23B72", edgecolor="black", alpha=0.7)
    ax3.axvline(x=0, color="red", linestyle="--", linewidth=2, label="Breakeven")
    ax3.axvline(x=metrics["avg_pnl_pct"], color="green", linestyle="--", linewidth=2, label="Average")
    ax3.set_title(f"3. PnL Distribution\n(Avg: {metrics['avg_pnl_pct']:.2f}%)", 
                  fontsize=12, fontweight="bold")
    ax3.set_xlabel("PnL %")
    ax3.set_ylabel("Frequency")
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # 4. PnL por Ticker
    ax4 = plt.subplot(3, 3, 4)
    ticker_pnl = trades_df.groupby("ticker")["pnl_pct"].mean().sort_values()
    colors_ticker = ["#D62828" if x < 0 else "#06A77D" for x in ticker_pnl]
    ticker_pnl.plot(kind="barh", ax=ax4, color=colors_ticker, edgecolor="black")
    ax4.axvline(x=0, color="black", linestyle="-", linewidth=0.8)
    ax4.set_title("4. Avg PnL por Ticker", fontsize=12, fontweight="bold")
    ax4.set_xlabel("Avg PnL %")
    ax4.grid(True, alpha=0.3, axis="x")
    
    # 5. Trades por Ticker
    ax5 = plt.subplot(3, 3, 5)
    trades_by_ticker = trades_df["ticker"].value_counts().sort_values(ascending=True)
    trades_by_ticker.plot(kind="barh", ax=ax5, color="#F18F01", edgecolor="black")
    ax5.set_title("5. Trades por Ticker", fontsize=12, fontweight="bold")
    ax5.set_xlabel("Count")
    ax5.grid(True, alpha=0.3, axis="x")
    
    # 6. Confianza vs Win Rate
    ax6 = plt.subplot(3, 3, 6)
    conf_win = trades_df.groupby(
        pd.cut(trades_df["entry_confidence"], bins=5)
    ).apply(lambda x: (x["pnl_pct"] > 0).sum() / len(x) * 100 if len(x) > 0 else 0)
    conf_win.plot(kind="bar", ax=ax6, color="#06A77D", edgecolor="black")
    ax6.set_title("6. Win Rate por Confidence Score", fontsize=12, fontweight="bold")
    ax6.set_ylabel("Win Rate %")
    ax6.set_xlabel("Confidence Band")
    ax6.grid(True, alpha=0.3, axis="y")
    plt.setp(ax6.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # 7. Duración de Trades
    ax7 = plt.subplot(3, 3, 7)
    ax7.hist(trades_df["days_held"], bins=15, color="#2E86AB", edgecolor="black", alpha=0.7)
    ax7.axvline(x=metrics["avg_days_held"], color="red", linestyle="--", linewidth=2, 
                label=f"Avg: {metrics['avg_days_held']:.1f}d")
    ax7.set_title("7. Duración de Trades", fontsize=12, fontweight="bold")
    ax7.set_xlabel("Days")
    ax7.set_ylabel("Frequency")
    ax7.legend()
    ax7.grid(True, alpha=0.3)
    
    # 8. PnL Scatter (Entry Price vs PnL)
    ax8 = plt.subplot(3, 3, 8)
    colors_scatter = ["#06A77D" if x > 0 else "#D62828" for x in trades_df["pnl_pct"]]
    ax8.scatter(trades_df["entry_price"], trades_df["pnl_pct"], 
               c=colors_scatter, s=100, alpha=0.6, edgecolor="black")
    ax8.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
    ax8.set_title("8. Entry Price vs PnL", fontsize=12, fontweight="bold")
    ax8.set_xlabel("Entry Price")
    ax8.set_ylabel("PnL %")
    ax8.grid(True, alpha=0.3)
    
    # 9. Señales BUY vs SELL
    ax9 = plt.subplot(3, 3, 9)
    signal_stats = trades_df.groupby("signal")["pnl_pct"].agg(["count", "mean"])
    signals = ["BUY", "SELL"]
    counts = [signal_stats.loc["BUY", "count"] if "BUY" in signal_stats.index else 0,
              signal_stats.loc["SELL", "count"] if "SELL" in signal_stats.index else 0]
    avg_pnl = [signal_stats.loc["BUY", "mean"] if "BUY" in signal_stats.index else 0,
               signal_stats.loc["SELL", "mean"] if "SELL" in signal_stats.index else 0]
    
    x_pos = np.arange(len(signals))
    bars = ax9.bar(x_pos, avg_pnl, color=["#06A77D", "#D62828"], edgecolor="black", alpha=0.7)
    ax9.axhline(y=0, color="black", linestyle="-", linewidth=0.8)
    ax9.set_xticks(x_pos)
    ax9.set_xticklabels([f"{sig}\n({int(counts[i])} trades)" for i, sig in enumerate(signals)])
    ax9.set_title("9. Avg PnL: BUY vs SELL", fontsize=12, fontweight="bold")
    ax9.set_ylabel("Avg PnL %")
    ax9.grid(True, alpha=0.3, axis="y")
    
    plt.suptitle(f"BACKTEST CONFIDENCE RULES\n{start_date.date()} → {trades_df['exit_date'].max().date()}",
                 fontsize=16, fontweight="bold", y=0.995)
    plt.tight_layout()
    
    filepath = "outputs/backtest/01_backtest_overview.png"
    plt.savefig(filepath, dpi=150, bbox_inches="tight")
    print(f"✓ Guardado: {filepath}")
    plt.close()

# ============================================================================
# IMPRIMIR RESUMEN
# ============================================================================

def print_backtest_summary(metrics, trades_df, start_date, validation_df):
    """Imprime resumen ejecutivo del backtest."""
    
    if metrics is None:
        return
    
    print("\n" + "="*70)
    print("📊 RESUMEN DEL BACKTEST")
    print("="*70)
    
    print(f"\n📅 Período: {start_date.date()} → {trades_df['exit_date'].max().date()}")
    print(f"   Total días: {(trades_df['exit_date'].max() - start_date).days}")
    
    print(f"\n💹 ESTADÍSTICAS OPERACIONALES:")
    print(f"  Total trades: {metrics['total_trades']}")
    print(f"  BUY trades: {metrics['buys']}")
    print(f"  SELL trades: {metrics['sells']}")
    
    print(f"\n✅ DESEMPEÑO:")
    print(f"  Win Rate: {metrics['win_rate']:.1f}%")
    print(f"  Winning trades: {metrics['winning_trades']}")
    print(f"  Losing trades: {metrics['losing_trades']}")
    print(f"  Profit Factor: {metrics['profit_factor']:.2f}x")
    
    print(f"\n💰 RETORNOS:")
    print(f"  Total PnL: {metrics['total_pnl_pct']:.2f}%")
    print(f"  Avg PnL/Trade: {metrics['avg_pnl_pct']:.2f}%")
    print(f"  Max Win: {metrics['max_win']:.2f}%")
    print(f"  Max Loss: {metrics['max_loss']:.2f}%")
    print(f"  Max Drawdown: {metrics['max_drawdown']:.2f}%")
    
    print(f"\n⏱️  DURACIÓN:")
    print(f"  Avg días/trade: {metrics['avg_days_held']:.1f}")
    
    print(f"\n🎯 VALIDACIÓN (Confianza vs Win Rate):")
    print(validation_df)
    
    print(f"\n{'='*70}")

# ============================================================================
# EXPORTAR RESULTADOS
# ============================================================================

def export_backtest_results(trades_df, metrics, start_date):
    """Exporta resultados del backtest a CSV."""
    
    os.makedirs("outputs/backtest", exist_ok=True)
    
    # Exportar trades
    filepath = "outputs/backtest/backtest_trades.csv"
    trades_df.to_csv(filepath, index=False)
    print(f"✓ Guardado: {filepath}")
    
    # Exportar métricas
    metrics_df = pd.DataFrame([metrics])
    filepath = "outputs/backtest/backtest_metrics.csv"
    metrics_df.to_csv(filepath, index=False)
    print(f"✓ Guardado: {filepath}")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    
    # Cargar datos
    df = load_confidence_data()
    
    # Seleccionar fecha inicial (si se pasa argumento, usar ese)
    if len(sys.argv) > 1:
        date_arg = sys.argv[1].replace("--date=", "").replace("--date", "").strip()
        try:
            start_date = pd.to_datetime(date_arg)
            print(f"✓ Fecha desde argumento: {start_date.date()}")
        except:
            print(f"❌ Formato inválido: {date_arg}")
            start_date = select_start_date(df)
    else:
        # Usar 3 meses atrás por defecto (sin selector interactivo)
        start_date = df["date"].max() - timedelta(days=90)
        print(f"✓ Usando 3 meses atrás por defecto: {start_date.date()}")
    
    # Ejecutar backtest
    trades_df, df_backtest = run_backtest(
        df, 
        start_date,
        confidence_threshold=3,
        position_size=1,
        take_profit_pct=1.5,
        stop_loss_pct=1.0
    )
    
    if trades_df is None:
        print("\n❌ Backtest no generó resultados")
        sys.exit(1)
    
    # Calcular métricas
    metrics, trades_df = calculate_backtest_metrics(trades_df)
    
    # Validar confiabilidad
    validation_df = validate_confidence_accuracy(trades_df)
    
    # Imprimir resumen
    print_backtest_summary(metrics, trades_df, start_date, validation_df)
    
    # Generar gráficas
    plot_backtest_results(trades_df, metrics, start_date)
    
    # Exportar datos
    export_backtest_results(trades_df, metrics, start_date)
    
    print("\n✨ BACKTEST COMPLETADO")
    print(f"   Resultados en: outputs/backtest/")
