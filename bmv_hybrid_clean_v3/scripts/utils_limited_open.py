# scripts/utils_limited_open.py
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
import os, csv

def compute_score(sig: Dict) -> float:
    prob = float(sig.get("prob") or sig.get("prob_win") or sig.get("p", 0))
    ev   = float(sig.get("ev")   or sig.get("expected_value") or sig.get("expected_return", 1.0))
    return prob * ev if ev != 0 else prob

def _append_decision_log(out_csv: str, row: Dict):
    Path(os.path.dirname(out_csv)).mkdir(parents=True, exist_ok=True)
    write_header = not os.path.exists(out_csv)
    with open(out_csv, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=row.keys())
        if write_header:
            w.writeheader()
        w.writerow(row)

def select_signals_with_limits(
    signals_today: List[Dict],
    open_positions_count: int = 0,
    max_open: Optional[int] = None,
    per_trade_cash: Optional[float] = None,
    budget: Optional[float] = None,
    decision_log_csv: Optional[str] = None,
    now_dt: Optional[datetime] = None,
) -> List[Dict]:
    # 1) score
    for s in signals_today:
        s["score"] = compute_score(s)

    # 2) ordenar por prioridad
    candidates = sorted(signals_today, key=lambda s: s["score"], reverse=True)

    # 3) estado actual
    slots_left = (max_open - open_positions_count) if (isinstance(max_open, int) and max_open >= 0) else None
    cash_left  = None
    if budget is not None and per_trade_cash:
        used_cash = open_positions_count * float(per_trade_cash)
        cash_left = float(budget) - used_cash

    # 4) seleccionar
    selected = []
    for s in candidates:
        ok = True
        reason = "ok"

        if slots_left is not None and slots_left <= 0:
            ok = False; reason = f"blocked:max_open({max_open})"
        if ok and cash_left is not None and cash_left < float(per_trade_cash):
            ok = False; reason = f"blocked:budget({budget})"

        if ok:
            selected.append(s)
            if slots_left is not None: slots_left -= 1
            if cash_left  is not None: cash_left  -= float(per_trade_cash)
            if decision_log_csv:
                _append_decision_log(decision_log_csv, {
                    "dt": (now_dt or datetime.now()).isoformat(timespec="seconds"),
                    "ticker": s.get("ticker") or s.get("symbol"),
                    "score": f"{s['score']:.6f}",
                    "decision": "OPEN",
                    "reason": "ok",
                    "max_open": max_open if max_open is not None else "",
                    "budget": budget if budget is not None else "",
                    "per_trade_cash": per_trade_cash if per_trade_cash is not None else "",
                })
        else:
            if decision_log_csv:
                _append_decision_log(decision_log_csv, {
                    "dt": (now_dt or datetime.now()).isoformat(timespec="seconds"),
                    "ticker": s.get("ticker") or s.get("symbol"),
                    "score": f"{s.get('score',0):.6f}",
                    "decision": "SKIP",
                    "reason": reason,
                    "max_open": max_open if max_open is not None else "",
                    "budget": budget if budget is not None else "",
                    "per_trade_cash": per_trade_cash if per_trade_cash is not None else "",
                })

    return selected
