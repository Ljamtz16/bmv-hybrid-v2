"""
Validación rápida del pipeline intraday
Ejecuta 11 → 39 → 40 para un día y muestra métricas clave
"""
import argparse
import subprocess
import sys
from pathlib import Path
import pandas as pd


def run_pipeline(date, prob_min: float | None = None):
    """Ejecutar pipeline completo."""
    print(f"\n{'='*60}")
    print(f"PIPELINE INTRADAY: {date}")
    print(f"{'='*60}\n")
    
    # Step 1: Inference
    print("▶ [1/3] Inferencia y filtros...")
    infer_cmd = [
        "python", "scripts/11_infer_and_gate_intraday.py", "--date", date
    ]
    if prob_min is not None:
        infer_cmd += ["--prob-min", str(prob_min)]
    else:
        infer_cmd += ["--prob-min", "0.35"]
    result = subprocess.run(
        infer_cmd,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"ERROR en inferencia:\n{result.stderr}")
        return False
    print(result.stdout.split('\n')[-4])  # Último resumen
    
    # Step 2: TTH
    print("\n▶ [2/3] Predicción TTH...")
    result = subprocess.run(
        ["python", "scripts/39_predict_tth_intraday.py", "--date", date],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"ERROR en TTH:\n{result.stderr}")
        return False
    # Extraer métricas TTH
    for line in result.stdout.split('\n'):
        if 'ETTH medio' in line or 'P(TP≺SL)' in line:
            print(f"  {line.strip()}")
    
    # Step 3: Trade Plan
    print("\n▶ [3/3] Plan de trading...")
    plan_cmd = [
        sys.executable, "scripts/40_make_trade_plan_intraday.py",
        "--date", date,
        "--tp-pct", "0.028", "--sl-pct", "0.005",
        "--allow-fractional",
        "--min-qty", "0.01",
        "--per-trade-cash", "250",
        "--capital-max", "1000"
    ]
    result = subprocess.run(
        plan_cmd,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"ERROR en plan:\n{result.stderr}")
        return False
    
    # Extraer resumen
    in_summary = False
    for line in result.stdout.split('\n'):
        if '=====' in line and 'RESUMEN' in line:
            in_summary = True
        if in_summary:
            print(line)
    
    return True


def show_plan(date):
    """Mostrar plan detallado."""
    plan_file = Path(f"reports/intraday/{date}/trade_plan_intraday.csv")
    if not plan_file.exists():
        print("\n⚠ No hay plan generado")
        return
    
    plan = pd.read_csv(plan_file)
    if len(plan) == 0:
        print("\n⚠ Plan vacío (0 trades)")
        return
    
    print(f"\n{'='*60}")
    print("DETALLE DEL PLAN")
    print(f"{'='*60}")
    
    for _, row in plan.iterrows():
        print(f"\n{row['direction']} {row['ticker']} @ {row['timestamp']}")
        print(f"  Entry: ${row['entry_price']:.2f}")
        print(f"  TP: ${row['tp_price']:.2f} (+{(row['tp_price']/row['entry_price']-1)*100:.1f}%)")
        print(f"  SL: ${row['sl_price']:.2f} ({(row['sl_price']/row['entry_price']-1)*100:.1f}%)")
        print(f"  Prob: {row['prob_win']*100:.1f}%, P(TP≺SL): {row['p_tp_before_sl']*100:.1f}%")
        print(f"  ETTH: {row['ETTH']*26:.1f} bars (~{row['ETTH']*6.5:.1f}h)")
        print(f"  E[PnL]: {row['exp_pnl_pct']*100:.2f}% (${row['exp_pnl_pct']*row['exposure']:.2f})")
        print(f"  Exposure: ${row['exposure']:.2f}")
    
    print(f"\n{'='*60}")
    print(f"TOTAL: {len(plan)} trades, ${plan['exposure'].sum():.2f} exposure")
    print(f"E[PnL] agregado: ${(plan['exp_pnl_pct'] * plan['exposure']).sum():.2f}")
    print(f"{'='*60}\n")


def show_snapshots(date):
    """Mostrar snapshots intermedios."""
    snap_dir = Path(f"reports/intraday/{date}")
    if not snap_dir.exists():
        return
    
    print(f"\n{'='*60}")
    print("SNAPSHOTS (para debugging)")
    print(f"{'='*60}")
    
    for snap in ['after_model', 'after_filters']:
        snap_file = snap_dir / f"forecast_{snap}.parquet"
        if snap_file.exists():
            df = pd.read_parquet(snap_file)
            print(f"  {snap}: {len(df)} filas")
            if len(df) > 0 and snap == 'after_model':
                print(f"    prob>=0.35: {(df['prob_win']>=0.35).sum()}")
                print(f"    prob>=0.50: {(df['prob_win']>=0.50).sum()}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Fecha YYYY-MM-DD")
    parser.add_argument("--show-snapshots", action="store_true", help="Mostrar snapshots intermedios")
    parser.add_argument("--prob-min", type=float, default=None, help="Umbral prob_win para el paso 11 (anula config)")
    args = parser.parse_args()
    
    success = run_pipeline(args.date, prob_min=args["prob_min"] if isinstance(args, dict) else args.prob_min)
    
    if success:
        show_plan(args.date)
        
        if args.show_snapshots:
            show_snapshots(args.date)
        
        print("✅ Pipeline completado exitosamente\n")
        sys.exit(0)
    else:
        print("❌ Pipeline falló\n")
        sys.exit(1)
