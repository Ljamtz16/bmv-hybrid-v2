import argparse, json, subprocess, sys, os
from pathlib import Path
from datetime import datetime

# ---------------------------
# Configuración por defecto
# ---------------------------
DEFAULT_DATES = [
    "2025-10-13","2025-10-14","2025-10-15","2025-10-16","2025-10-17",
    "2025-10-20","2025-10-21","2025-10-22","2025-10-23","2025-10-24",
    "2025-10-27","2025-10-30","2025-10-31"
]

def run(cmd):
    print(f"\n$ {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.stdout: print(res.stdout)
    if res.stderr: print(res.stderr)
    if res.returncode != 0:
        raise SystemExit(f"Command failed: {' '.join(cmd)}")
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="*", default=DEFAULT_DATES,
                    help="Fechas YYYY-MM-DD (por defecto: octubre 2025)")
    ap.add_argument("--tp-list", nargs="*", type=float, default=[0.015, 0.018, 0.020],
                    help="Lista de TP en fracción (ej. 0.018 = 1.8%)")
    ap.add_argument("--sl", type=float, default=0.005, help="SL en fracción (0.005 = 0.5%)")
    ap.add_argument("--prob-min", type=float, default=0.25, help="Umbral prob_win para paso 11/40")
    ap.add_argument("--p-tp-sl-min", type=float, default=0.15, help="Mínimo P(TP<SL) para paso 40")
    ap.add_argument("--cost", type=float, default=0.0004, help="Costo usado en E[PnL] del paso 40")
    ap.add_argument("--per-trade-cash", type=float, default=250.0)
    ap.add_argument("--capital-max", type=float, default=1000.0)
    ap.add_argument("--allow-fractional", action="store_true", help="Permite qty fraccional en paso 40")
    ap.add_argument("--min-qty", type=float, default=1.0, help="Mínimo de qty (1.0 si no fraccional)")
    ap.add_argument("--tag-prefix", default="sweep",
                    help="Prefijo de tag para colecta (se añade tpXXXX)")
    args = ap.parse_args()

    py = sys.executable  # usa el Python del venv actual

    # Verifica que existen scripts
    root = Path(__file__).resolve().parents[1]
    s39 = root / "scripts" / "39_predict_tth_intraday.py"
    s40 = root / "scripts" / "40_make_trade_plan_intraday.py"
    sCollect = root / "scripts" / "collect_paper_results.py"

    if not s39.exists() or not s40.exists() or not sCollect.exists():
        raise SystemExit("No encuentro 39/40/collect_paper_results.py. Revisa rutas.")

    # Barrido por TP
    for tp in args.tp_list:
        tp_bp = int(round(tp*10000))  # ej 0.018 -> 180
        tag = f"{args.tag_prefix}_tp{tp_bp}_sl{int(args.sl*10000)}"

        print("\n" + "="*80)
        print(f" BARRIDO TP={tp:.3%}  SL={args.sl:.3%}  TAG={tag}")
        print("="*80)

        for d in args.dates:
            # 1) Recalcular TTH para esa fecha (por si cambia TP/SL downstream)
            run([py, str(s39), "--date", d])

            # 2) Generar plan con parámetros deseados
            cmd40 = [
                py, str(s40), "--date", d,
                "--tp-pct", str(tp), "--sl-pct", str(args.sl),
                "--per-trade-cash", str(args.per_trade_cash),
                "--capital-max", str(args.capital_max),
                "--prob-win-min", str(args.prob_min),
                "--p-tp-sl-min", str(args.p_tp_sl_min)
            ]
            # Note: script 40 usa integer-only qty por defecto, no necesita --min-qty
            run(cmd40)

        # 3) Colectar resultados hacia paper_summary.csv con tag específico
        run([py, str(sCollect), "--root", "reports/intraday", "--tag", tag])

    print("\n" + "="*80)
    print(" Listo. Revisa paper_summary.csv y compara TAGs por columna.")
    print(" Consejo: usa compare_paper_policies.py para un resumen por TAG.")
    print("="*80)

if __name__ == "__main__":
    main()
