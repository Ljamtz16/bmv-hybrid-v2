#!/usr/bin/env python
"""
Generador de reporte ejecutivo (texto) de análisis
"""

import pandas as pd
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parent
CSV_PATH = REPO_ROOT / "reports" / "forecast" / "2025-11" / "forecast_signals.csv"
EQUITY_PATH = REPO_ROOT / "outputs" / "equity_curve.csv"
REPORT_PATH = REPO_ROOT / "outputs" / "ANALYSIS_REPORT.txt"

def load_data():
    """Cargar datos."""
    try:
        df_pred = pd.read_csv(CSV_PATH)
        df_pred["date"] = pd.to_datetime(df_pred["date"])
        df_pred = df_pred.dropna(subset=["y_H3", "y_hat"])
    except Exception as e:
        print(f"Error cargando forecast: {e}")
        df_pred = None
    
    try:
        df_equity = pd.read_csv(EQUITY_PATH)
    except Exception as e:
        print(f"Error cargando equity: {e}")
        df_equity = None
    
    return df_pred, df_equity

def generate_report(df_pred, df_equity):
    """Generar reporte."""
    lines = []
    
    # Header
    lines.append("=" * 100)
    lines.append("REPORTE EJECUTIVO: ANÁLISIS PREDICCIÓN VS REALIDAD")
    lines.append("USA Hybrid Clean V1")
    lines.append("=" * 100)
    lines.append("")
    lines.append(f"Fecha de generación: {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
    lines.append("")
    
    # Sección 1: Datos
    lines.append("┌" + "─" * 98 + "┐")
    lines.append("│ 1. DATOS DISPONIBLES".ljust(99) + "│")
    lines.append("└" + "─" * 98 + "┘")
    lines.append("")
    
    if df_pred is not None:
        lines.append(f"✓ Predicciones cargadas: {len(df_pred):,} observaciones")
        lines.append(f"  • Período: {df_pred['date'].min().date()} a {df_pred['date'].max().date()}")
        lines.append(f"  • Tickers: {df_pred['ticker'].nunique()} ({', '.join(sorted(df_pred['ticker'].unique())[:5])}...)")
        lines.append(f"  • Columnas: y_H3 (real), y_hat (predicción), prob_win (probabilidad)")
    else:
        lines.append("✗ No se pudo cargar forecast_signals.csv")
    
    lines.append("")
    
    if df_equity is not None:
        lines.append(f"✓ Trades ejecutados: {len(df_equity):,} operaciones")
        if "Fecha Cierre" in df_equity.columns:
            lines.append(f"  • Período: {df_equity['Fecha Cierre'].min()} a {df_equity['Fecha Cierre'].max()}")
        lines.append(f"  • Tickers: {df_equity['Ticker'].nunique()}")
    else:
        lines.append("✗ No se pudo cargar equity_curve.csv")
    
    lines.append("")
    
    # Sección 2: Regresión
    if df_pred is not None:
        lines.append("┌" + "─" * 98 + "┐")
        lines.append("│ 2. ANÁLISIS DE REGRESIÓN (Modelo de Retorno H3)".ljust(99) + "│")
        lines.append("└" + "─" * 98 + "┘")
        lines.append("")
        
        y_true = df_pred["y_H3"].values
        y_pred = df_pred["y_hat"].values
        
        import numpy as np
        mae = np.abs(y_true - y_pred).mean()
        rmse = np.sqrt(((y_true - y_pred) ** 2).mean())
        dir_acc = (np.sign(y_true) == np.sign(y_pred)).mean()
        
        lines.append(f"📊 GLOBAL:")
        lines.append(f"  MAE (Mean Absolute Error):           {mae:.8f}")
        lines.append(f"  RMSE (Root Mean Squared Error):      {rmse:.8f}")
        lines.append(f"  Directional Accuracy (sign correct): {dir_acc:.2%}")
        lines.append(f"  Muestras:                             {len(df_pred):,}")
        
        # Top 3 tickers
        lines.append("")
        lines.append("📈 TOP 3 TICKERS (por # de observaciones):")
        top_tickers = df_pred["ticker"].value_counts().head(3)
        for ticker, count in top_tickers.items():
            subset = df_pred[df_pred["ticker"] == ticker]
            y_t = subset["y_H3"].values
            y_p = subset["y_hat"].values
            m_mae = np.abs(y_t - y_p).mean()
            m_dir = (np.sign(y_t) == np.sign(y_p)).mean()
            lines.append(f"  {ticker:6s} | N={count:5d} | MAE={m_mae:.6f} | Dir Acc={m_dir:.2%}")
        
        lines.append("")
    
    # Sección 3: Probabilidad
    if df_pred is not None:
        lines.append("┌" + "─" * 98 + "┐")
        lines.append("│ 3. ANÁLISIS DE PROBABILIDAD (prob_win)".ljust(99) + "│")
        lines.append("└" + "─" * 98 + "┘")
        lines.append("")
        
        df_prob = df_pred.dropna(subset=["prob_win"]).copy()
        df_prob["y_true_binary"] = (df_prob["y_H3"] > 0).astype(int)
        
        brier = ((df_prob["prob_win"] - df_prob["y_true_binary"]) ** 2).mean()
        wr_real = df_prob["y_true_binary"].mean()
        wr_pred = df_prob["prob_win"].mean()
        bias = wr_pred - wr_real
        
        lines.append(f"📊 GLOBAL:")
        lines.append(f"  Brier Score:                  {brier:.6f} {'✓ Bien' if brier < 0.28 else '⚠️ Revisar'}")
        lines.append(f"  Win Rate Real (% H3>0):       {wr_real:.2%}")
        lines.append(f"  Prob_win Predicha (promedio): {wr_pred:.2%}")
        lines.append(f"  Sesgo:                        {bias:+.2%} {'(conservador)' if bias < 0 else '(optimista)'}")
        lines.append(f"  Muestras:                     {len(df_prob):,}")
        
        lines.append("")
        lines.append("📈 BEST / WORST CALIBRACIÓN:")
        calib_by_ticker = []
        for ticker in df_prob["ticker"].unique():
            subset = df_prob[df_prob["ticker"] == ticker]
            b = ((subset["prob_win"] - subset["y_true_binary"]) ** 2).mean()
            calib_by_ticker.append((ticker, b))
        
        calib_by_ticker.sort(key=lambda x: x[1])
        best = calib_by_ticker[0]
        worst = calib_by_ticker[-1]
        
        lines.append(f"  ✓ Mejor: {best[0]:6s} Brier={best[1]:.4f}")
        lines.append(f"  ✗ Peor:  {worst[0]:6s} Brier={worst[1]:.4f}")
        lines.append("")
    
    # Sección 4: Trading
    if df_equity is not None:
        lines.append("┌" + "─" * 98 + "┐")
        lines.append("│ 4. RESULTADOS DE TRADING (Equity Curve)".ljust(99) + "│")
        lines.append("└" + "─" * 98 + "┘")
        lines.append("")
        
        total_trades = len(df_equity)
        total_pnl = df_equity["PnL USD"].sum()
        wins = (df_equity["PnL USD"] > 0).sum()
        win_rate = wins / total_trades if total_trades > 0 else 0
        
        lines.append(f"💰 RESUMEN:")
        lines.append(f"  Total Trades:    {total_trades}")
        lines.append(f"  Win Rate:        {win_rate:.2%}")
        lines.append(f"  Total PnL:       ${total_pnl:,.2f}")
        lines.append(f"  Avg PnL/Trade:   ${total_pnl/total_trades:,.2f}")
        lines.append("")
    
    # Sección 5: Recomendaciones
    lines.append("┌" + "─" * 98 + "┐")
    lines.append("│ 5. RECOMENDACIONES".ljust(99) + "│")
    lines.append("└" + "─" * 98 + "┘")
    lines.append("")
    
    if df_pred is not None and dir_acc < 0.52:
        lines.append("🔴 CRÍTICO: Directional Accuracy < 52%")
        lines.append("   → El modelo NO predice bien si sube o baja")
        lines.append("   → Revisar features y considerar reentrenamiento")
        lines.append("")
    
    if df_pred is not None and abs(bias) > 0.10:
        lines.append("🟡 SESGO SISTEMÁTICO en prob_win")
        lines.append(f"   → Diferencia: {bias:+.2%}")
        lines.append("   → Usar calibración isotónica para ajustar")
        lines.append("")
    
    if df_equity is not None and total_trades < 20:
        lines.append("🟡 DATOS INSUFICIENTES para validación")
        lines.append(f"   → Solo {total_trades} trades (mínimo recomendado: 30-50)")
        lines.append("   → Esperar a acumular más operaciones")
        lines.append("")
    
    lines.append("✅ PRÓXIMOS PASOS:")
    lines.append("   1. Ejecutar análisis semanalmente para monitorear degradación")
    lines.append("   2. Si Directional Accuracy < 48%, revisar features")
    lines.append("   3. Recalibrar prob_win con CalibratedClassifierCV")
    lines.append("   4. Después de 30 trades: revisar R:R, drawdown máximo")
    lines.append("")
    
    # Footer
    lines.append("=" * 100)
    lines.append("Para gráficas interactivas, abre: analysis_dashboard.html")
    lines.append("=" * 100)
    
    return "\n".join(lines)

def main():
    print("Generando reporte ejecutivo...")
    
    df_pred, df_equity = load_data()
    report = generate_report(df_pred, df_equity)
    
    # Mostrar
    print(report)
    
    # Guardar con encoding UTF-8
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n✅ Reporte guardado: {REPORT_PATH}")

if __name__ == "__main__":
    main()
