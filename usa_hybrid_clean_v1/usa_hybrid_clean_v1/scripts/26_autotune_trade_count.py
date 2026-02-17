import argparse, json, os, pandas as pd
from calendar import monthrange

GRID_MIN_PROB = [0.52, 0.54, 0.56, 0.58, 0.60]
GRID_MIN_ABSY = [0.04, 0.05, 0.06, 0.07]

def count_signals(forecast_csv, p, y, gate_threshold):
    df = pd.read_csv(forecast_csv)
    df.columns = [c.lower().strip() for c in df.columns]
    gate_ok = (df.get("gate_ok", 1) == 1)
    patt_ok = (df.get("gate_pattern_ok", 1) == 1)
    # leve tolerancia si existe pattern_weight
    if "pattern_weight" in df.columns:
        gate_ok = gate_ok & (df["pattern_weight"] >= (gate_threshold - 0.50))
    m = gate_ok & patt_ok
    if "prob_win" in df.columns:
        m = m & (df["prob_win"] >= p)
    if "y_hat" in df.columns:
        m = m & (df["y_hat"].abs() >= y)
    return int(m.sum())

def feasible_trades(month, horizon_days, max_open, cooldown_days):
    year, mo = map(int, month.split("-"))
    days = monthrange(year, mo)[1]
    cycles = days / max(1, (horizon_days + cooldown_days))
    return int(cycles * max_open)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--forecast", required=True)
    ap.add_argument("--target_low", type=int, default=10)
    ap.add_argument("--target_high", type=int, default=15)
    ap.add_argument("--gate-threshold", type=float, default=0.58)
    ap.add_argument("--gate-grid", type=str, default="0.56,0.57,0.58",
                    help="Comma-separated gate thresholds to consider; if empty, use --gate-threshold only")
    ap.add_argument("--horizon-days", type=int, default=3)
    ap.add_argument("--max-open", type=int, default=5)
    ap.add_argument("--cooldown-days", type=int, default=0)
    ap.add_argument("--out-choice", dest="out_choice", default=None)
    ap.add_argument("--write-policy", action="store_true")
    ap.add_argument("--policy-dir", default="policies/monthly")
    args = ap.parse_args()

    cap = feasible_trades(args.month, args.horizon_days, args.max_open, args.cooldown_days)
    target_mid = 0.5 * (args.target_low + args.target_high)

    best = None
    best_exec_est = None
    gates = []
    if args.gate_grid:
        try:
            gates = [float(x) for x in args.gate_grid.split(",") if x.strip()]
        except Exception:
            gates = []
    if not gates:
        gates = [float(args.gate_threshold)]

    for gt in gates:
        for mp in GRID_MIN_PROB:
            for ay in GRID_MIN_ABSY:
                n = count_signals(args.forecast, mp, ay, gt)
                # Estima ejecución realista: limitado por capacidad y penalizado por severidad del umbral
                strict_penalty = max(0.0, mp - 0.50) * 1.1
                exec_est = min(n, cap) * (1.0 - strict_penalty)
                score = abs(target_mid - exec_est)
                penalty = 0.0
                if exec_est < args.target_low:
                    # penalizaciones fuertes si quedamos bajo 10
                    if mp >= 0.58:
                        penalty += 6.0
                    if ay >= 0.06:
                        penalty += 3.0
                    if gt >= 0.58:
                        penalty += 2.0
                if exec_est > args.target_high:
                    if mp <= 0.56:
                        penalty += 1.5
                    if ay <= 0.05:
                        penalty += 1.0
                total_score = score + penalty
                cand = {
                    "month": args.month,
                    "gate_threshold": gt,
                    "min_prob": mp,
                    "min_abs_yhat": ay,
                    "signals": n,
                    "exec_cap": cap,
                    "exec_est": exec_est,
                    "score": total_score,
                }
                if best is None or cand["score"] < best["score"]:
                    best = cand
                    best_exec_est = exec_est

    if args.out_choice:
        os.makedirs(os.path.dirname(args.out_choice), exist_ok=True)
        with open(args.out_choice, "w") as f:
            json.dump({"best": best}, f, indent=2)
    print("[autotune]", best)

    if args.write_policy and args.month:
        os.makedirs(args.policy_dir, exist_ok=True)
        out_pol = os.path.join(args.policy_dir, f"Policy_{args.month}.json")
        # Fallback si seguimos cortos: forzar mínimos y gate sugeridos
        if best_exec_est is not None and best_exec_est < args.target_low:
            best["min_prob"] = 0.54
            best["min_abs_yhat"] = 0.05
            best["gate_threshold"] = 0.56
        monthly = {
            "month": args.month,
            "gate_threshold": best["gate_threshold"],
            "min_prob": best["min_prob"],
            "min_abs_yhat": best["min_abs_yhat"],
        }
        # Nota: per_trade_cash se ajusta en el runner según capital y max_open
        with open(out_pol, "w") as f:
            json.dump(monthly, f, indent=2)
        print(f"[autotune] Policy mensual escrita -> {out_pol}  {best}")

if __name__ == "__main__":
    main()
