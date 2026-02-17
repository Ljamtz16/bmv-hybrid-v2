# scripts/28_promote_policy_to_wfbox.py
from __future__ import annotations
import argparse, json, csv
from pathlib import Path

HEAD = [
    "month","tp_pct","sl_pct","horizon_days","min_abs_y",
    "long_only","per_trade_cash","commission_side"
]

def load_best_policy_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        p = json.load(f)
    # Defaults por si faltan en el JSON
    p.setdefault("min_abs_y", 0.0)
    p.setdefault("long_only", True)
    p.setdefault("per_trade_cash", 1000.0)
    p.setdefault("commission_side", 5.0)
    return p

def upsert_row(rows: list[dict], new_row: dict) -> list[dict]:
    out = []
    found = False
    for r in rows:
        if r["month"] == new_row["month"]:
            out.append(new_row)
            found = True
        else:
            out.append(r)
    if not found:
        out.append(new_row)
    return out

def main():
    ap = argparse.ArgumentParser(description="Promueve una policy JSON al CSV walk-forward.")
    ap.add_argument("--month", required=True, help="YYYY-MM (ej: 2025-05)")
    ap.add_argument("--policy-json", required=True, help="JSON con tp/sl/h/etc (p.ej. runs/policy_best_YYYY-MM.json)")
    ap.add_argument("--wf-csv", default="wf_box/reports/forecast/policy_selected_walkforward.csv",
                    help="CSV maestro de políticas walk-forward")
    args = ap.parse_args()

    best = load_best_policy_json(Path(args.policy_json))

    # Cargar CSV existente si hay
    wf_csv = Path(args.wf_csv)
    rows = []
    if wf_csv.exists():
        with open(wf_csv, "r", encoding="utf-8-sig", newline="") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                rows.append(r)

    # Normaliza tipos a str para escribir CSV
    new_row = {
        "month": args.month,
        "tp_pct": str(best["tp_pct"]),
        "sl_pct": str(best["sl_pct"]),
        "horizon_days": str(best["horizon_days"]),
        "min_abs_y": str(best.get("min_abs_y", 0.0)),
        "long_only": "True" if best.get("long_only", True) else "False",
        "per_trade_cash": str(best.get("per_trade_cash", 1000.0)),
        "commission_side": str(best.get("commission_side", 5.0)),
    }

    rows = upsert_row(rows, new_row)

    # Ordena por mes (opcional)
    rows = sorted(rows, key=lambda r: r["month"])

    wf_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(wf_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEAD)
        w.writeheader()
        for r in rows:
            # Asegura que estén todas las columnas
            rfull = {k: r.get(k, "") for k in HEAD}
            w.writerow(rfull)

    print(f"✅ Policy de {args.month} promovida a {wf_csv}")

if __name__ == "__main__":
    main()
