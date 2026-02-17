# scripts/09_prepare_paper_config.py
from __future__ import annotations
import re, sys
from pathlib import Path
import pandas as pd
import yaml

CFG = Path("config/paper.yaml")
SWEEP = Path("reports/param_sweep")
AGG = SWEEP / "validation_aggregate.csv"
SUM = SWEEP / "param_sweep_summary.csv"

RGX = re.compile(
    r"^(?P<month>\d{4}-\d{2})_tp(?P<tp>[0-9.]+)_sl(?P<sl>[0-9.]+)_tr(?P<tr>[0-9.]+)_act(?P<act>[0-9.]+)_be(?P<be>[0-9.]+)_(?P<gate>auto|true|false)"
)

def parse_run_tag(run_tag: str):
    m = RGX.match(run_tag)
    if not m:
        raise ValueError(f"No pude parsear run_tag: {run_tag}")
    d = m.groupdict()
    return dict(
        tp_atr_mult=float(d["tp"]),
        sl_atr_mult=float(d["sl"]),
        trail_atr_mult=float(d["tr"]),
        trail_activation_atr=float(d["act"]),
        break_even_atr=float(d["be"]),
        buy_gate_mode=d["gate"]
    )

def pick_best(run_tag: str | None):
    # Prefiere agregado global
    if AGG.exists():
        df = pd.read_csv(AGG)
        df = df.sort_values(["PnL_sum","Sharpe_avg"], ascending=[False, False])
        best = df.iloc[0]["run_tag"] if "run_tag" in df.columns else None
    elif SUM.exists():
        df = pd.read_csv(SUM)
        df = df.sort_values(["PnL_sum","Sharpe"], ascending=[False, False])
        best = df.iloc[0]["run_tag"] if "run_tag" in df.columns else None
    else:
        raise SystemExit("No encuentro resultados (validation_aggregate.csv ni param_sweep_summary.csv)")

    return run_tag or str(best)

if __name__ == "__main__":
    run_tag = None
    if len(sys.argv) > 1:
        # uso: python 09_prepare_paper_config.py "<run_tag>"
        run_tag = sys.argv[1]

    chosen = pick_best(run_tag)
    params = parse_run_tag(chosen)

    with CFG.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("exec", {})
    cfg["exec"].update({
        "tp_atr_mult": params["tp_atr_mult"],
        "sl_atr_mult": params["sl_atr_mult"],
        "commission_pct": cfg["exec"].get("commission_pct", 0.001),
        "slippage_pct": cfg["exec"].get("slippage_pct", 0.0002),
        "max_holding_days": cfg["exec"].get("max_holding_days", 3),
        "trail_atr_mult": params["trail_atr_mult"],
        "trail_activation_atr": params["trail_activation_atr"],
        "break_even_atr": params["break_even_atr"],
    })
    # signals.apply_buy_gate según modo elegido
    cfg.setdefault("signals", {})
    cfg["signals"]["apply_buy_gate"] = params["buy_gate_mode"]

    with CFG.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)

    print("✅ Config actualizada para paper trading con:", chosen)
    print("→ exec:", {k: cfg["exec"][k] for k in ["tp_atr_mult","sl_atr_mult","trail_atr_mult","trail_activation_atr","break_even_atr"]})
    print("→ signals.apply_buy_gate:", cfg["signals"]["apply_buy_gate"])
