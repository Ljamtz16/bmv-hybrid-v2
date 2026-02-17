#!/usr/bin/env python3
"""
Trazar el flujo de generación de plan semanal
y verificar dónde se calcula etth_days_raw
"""
import pandas as pd
from pathlib import Path

print("="*80)
print("FLUJO COMPLETO: GENERACIÓN DE PLAN SEMANAL")
print("="*80)

# PASO 1
print("\n[PASO 1] CARGAR FORECAST")
print("-"*80)
forecast_file = Path("evidence/forecast_retrained_robust/forecast_prob_win_retrained.csv")
if forecast_file.exists():
    df_forecast = pd.read_csv(forecast_file)
    print(f"  ✓ Archivo: {forecast_file}")
    print(f"  ✓ Filas: {len(df_forecast):,}")
    print(f"  ✓ Columnas principales: {df_forecast.columns.tolist()[:10]}")
    print(f"\n  EJEMPLO SALIDA:")
    if len(df_forecast) > 0:
        row = df_forecast.iloc[0]
        print(f"    ticker: {row['ticker']}")
        print(f"    date: {row['date']}")
        print(f"    close: ${row.get('close', 'N/A')}")
        print(f"    prob_win_retrained: {row.get('prob_win_retrained', 'N/A')}")

# PASO 2
print("\n[PASO 2] OBTENER PRECIOS ACTUALES + CALCULAR TP/SL")
print("-"*80)
print("  Usando yfinance para cada ticker...")
print("  EJEMPLO SALIDA:")
print("    ticker: AAPL")
print("    precio_actual: $248.45 (from yfinance)")
print("    entry: $248.45")
print("    tp_price: $252.41 (entry * 1.016)")
print("    sl_price: $245.74 (entry * 0.990)")

# PASO 3
print("\n[PASO 3] GENERAR SEÑALES")
print("-"*80)
print("  Aplicar: side = BUY si prob_win > 0.5, SELL si < 0.5")
print("  Calcular: qty = (500 / entry)")
print("  EJEMPLO SALIDA:")
print("    {")
print('      "ticker": "AAPL",')
print('      "side": "BUY",')
print('      "entry": 248.45,')
print('      "tp_price": 252.41,')
print('      "sl_price": 245.74,')
print('      "qty": 2,')
print('      "prob_win": 0.78,')
print('      "strength": 0.78')
print("    }")

# PASO 4
print("\n[PASO 4] GUARDAR PLAN (generate_weekly_plans.py)")
print("-"*80)
plan_files = sorted(Path("evidence/weekly_plans").glob("plan_standard_*.csv"))
if plan_files:
    latest_plan = plan_files[-1]
    df_plan = pd.read_csv(latest_plan)
    print(f"  ✓ Archivo generado: {latest_plan.name}")
    print(f"  ✓ Filas: {len(df_plan)}")
    print(f"  ✓ Columnas: {df_plan.columns.tolist()}")
    print(f"\n  EJEMPLO SALIDA (CSV):")
    if len(df_plan) > 0:
        row = df_plan.iloc[0]
        print(f"    ticker,side,entry,tp_price,sl_price,qty,prob_win,...")
        print(f"    {row['ticker']},{row['side']},{row['entry']:.2f},{row['tp_price']:.2f}," + 
              f"{row['sl_price']:.2f},{row['qty']:.0f},{row['prob_win']:.2f},...")
        
        # AQUÍ ES LA PREGUNTA CLAVE
        if 'etth_days_raw' in df_plan.columns:
            print(f"\n  ✓✓✓ COLUMNA 'etth_days_raw' PRESENTE")
            print(f"      Valor: {row['etth_days_raw']:.2f} días")
            print(f"      EN MINUTOS: {int(row['etth_days_raw'] * 24 * 60)} min")
        else:
            print(f"\n  ✗✗✗ COLUMNA 'etth_days_raw' NO PRESENTE")
            print(f"      Esto es problema - debería estar aquí")

# PASO 5
print("\n[PASO 5] CARGAR EN DASHBOARD")
print("-"*80)
execute_plan = Path("val/trade_plan_EXECUTE.csv")
if execute_plan.exists():
    df_exec = pd.read_csv(execute_plan)
    print(f"  ✓ Archivo: val/trade_plan_EXECUTE.csv")
    print(f"  ✓ Filas: {len(df_exec)}")
    print(f"  ✓ Columnas: {df_exec.columns.tolist()[:10]}...")
    if 'etth_days_raw' in df_exec.columns:
        print(f"\n  ✓ etth_days_raw en EXECUTE -> Se puede leer en dashboard")
    else:
        print(f"\n  ✗ etth_days_raw en EXECUTE NO disponible")

print("\n" + "="*80)
print("RESUMEN: ¿En qué paso se estima el tiempo?")
print("="*80)
print("""
Si etth_days_raw está en el plan final:
  → Se calcula ANTES de generate_weekly_plans o EN ese script

Si etth_days_raw NO está en el plan final:
  → Nunca se calcula y el dashboard debe hacerlo dinámicamente
  
Estado actual: Verificar arriba ↑
""")
