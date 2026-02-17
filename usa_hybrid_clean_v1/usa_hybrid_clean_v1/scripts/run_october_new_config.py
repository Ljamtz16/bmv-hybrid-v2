"""
Run complete October pipeline with new configuration (prob_win_min=0.05)
"""
import subprocess
from datetime import datetime

dates = ["2025-10-16", "2025-10-17", "2025-10-22", "2025-10-31"]

print("=" * 80)
print("EJECUTANDO PIPELINE OCTUBRE CON NUEVA CONFIGURACIÓN")
print("=" * 80)
print(f"Fechas: {dates}")
print(f"Configuración: prob_win_min=0.05 (5%)")
print()

for date in dates:
    print(f"\n{'=' * 80}")
    print(f"PROCESANDO: {date}")
    print(f"{'=' * 80}")
    
    # Step 1: Inference
    print(f"\n[1/3] Inferencia...")
    cmd1 = f"python scripts/11_infer_and_gate_intraday.py --date {date} --prob-min 0.05"
    result = subprocess.run(cmd1, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR en inferencia: {result.stderr}")
        continue
    
    # Extract signal count
    for line in result.stdout.split('\n'):
        if 'Forecast guardado' in line or 'Total señales' in line or 'Tickers únicos' in line:
            print(line.strip())
    
    # Step 2: TTH Prediction
    print(f"\n[2/3] Predicción TTH...")
    cmd2 = f"python scripts/39_predict_tth_intraday.py --date {date}"
    result = subprocess.run(cmd2, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR en TTH: {result.stderr}")
        continue
    
    for line in result.stdout.split('\n'):
        if 'ETTH medio' in line or 'P(TP<SL) medio' in line:
            print(line.strip())
    
    # Step 3: Trade Plan
    print(f"\n[3/3] Plan de trading...")
    cmd3 = f"python scripts/40_make_trade_plan_intraday.py --date {date}"
    result = subprocess.run(cmd3, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR en plan: {result.stderr}")
        continue
    
    for line in result.stdout.split('\n'):
        if 'Plan final' in line or 'Exposure total' in line or 'Prob win media' in line:
            print(line.strip())

print("\n" + "=" * 80)
print("PIPELINE COMPLETADO")
print("=" * 80)
