# scripts/paper_run_daily.py
from __future__ import annotations

import os
import argparse
from pathlib import Path
import pandas as pd

from src.config import load_cfg
from src.io.loader import load_daily_map
from scripts._eval_core import run_once_day, ensure_atr_aliases_inplace, pick_eval_dates

def parse_args():
    p = argparse.ArgumentParser(
        description="Runner de paper trading diario: evalúa día por día y construye equity."
    )
    p.add_argument("--start", required=True, type=str, help="Fecha inicio (YYYY-MM-DD), inclusive.")
    p.add_argument("--end", required=True, type=str, help="Fecha fin (YYYY-MM-DD), exclusivo.")
    p.add_argument("--cfg", type=str, default=os.environ.get("CFG", "config/paper.yaml"),
                   help="Ruta al YAML de configuración (default: env CFG o config/paper.yaml)")
    p.add_argument("--dump", action="store_true",
                   help="Si se pasa, guarda signals/trades por día en reports/paper_trading/YYYY-MM-DD/")
    return p.parse_args()

def main():
    args = parse_args()
    cfg = load_cfg(args.cfg)

    reports_root = Path(getattr(cfg, "reports_dir", "reports"))
    out_dir = reports_root / "paper_trading"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Fechas disponibles (ancla a un ticker con datos diarios)
    aliases = getattr(cfg, "aliases", None)
    d1_map = load_daily_map(Path(cfg.data_dir) / "raw" / "1d", cfg.tickers, aliases=aliases, debug=False)
    ensure_atr_aliases_inplace(d1_map)

    dates = pick_eval_dates(d1_map, cfg.tickers, args.start, args.end)
    if not dates:
        print(f"⚠️ No hay fechas entre {args.start} y {args.end}. Nada que hacer.")
        return

    # 2) Bucle diario
    rows = []
    equity = 0.0
    for d in dates:
        day_s = pd.Timestamp(d).strftime("%Y-%m-%d")
        day_e = (pd.Timestamp(d) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        dump_dir = (out_dir / day_s) if args.dump else None

        res = run_once_day(cfg, day_s, day_e, dump_dir=dump_dir)
        if "error" in res and res.get("Trades", 0) == 0:
            # Día sin mercado o sin datos → continuamos
            continue

        pnl = float(res.get("PnL_sum", 0.0))
        equity += pnl

        rows.append({
            "date": day_s,
            "pnl": pnl,
            "equity": equity,
            "trades": int(res.get("Trades", 0)),
            "win_rate_%": float(res.get("WinRate_%", 0.0)),
            "sharpe": float(res.get("Sharpe", 0.0)),
            "buy_gate": res.get("buy_gate", "")
        })

        print(f"{day_s} | pnl={pnl:.2f} | eq={equity:.2f} | trades={rows[-1]['trades']} | gate={rows[-1]['buy_gate']}")

    # 3) Guardar curva de equity
    df = pd.DataFrame(rows)
    out_csv = out_dir / "paper_daily_equity.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"\n✅ Paper trading finalizado. Equity final = {equity:.2f}")
    print(f"↳ Curva diaria guardada en: {out_csv}")

if __name__ == "__main__":
    main()
