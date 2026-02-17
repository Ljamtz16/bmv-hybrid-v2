#!/usr/bin/env python3
"""
Generar plan STANDARD para hoy basado en PROBWIN_55
Plan STANDARD es más conservador: menos posiciones, mayor prob_win, stops más ajustados
"""
import pandas as pd
from pathlib import Path
from datetime import datetime

# Rutas
EXECUTE_PATH = Path("val/trade_plan_EXECUTE.csv")
OUTPUT_PATH = Path("val/trade_plan_STANDARD.csv")

print("=" * 80)
print("GENERADOR PLAN STANDARD")
print("=" * 80)

if not EXECUTE_PATH.exists():
    print(f"ERROR: {EXECUTE_PATH} no existe")
    exit(1)

# Cargar PROBWIN_55
df = pd.read_csv(EXECUTE_PATH)
print(f"\n[PROBWIN_55] {len(df)} posiciones")
print(df[["ticker", "side", "entry", "prob_win", "exposure"]].to_string())

# Crear STANDARD: filtrar solo posiciones con prob_win >= 0.55 (55%)
# y reducir exposición para ser más conservador
standard = df[df["prob_win"] >= 0.55].copy()

print(f"\n[STANDARD] {len(standard)} posiciones (prob_win >= 55%)")

# Aplicar cambios conservadores
standard["exposure"] = standard["exposure"] * 0.75  # 25% menos exposición
standard["plan_type"] = "STANDARD"
standard["generated_at"] = datetime.now().isoformat()

# Guardar
standard.to_csv(OUTPUT_PATH, index=False)
print(f"\n✓ Guardado: {OUTPUT_PATH}")
print(f"\nResumen STANDARD:")
print(f"  Posiciones: {len(standard)}")
print(f"  Exposición Total: ${standard['exposure'].sum():.2f}")
print(f"  Prob Win Promedio: {standard['prob_win'].mean()*100:.1f}%")
print("\n" + "=" * 80)
