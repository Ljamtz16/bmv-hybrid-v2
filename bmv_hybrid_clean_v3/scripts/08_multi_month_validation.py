# scripts/08_multi_month_validation.py
from __future__ import annotations
import argparse, os, subprocess, sys, shutil, json
from pathlib import Path
import pandas as pd
import yaml

CFG_PATH = Path("config/base.yaml")
REPORTS = Path("reports")
SWEEP_DIR = REPORTS / "param_sweep"
SUMMARY_CSV = SWEEP_DIR / "param_sweep_summary.csv"

def expand_months(expr: str) -> list[str]:
    """
    Acepta:
      - Lista: "2024-09,2024-10,2024-11"
      - Rango: "2024-09:2025-01"  (ambos inclusive)
    Devuelve lista ordenada de YYYY-MM.
    """
    expr = expr.strip()
    if ":" not in expr:
        return [m.strip() for m in expr.split(",") if m.strip()]
    start_s, end_s = [x.strip() for x in expr.split(":", 1)]
    start = pd.Period(start_s, freq="M")
    end = pd.Period(end_s, freq="M")
    months = pd.period_range(start, end, freq="M")
    return [p.strftime("%Y-%m") for p in months]

def run_sweep(months: list[str],
              tp: str, sl: str, trail: str, trail_act: str, breakeven: str,
              gate: str,
              dump: bool,
              lookback_months: int,
              use_lookback_tau: bool,
              use_lookback_gate: bool,
              gate_min_trades: int,
              gate_expect_min: float):
    cmd = [
        str(Path(".venv/Scripts/python.exe")), "scripts/07_param_sweep_eval.py",
        "--months", ",".join(months),
        "--tp", tp, "--sl", sl, "--trail", trail, "--trail_act", trail_act,
        "--breakeven", breakeven, "--gate", gate,
        "--lookback_months", str(lookback_months),
    ]
    if dump: cmd.append("--dump")
    if use_lookback_tau: cmd.append("--use_lookback_tau")
    if use_lookback_gate: cmd.append("--use_lookback_gate")
    cmd.extend(["--gate_min_trades", str(gate_min_trades)])
    cmd.extend(["--gate_expect_min", str(gate_expect_min)])

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    print("→ Ejecutando:", " ".join(cmd))
    proc = subprocess.run(cmd, env=env)
    if proc.returncode != 0:
        sys.exit(proc.returncode)

def consolidate(months: list[str], topN: int = 3):
    if not SUMMARY_CSV.exists():
        print(f"⚠️ No existe {SUMMARY_CSV}. Corre primero el sweep.")
        sys.exit(1)
    df = pd.read_csv(SUMMARY_CSV)
    if "eval_start" not in df.columns or "run_tag" not in df.columns:
        print("⚠️ SUMMARY no tiene columnas esperadas.")
        sys.exit(1)

    # Derivar month YYYY-MM a partir de eval_start
    df["month"] = pd.to_datetime(df["eval_start"]).dt.strftime("%Y-%m")
    df = df[df["month"].isin(months)].copy()
    if df.empty:
        print("⚠️ No hay filas para los meses pedidos.")
        sys.exit(1)

    # === Top N por mes (orden PnL_sum desc, luego Sharpe)
    top_rows = []
    for m in sorted(df["month"].unique()):
        dm = df[df["month"] == m].copy()
        dm = dm.sort_values(["PnL_sum", "Sharpe"], ascending=[False, False])
        dm["rank"] = range(1, len(dm) + 1)
        top_rows.append(dm.head(topN))
    top_df = pd.concat(top_rows, ignore_index=True)
    out_top = SWEEP_DIR / "topN_validation.csv"
    top_df.to_csv(out_top, index=False, encoding="utf-8")
    print(f"✅ Top {topN} por mes → {out_top}")

    # === Agregado global por run_tag
    agg = (df.groupby("run_tag", as_index=False)
             .agg(
                 Trades=("Trades","sum"),
                 WinRate_avg=("WinRate_%","mean"),
                 PnL_sum=("PnL_sum","sum"),
                 MDD_avg=("MDD","mean"),
                 Sharpe_avg=("Sharpe","mean"),
                 Expectancy_avg=("Expectancy","mean")
             )
          )
    agg = agg.sort_values(["PnL_sum", "Sharpe_avg"], ascending=[False, False])
    out_agg = SWEEP_DIR / "validation_aggregate.csv"
    agg.to_csv(out_agg, index=False, encoding="utf-8")
    print(f"✅ Agregado global → {out_agg}")

    # Campeón global (línea 1)
    if not agg.empty:
        champ = agg.iloc[0].to_dict()
        print("\n🏆 Campeón global (agregado por meses):")
        for k, v in champ.items():
            print(f"  {k}: {v}")

def maybe_override_tickers(tickers_csv: str | None):
    """
    Si se pasa --tickers "ALFA.MX,BETA.MX", sobreescribe temporalmente base.yaml.
    Hace backup y restaura al final (usa contexto).
    """
    class Ctx:
        def __init__(self, do_backup: bool): self.do_backup = do_backup
        def __enter__(self):
            if not tickers_csv: return
            self.bak = CFG_PATH.with_suffix(".backup.before_08.yaml")
            shutil.copy2(CFG_PATH, self.bak)
            with CFG_PATH.open("r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            tlst = [t.strip() for t in tickers_csv.split(",") if t.strip()]
            cfg["tickers"] = tlst
            with CFG_PATH.open("w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
            print(f"📝 Tickers temporales aplicados en base.yaml: {tlst}")
        def __exit__(self, exc_type, exc, tb):
            if tickers_csv:
                shutil.copy2(self.bak, CFG_PATH)
                print("🔙 base.yaml restaurado (tickers originales).")
    return Ctx(bool(tickers_csv))

def parse_args():
    p = argparse.ArgumentParser(description="Validación multi-mes y consolidación.")
    p.add_argument("--months", type=str, required=True,
                   help='Rango o lista. Ej: "2024-09:2025-01" o "2024-11,2024-12"')
    p.add_argument("--tickers", type=str, default=None,
                   help='Opcional: lista de tickers para esta validación, ej: "ALSEA.MX,OMAB.MX" (se restaura al final)')
    p.add_argument("--tp", type=str, default="1.6,1.7",
                   help="Valores de tp_atr_mult")
    p.add_argument("--sl", type=str, default="0.7,0.8",
                   help="Valores de sl_atr_mult")
    p.add_argument("--trail", type=str, default="0.6,0.7",
                   help="Valores de trail_atr_mult")
    p.add_argument("--trail_act", type=str, default="0.6",
                   help="Valores de trail_activation_atr")
    p.add_argument("--breakeven", type=str, default="0.8,1.0",
                   help="Valores de break_even_atr")
    p.add_argument("--gate", type=str, default="auto,true,false",
                   help="Modos de buy_gate")
    p.add_argument("--dump", action="store_true", help="Guardar dumps por corrida")
    p.add_argument("--lookback_months", type=int, default=12)
    p.add_argument("--use_lookback_tau", action="store_true")
    p.add_argument("--use_lookback_gate", action="store_true")
    p.add_argument("--gate_min_trades", type=int, default=6)
    p.add_argument("--gate_expect_min", type=float, default=0.0)
    p.add_argument("--topN", type=int, default=3, help="Top-N por mes")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    months = expand_months(args.months)

    with maybe_override_tickers(args.tickers):
        run_sweep(
            months=months,
            tp=args.tp, sl=args.sl, trail=args.trail, trail_act=args.trail_act, breakeven=args.breakeven,
            gate=args.gate, dump=args.dump,
            lookback_months=args.lookback_months,
            use_lookback_tau=args.use_lookback_tau,
            use_lookback_gate=args.use_lookback_gate,
            gate_min_trades=args.gate_min_trades,
            gate_expect_min=args.gate_expect_min,
        )

    consolidate(months, topN=args.topN)
