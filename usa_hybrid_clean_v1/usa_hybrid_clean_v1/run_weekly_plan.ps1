"""
Script para ejecutar el flujo completo de esta semana:
1. Generar planes (STANDARD + PROBWIN_55)
2. Monitorizar con dashboard
"""
import subprocess
import time
import webbrowser
from datetime import datetime
from pathlib import Path

print("="*80)
print("PLAN DE ACCION SEMANAL - FLUJO COMPLETO")
print("="*80)
print(f"\nFecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# [1] Generar planes
print(f"\n[1] GENERANDO PLANES")
print("-" * 80)
print("Ejecutando: python generate_weekly_plans.py")

result = subprocess.run(
    ["./.venv/Scripts/python.exe", "generate_weekly_plans.py"],
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='replace'
)

print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

if result.returncode != 0:
    print("\nERROR: No se pudieron generar los planes")
    exit(1)

print("\n✓ Planes generados exitosamente")

# [2] Esperar un poco
time.sleep(2)

# [3] Iniciar dashboard
print(f"\n[2] INICIANDO DASHBOARD")
print("-" * 80)
print("Ejecutando: python dashboard_compare_plans.py")
print("\nDashboard disponible en: http://localhost:7777")
print("\nPresione Ctrl+C para detener el servidor\n")

try:
    # Intentar abrir en navegador después de 2 segundos
    time.sleep(2)
    webbrowser.open("http://localhost:7777")
except:
    print("\n[INFO] No se pudo abrir el navegador automáticamente")
    print("Visite: http://localhost:7777")

# Ejecutar dashboard
subprocess.run(
    ["./.venv/Scripts/python.exe", "dashboard_compare_plans.py"],
    text=True,
    encoding='utf-8'
)
