"""
policy_tuner.py — Selección walk-forward de la política de trading por mes.

Uso:
  python scripts/policy_tuner.py --targets 2025-02 2025-03 2025-04 --back-k 2 --metric net_rr --lambda 0.5

Salida:
  reports/forecast/policy_selected_walkforward.csv
    columnas: target_month, min_abs_y, tp_pct, sl_pct, horizon_days, long_only,
              capital_initial, fixed_cash_per_trade, commission_side, score, metric, back_k, lambda

Notas:
- Optimiza parámetros de la ESTRATEGIA (no del modelo) usando SOLO meses previos a cada target.
- Métricas disponibles:
    net      : suma de net_pnl_sum
    net_rr   : suma net_pnl_sum - λ * max_drawdown_mensual (equity por meses de backset)
    per_trade: media de (net_pnl_sum / trades) en backset (robusto a distinto # de operaciones)
- Tolerante a meses faltantes en el backset: salta meses sin predictions.csv y, si es necesario,
  reduce back_k a 1. Si no hay evidencia, usa defaults.
"""
import os, sys, argparse, subprocess, json, itertools, csv, statistics, re
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
FORECAST_DIR = os.path.join(ROOT, "reports", "forecast")
POLICY_CSV = os.path.join(FORECAST_DIR, "policy_selected_walkforward.csv")

# ============== Espacio de búsqueda (ajústalo si quieres) ===================
SPACE = {
    "tp_pct":        [0.03, 0.04],
    "sl_pct":        [0.02, 0.025, 0.03],
    "horizon_days":  [3, 4, 5],
    "min_abs_y":     [0.035, 0.04, 0.045, 0.05],
    "long_only":     [True],
}
# Parámetros fijos de trading
CAPITAL_INITIAL = 10000
FIXED_CASH      = 2000
COMMISSION_SIDE = 5.0
# ============================================================================

def month_back_list(end_month: str, k: int = 2):
    """Lista cronológica de k meses previos a end_month (YYYY-MM)."""
    y, m = map(int, end_month.split("-"))
    base = datetime(y, m, 1)
    out = []
    for i in range(1, k+1):
        mm = (base.month - i - 1) % 12 + 1
        yy = base.year + (base.month - i - 1) // 12
        if mm <= 0:
            mm += 12
        out.append(f"{yy:04d}-{mm:02d}")
    return sorted(out)

def month_has_predictions(month: str) -> bool:
    pred = os.path.join(FORECAST_DIR, month, "validation", "predictions.csv")
    return os.path.exists(pred)

import re, json, ast

PAT = re.compile(r"Simulación terminada\. Resumen:\s*(\{.*\})", re.DOTALL)

def parse_summary_from_output(output_text: str):
    """
    Extrae el dict de 'Simulación terminada. Resumen: {...}'.
    1) Intenta JSON; 2) cae a ast.literal_eval si hay comillas simples, etc.
    Toma la ÚLTIMA ocurrencia por seguridad.
    """
    m = list(PAT.finditer(output_text))
    if not m:
        return None
    blob = m[-1].group(1).strip()

    # 1) JSON
    try:
        return json.loads(blob)
    except Exception:
        pass

    # 2) Dict Python (comillas simples)
    try:
        return ast.literal_eval(blob)
    except Exception:
        return None


def run_sim(month: str, params: dict):
    args = [
        sys.executable, os.path.join(HERE, "simulate_trading.py"),
        "--month", month,
        "--capital-initial", str(CAPITAL_INITIAL),
        "--fixed-cash", str(FIXED_CASH),
        "--tp-pct", str(params["tp_pct"]),
        "--sl-pct", str(params["sl_pct"]),
        "--horizon-days", str(params["horizon_days"]),
        "--commission-side", str(COMMISSION_SIDE),
        "--min-abs-y", str(params["min_abs_y"]),
    ]
    if params.get("long_only", True):
        args.append("--long-only")
    p = subprocess.run(args, capture_output=True, text=True, cwd=ROOT)
    combined = (p.stdout or "") + "\n" + (p.stderr or "")
    return parse_summary_from_output(combined)

def grid(space):
    keys = list(space.keys())
    for vals in itertools.product(*(space[k] for k in keys)):
        yield dict(zip(keys, vals))

def max_drawdown_from_monthly_equity(month_results):
    """
    Aproxima max drawdown a partir de equity mensual (cumulative net_pnl_sum).
    month_results: lista de dicts con net_pnl_sum por mes en orden cronológico.
    """
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in month_results:
        equity += r.get("net_pnl_sum", 0.0)
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
    return max_dd

def score_net(back_results, lam=0.5):
    # Suma neta sin penalización
    return sum(r.get("net_pnl_sum", 0.0) for r in back_results)

def score_net_rr(back_results, lam=0.5):
    # Reward-Risk mensual: neto - λ * max_drawdown_mensual
    net = sum(r.get("net_pnl_sum", 0.0) for r in back_results)
    dd  = max_drawdown_from_monthly_equity(back_results)
    return net - lam * dd

def score_per_trade(back_results, lam=0.5):
    # Media de net_pnl por trade en los meses de backset
    per_tr = []
    for r in back_results:
        n = max(1, int(r.get("trades", 0)))
        per_tr.append(r.get("net_pnl_sum", 0.0) / n)
    return statistics.mean(per_tr) if per_tr else -1e18

def evaluate_combo(back_months, combo, metric="net", lam=0.5):
    results = []
    for m in back_months:
        if not month_has_predictions(m):
            # No hay datos para evaluar este mes -> lo saltamos
            continue
        res = run_sim(m, combo)
        if not res:
            # Si falló la simulación de este mes, lo saltamos también
            continue
        results.append(res)

    if not results:
        # Sin evidencia, devolvemos score muy bajo para descartar el combo
        return None, -1e18

    if metric == "net":
        sc = score_net(results, lam)
    elif metric == "net_rr":
        sc = score_net_rr(results, lam)
    elif metric == "per_trade":
        sc = score_per_trade(results, lam)
    else:
        sc = score_net(results, lam)
    return results, sc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="+", required=False,
                    help="Meses target YYYY-MM (si no se pasan, se detectan en reports/forecast/)")
    ap.add_argument("--back-k", type=int, default=2, help="Meses hacia atrás para tuning (default 2)")
    ap.add_argument("--metric", choices=["net","net_rr","per_trade"], default="net", help="Objetivo de selección")
    ap.add_argument("--lambda", dest="lam", type=float, default=0.5, help="Peso de penalización (solo net_rr)")
    args = ap.parse_args()

    # Detectar targets si no vienen por CLI
    targets = args.targets
    if not targets:
        if not os.path.isdir(FORECAST_DIR):
            print(f"ERROR: No existe {FORECAST_DIR}. Genera forecasts primero.")
            sys.exit(1)
        targets = sorted([d for d in os.listdir(FORECAST_DIR) if len(d)==7 and d[4]=='-'])

    Path(FORECAST_DIR).mkdir(parents=True, exist_ok=True)

    rows = []
    for t in targets:
        # Construir backset con tolerancia a falta de meses
        raw_back = month_back_list(t, k=args.back_k)
        back_months = [m for m in raw_back if month_has_predictions(m)]
        if not back_months and args.back_k > 1:
            raw_back = month_back_list(t, k=1)
            back_months = [m for m in raw_back if month_has_predictions(m)]

        if not back_months:
            print(f"[policy_tuner] WARNING: no hay backset utilizable para {t} (faltan predictions). Usaré defaults.")
            rows.append({
                "target_month": t,
                "min_abs_y": 0.04,
                "tp_pct": 0.03,
                "sl_pct": 0.025,
                "horizon_days": 5,
                "long_only": True,
                "capital_initial": CAPITAL_INITIAL,
                "fixed_cash_per_trade": FIXED_CASH,
                "commission_side": COMMISSION_SIDE,
                "score": 0.0,
                "metric": args.metric,
                "back_k": args.back_k,
                "lambda": args.lam,
            })
            print(f"[policy_tuner] {t} -> best=defaults (sin backset disponible)")
            continue

        best_score = -1e18
        best_combo = None

        print(f"[policy_tuner] Tuning para {t} con backset={back_months}, metric={args.metric}, lambda={args.lam}")
        for combo in grid(SPACE):
            _, sc = evaluate_combo(back_months, combo, metric=args.metric, lam=args.lam)
            if sc > best_score:
                best_score, best_combo = sc, combo

        if best_combo is None:
            print(f"[policy_tuner] WARNING: no hubo combo válido para {t}, usando defaults.")
            best_combo = dict(tp_pct=0.03, sl_pct=0.025, horizon_days=5, min_abs_y=0.04, long_only=True)
            best_score = 0.0

        rows.append({
            "target_month": t,
            "min_abs_y": best_combo["min_abs_y"],
            "tp_pct": best_combo["tp_pct"],
            "sl_pct": best_combo["sl_pct"],
            "horizon_days": best_combo["horizon_days"],
            "long_only": best_combo.get("long_only", True),
            "capital_initial": CAPITAL_INITIAL,
            "fixed_cash_per_trade": FIXED_CASH,
            "commission_side": COMMISSION_SIDE,
            "score": round(best_score, 4),
            "metric": args.metric,
            "back_k": args.back_k,
            "lambda": args.lam,
        })

        print(f"[policy_tuner] {t} -> best={best_combo} score={best_score:.2f}")

    # Guardar CSV
    if rows:
        keys = ["target_month","min_abs_y","tp_pct","sl_pct","horizon_days","long_only",
                "capital_initial","fixed_cash_per_trade","commission_side",
                "score","metric","back_k","lambda"]
        with open(POLICY_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"[policy_tuner] Guardado: {POLICY_CSV}")
    else:
        print("[policy_tuner] No se generó ninguna fila (¿sin targets?).")

if __name__ == "__main__":
    main()
