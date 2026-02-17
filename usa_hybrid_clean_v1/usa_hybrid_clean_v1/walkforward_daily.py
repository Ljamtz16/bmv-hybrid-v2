"""
WALK-FORWARD BACKTEST DÍA POR DÍA (1 SEMANA)
Simula predicciones día por día y compara con datos reales

Flujo:
  Día 1 → Predecir precio para Día 2 → Comparar con real
  Día 2 → Predecir precio para Día 3 → Comparar con real
  ...
  Día 7 → Validar toda la semana

Gráfica el precio de la acción predicho vs real por ticker
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import sys
import os

# ============================================================================
# CARGAR DATOS
# ============================================================================

def load_data():
    """Carga datos con confidence scores."""
    filepath = "outputs/analysis/all_signals_with_confidence.csv"
    if not os.path.exists(filepath):
        print(f"❌ ERROR: {filepath} no existe")
        print("   Ejecuta primero: python analyze_price_confidence.py")
        sys.exit(1)
    
    df = pd.read_csv(filepath)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    
    print(f"✓ Datos cargados: {len(df)} observaciones")
    print(f"  Rango: {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"  Tickers: {df['ticker'].nunique()}")
    
    return df

# ============================================================================
# SELECCIONAR SEMANA
# ============================================================================

def select_week(df):
    """Selecciona últimos 7 días disponibles."""
    
    unique_dates = df["date"].dt.date.unique()
    unique_dates = sorted(unique_dates)
    
    # Usar últimos 7 días
    start_idx = len(unique_dates) - 10
    week_dates = unique_dates[start_idx:start_idx + 7]
    
    print(f"\n✓ Semana seleccionada (últimos 7 días):")
    for i, d in enumerate(week_dates, 1):
        print(f"  Día {i}: {d}")
    
    return week_dates

# ============================================================================
# SIMULAR DÍA POR DÍA
# ============================================================================

def simulate_day_by_day(df, week_dates, confidence_threshold=3):
    """Simula predicciones día por día y compara con realidad."""
    
    print("\n" + "="*70)
    print("SIMULACIÓN DÍA POR DÍA")
    print("="*70)
    
    daily_results = []
    
    for day_idx, current_date in enumerate(week_dates[:-1], 1):
        
        print(f"\n📅 DÍA {day_idx}: {current_date}")
        print("-" * 70)
        
        day_data = df[df["date"].dt.date == current_date].copy()
        
        if len(day_data) == 0:
            print(f"  ⚠️  Sin datos para {current_date}")
            continue
        
        day_data = day_data[day_data["confidence_score"] >= confidence_threshold]
        
        print(f"  Señales operables (conf ≥ {confidence_threshold}): {len(day_data)}")
        
        if len(day_data) == 0:
            print(f"  ⚠️  Sin señales operables")
            continue
        
        for _, row in day_data.iterrows():
            
            ticker = row["ticker"]
            price_today = row["close"]
            price_pred_tomorrow = row["price_pred"]
            
            next_date = week_dates[day_idx]
            next_day_data = df[(df["ticker"] == ticker) & 
                              (df["date"].dt.date == next_date)]
            
            if len(next_day_data) == 0:
                continue
            
            price_real_tomorrow = next_day_data.iloc[0]["close"]
            error_dollars = price_real_tomorrow - price_pred_tomorrow
            error_pct = (error_dollars / price_pred_tomorrow) * 100
            
            pred_direction = "UP" if row["y_hat"] > 0 else "DOWN"
            real_direction = "UP" if price_real_tomorrow > price_today else "DOWN"
            direction_correct = pred_direction == real_direction
            
            daily_results.append({
                "day": day_idx,
                "date_pred": current_date,
                "date_real": next_date,
                "ticker": ticker,
                "signal": row["trading_signal"],
                "confidence": row["confidence_score"],
                "price_today": price_today,
                "price_pred_tomorrow": price_pred_tomorrow,
                "price_real_tomorrow": price_real_tomorrow,
                "error_dollars": error_dollars,
                "error_pct": error_pct,
                "pred_direction": pred_direction,
                "real_direction": real_direction,
                "direction_correct": direction_correct,
                "prob_win": row["prob_win"],
                "y_hat": row["y_hat"]
            })
            
            status = "✓" if direction_correct else "✗"
            print(f"    {status} {ticker}: Pred ${price_pred_tomorrow:.2f} → Real ${price_real_tomorrow:.2f} | "
                  f"Error: {error_pct:+.2f}% | Conf: {row['confidence_score']}/5")
    
    results_df = pd.DataFrame(daily_results)
    
    if len(results_df) == 0:
        print("\n❌ Sin resultados generados")
        return None
    
    return results_df

# ============================================================================
# CALCULAR MÉTRICAS
# ============================================================================

def calculate_metrics(results_df):
    """Calcula métricas de precisión."""
    
    if results_df is None or len(results_df) == 0:
        return None
    
    metrics = {}
    metrics["total_predictions"] = len(results_df)
    metrics["directional_accuracy"] = (results_df["direction_correct"].sum() / len(results_df)) * 100
    metrics["mae_pct"] = results_df["error_pct"].abs().mean()
    metrics["rmse_pct"] = np.sqrt((results_df["error_pct"] ** 2).mean())
    metrics["mean_error_pct"] = results_df["error_pct"].mean()
    
    daily_metrics = results_df.groupby("day").agg({
        "direction_correct": lambda x: (x.sum() / len(x)) * 100,
        "error_pct": lambda x: x.abs().mean(),
        "ticker": "count"
    }).round(2)
    daily_metrics.columns = ["Dir_Acc_%", "MAE_%", "Predictions"]
    
    ticker_metrics = results_df.groupby("ticker").agg({
        "direction_correct": lambda x: (x.sum() / len(x)) * 100,
        "error_pct": lambda x: x.abs().mean(),
        "date_pred": "count"
    }).round(2)
    ticker_metrics.columns = ["Dir_Acc_%", "MAE_%", "Predictions"]
    ticker_metrics = ticker_metrics.sort_values("MAE_%")
    
    conf_metrics = results_df.groupby("confidence").agg({
        "direction_correct": lambda x: (x.sum() / len(x)) * 100,
        "error_pct": lambda x: x.abs().mean(),
        "ticker": "count"
    }).round(2)
    conf_metrics.columns = ["Dir_Acc_%", "MAE_%", "Predictions"]
    
    return metrics, daily_metrics, ticker_metrics, conf_metrics

# ============================================================================
# GRAFICAR PRECIO PREDICHO VS REAL
# ============================================================================

def plot_price_comparison(results_df, week_dates):
    """Gráfica de precio predicho vs real por ticker (6 tickers)."""
    
    if results_df is None or len(results_df) == 0:
        print("\n❌ Sin datos para graficar")
        return
    
    os.makedirs("outputs/multiday", exist_ok=True)
    
    top_tickers = results_df["ticker"].value_counts().head(6).index.tolist()
    
    fig, axes = plt.subplots(3, 2, figsize=(16, 12))
    axes = axes.flatten()
    
    for idx, ticker in enumerate(top_tickers):
        ax = axes[idx]
        
        ticker_data = results_df[results_df["ticker"] == ticker].sort_values("date_pred")
        
        if len(ticker_data) == 0:
            ax.text(0.5, 0.5, f"No data for {ticker}", ha="center", va="center")
            ax.set_title(f"{ticker} - No Data")
            continue
        
        days_range = range(len(ticker_data) * 2)
        
        pred_line = [ticker_data.iloc[i//2]["price_today"] if i % 2 == 0 
                     else ticker_data.iloc[i//2]["price_pred_tomorrow"]
                     for i in days_range]
        
        real_line = [ticker_data.iloc[i//2]["price_today"] if i % 2 == 0 
                     else ticker_data.iloc[i//2]["price_real_tomorrow"]
                     for i in days_range]
        
        ax.plot(days_range, pred_line, 'o-', color="#2E86AB", linewidth=2, 
                markersize=6, label="Predicho", alpha=0.8)
        ax.plot(days_range, real_line, 's-', color="#06A77D", linewidth=2, 
                markersize=6, label="Real", alpha=0.8)
        
        ax.fill_between(days_range, pred_line, real_line, alpha=0.2, color="red")
        
        mae = ticker_data["error_pct"].abs().mean()
        dir_acc = (ticker_data["direction_correct"].sum() / len(ticker_data)) * 100
        
        ax.set_title(f"{ticker}\nMAE: {mae:.2f}% | Dir Acc: {dir_acc:.1f}%", 
                    fontsize=11, fontweight="bold")
        ax.set_ylabel("Precio ($)")
        ax.set_xlabel("Timeline")
        ax.legend(loc="best", fontsize=9)
        ax.grid(True, alpha=0.3)
        
        xtick_labels = []
        for i in days_range:
            if i % 2 == 0:
                xtick_labels.append(f"D{ticker_data.iloc[i//2]['day']}")
            else:
                xtick_labels.append(f"D{ticker_data.iloc[i//2]['day']}+1")
        ax.set_xticks(days_range[::2])
        ax.set_xticklabels(xtick_labels[::2], rotation=45, ha='right')
    
    plt.suptitle(f"PRECIO PREDICHO vs REAL (DÍA POR DÍA)\n{week_dates[0]} → {week_dates[-1]}", 
                 fontsize=14, fontweight="bold", y=0.995)
    plt.tight_layout()
    
    filepath = "outputs/multiday/01_price_pred_vs_real_by_ticker.png"
    plt.savefig(filepath, dpi=150, bbox_inches="tight")
    print(f"✓ Guardado: {filepath}")
    plt.close()
    
    # Dashboard de métricas
    fig = plt.figure(figsize=(16, 10))
    
    ax1 = plt.subplot(2, 3, 1)
    daily_acc = results_df.groupby("day").apply(
        lambda x: (x["direction_correct"].sum() / len(x)) * 100
    )
    ax1.bar(daily_acc.index, daily_acc.values, color="#06A77D", edgecolor="black", alpha=0.7)
    ax1.axhline(y=50, color="red", linestyle="--", linewidth=2, label="Random (50%)")
    ax1.set_title("1. Directional Accuracy por Día", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Día")
    ax1.set_ylabel("Accuracy (%)")
    ax1.legend()
    ax1.grid(True, alpha=0.3, axis="y")
    
    ax2 = plt.subplot(2, 3, 2)
    daily_mae = results_df.groupby("day")["error_pct"].apply(lambda x: x.abs().mean())
    ax2.bar(daily_mae.index, daily_mae.values, color="#F18F01", edgecolor="black", alpha=0.7)
    ax2.set_title("2. MAE por Día", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Día")
    ax2.set_ylabel("MAE (%)")
    ax2.grid(True, alpha=0.3, axis="y")
    
    ax3 = plt.subplot(2, 3, 3)
    daily_count = results_df["day"].value_counts().sort_index()
    ax3.bar(daily_count.index, daily_count.values, color="#2E86AB", edgecolor="black", alpha=0.7)
    ax3.set_title("3. Predicciones por Día", fontsize=12, fontweight="bold")
    ax3.set_xlabel("Día")
    ax3.set_ylabel("Count")
    ax3.grid(True, alpha=0.3, axis="y")
    
    ax4 = plt.subplot(2, 3, 4)
    ax4.hist(results_df["error_pct"], bins=20, color="#A23B72", edgecolor="black", alpha=0.7)
    ax4.axvline(x=0, color="red", linestyle="--", linewidth=2, label="Sin error")
    ax4.axvline(x=results_df["error_pct"].mean(), color="green", linestyle="--", 
                linewidth=2, label=f"Media: {results_df['error_pct'].mean():.2f}%")
    ax4.set_title("4. Distribución de Errores", fontsize=12, fontweight="bold")
    ax4.set_xlabel("Error (%)")
    ax4.set_ylabel("Frequency")
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    ax5 = plt.subplot(2, 3, 5)
    ticker_acc = results_df.groupby("ticker").apply(
        lambda x: (x["direction_correct"].sum() / len(x)) * 100
    ).sort_values(ascending=True)
    colors_ticker = ["#D62828" if x < 50 else "#06A77D" for x in ticker_acc]
    ticker_acc.plot(kind="barh", ax=ax5, color=colors_ticker, edgecolor="black")
    ax5.axvline(x=50, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax5.set_title("5. Directional Accuracy por Ticker", fontsize=12, fontweight="bold")
    ax5.set_xlabel("Accuracy (%)")
    ax5.grid(True, alpha=0.3, axis="x")
    
    ax6 = plt.subplot(2, 3, 6)
    conf_acc = results_df.groupby("confidence").apply(
        lambda x: (x["direction_correct"].sum() / len(x)) * 100
    )
    ax6.bar(conf_acc.index, conf_acc.values, color="#06A77D", edgecolor="black", alpha=0.7)
    ax6.axhline(y=50, color="red", linestyle="--", linewidth=2, label="Random")
    ax6.set_title("6. Accuracy por Confidence Score", fontsize=12, fontweight="bold")
    ax6.set_xlabel("Confidence")
    ax6.set_ylabel("Accuracy (%)")
    ax6.legend()
    ax6.grid(True, alpha=0.3, axis="y")
    
    plt.suptitle(f"WALK-FORWARD VALIDATION (DÍA POR DÍA)\n{week_dates[0]} → {week_dates[-1]}", 
                 fontsize=14, fontweight="bold", y=0.995)
    plt.tight_layout()
    
    filepath = "outputs/multiday/02_daily_metrics_dashboard.png"
    plt.savefig(filepath, dpi=150, bbox_inches="tight")
    print(f"✓ Guardado: {filepath}")
    plt.close()

# ============================================================================
# IMPRIMIR RESUMEN
# ============================================================================

def print_summary(results_df, metrics, daily_metrics, ticker_metrics, conf_metrics, week_dates):
    """Imprime resumen."""
    
    if results_df is None:
        return
    
    print("\n" + "="*70)
    print("📊 RESUMEN WALK-FORWARD BACKTEST (DÍA POR DÍA)")
    print("="*70)
    
    print(f"\n📅 PERÍODO: {week_dates[0]} → {week_dates[-1]} (7 días)")
    print(f"   Predicciones evaluadas: {metrics['total_predictions']}")
    print(f"   Tickers operados: {results_df['ticker'].nunique()}")
    
    print(f"\n📈 PRECISIÓN GLOBAL:")
    print(f"   Directional Accuracy: {metrics['directional_accuracy']:.1f}%")
    print(f"   MAE: {metrics['mae_pct']:.2f}%")
    print(f"   RMSE: {metrics['rmse_pct']:.2f}%")
    print(f"   Mean Error: {metrics['mean_error_pct']:+.2f}%")
    
    print(f"\n📊 MÉTRICAS POR DÍA:")
    print(daily_metrics)
    
    print(f"\n🎯 TOP TICKERS (menor error):")
    print(ticker_metrics.head(5))
    
    print(f"\n🔍 VALIDACIÓN CONFIANZA:")
    print(conf_metrics)
    
    print("\n" + "="*70)

# ============================================================================
# EXPORTAR
# ============================================================================

def export_results(results_df):
    """Exporta resultados."""
    
    os.makedirs("outputs/multiday", exist_ok=True)
    
    filepath = "outputs/multiday/daily_predictions.csv"
    results_df.to_csv(filepath, index=False)
    print(f"✓ Guardado: {filepath}")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    
    df = load_data()
    
    if len(sys.argv) > 1:
        date_arg = sys.argv[1].replace("--date=", "").replace("--date", "").strip()
        try:
            start_date = pd.to_datetime(date_arg).date()
            print(f"✓ Fecha desde argumento: {start_date}")
            
            unique_dates = df["date"].dt.date.unique()
            unique_dates = sorted(unique_dates)
            start_idx = np.argmin([abs((d - start_date).days) for d in unique_dates])
            week_dates = unique_dates[start_idx:start_idx + 7]
        except:
            print(f"❌ Formato inválido: {date_arg}")
            week_dates = select_week(df)
    else:
        week_dates = select_week(df)
    
    results_df = simulate_day_by_day(df, week_dates, confidence_threshold=3)
    
    if results_df is None:
        print("\n❌ Sin resultados generados")
        sys.exit(1)
    
    metrics, daily_metrics, ticker_metrics, conf_metrics = calculate_metrics(results_df)
    
    print_summary(results_df, metrics, daily_metrics, ticker_metrics, conf_metrics, week_dates)
    
    plot_price_comparison(results_df, week_dates)
    
    export_results(results_df)
    
    print("\n✨ WALK-FORWARD BACKTEST COMPLETADO")
    print("   Gráficas en: outputs/multiday/")
