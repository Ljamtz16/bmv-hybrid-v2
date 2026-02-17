# -*- coding: utf-8 -*-
"""
Recolecta KPIs diarios desde reports/intraday/YYYY-MM-DD
y genera un CSV resumen para comparar políticas (A/B).
- Lee plan_stats.json si existe (campos flexibles)
- Calcula métricas a partir de trade_plan_intraday.csv si faltan
- Soporta etiqueta --tag para diferenciar políticas
- Salida: paper_summary.csv (append seguro)

Uso:
  python scripts/collect_paper_results.py --root reports/intraday --tag A
  python scripts/collect_paper_results.py --root reports/intraday --tag B --out paper_summary.csv
"""

import argparse, json, sys, math
from pathlib import Path
from datetime import datetime
import csv

def read_text_safe(p: Path) -> str:
    if not p.exists():
        return ""
    raw = p.read_text(encoding="utf-8", errors="replace")
    # quita BOM si viene de editores de Windows
    if raw and raw[0] == "\ufeff":
        raw = raw.lstrip("\ufeff")
    return raw

def load_json_safe(p: Path):
    try:
        raw = read_text_safe(p)
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}

def parse_float(x, default=0.0):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return default
        return float(x)
    except Exception:
        return default

def list_day_dirs(root: Path):
    # Directorios tipo YYYY-MM-DD
    items = []
    if not root.exists():
        return items
    for child in root.iterdir():
        if child.is_dir():
            name = child.name
            try:
                # valida formato fecha
                datetime.strptime(name, "%Y-%m-%d")
                items.append(child)
            except ValueError:
                pass
    return sorted(items, key=lambda p: p.name)

def read_csv_rows(p: Path):
    if not p.exists():
        return []
    import pandas as pd
    try:
        df = pd.read_csv(p)
        return df
    except Exception:
        # lector mínimo si pandas no está disponible
        rows = []
        with p.open("r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        # conv. lista dicts -> DataFrame-like mínimo
        class MiniDF(list):
            def __init__(self, rows):
                super().__init__(rows)
                self.columns = list(rows[0].keys()) if rows else []
            def __len__(self): return super().__len__()
            def __iter__(self): return super().__iter__()
            def __getitem__(self, key):
                return [r.get(key) for r in self]
        return MiniDF(rows)

def compute_day_metrics(day_dir: Path):
    """
    Intenta usar plan_stats.json si existe.
    Si no, calcula desde trade_plan_intraday.csv:
      - num_trades, exposure_total
      - exp_pnl_sum_usd (sum(exp_pnl_pct * exposure))
      - prob_win_mean, p_tp_before_sl_mean
      - etth_median_days, spread_mean_bps
    """
    stats_path = day_dir / "plan_stats.json"
    plan_path  = day_dir / "trade_plan_intraday.csv"

    stats = load_json_safe(stats_path)
    result = {
        "date": day_dir.name,
        "num_candidates": None,
        "num_plan_trades": None,
        "exposure_total": None,
        "prob_win_mean": None,
        "p_tp_before_sl_mean": None,
        "etth_median_days": None,
        "spread_mean_bps": None,
        "exp_pnl_sum_pct": None,   # suma % (ponderada por nada)
        "exp_pnl_sum_usd": None,   # suma en USD (usando exposure)
        "notes": ""
    }

    # Prioriza stats si trae campos útiles
    if stats:
        result["num_candidates"]       = stats.get("num_candidates")
        result["num_plan_trades"]      = stats.get("num_plan_trades")
        result["exposure_total"]       = stats.get("exposure_total")
        result["prob_win_mean"]        = stats.get("prob_win_mean")
        result["p_tp_before_sl_mean"]  = stats.get("p_tp_before_sl_mean")
        result["etth_median_days"]     = stats.get("etth_median_days")
        result["spread_mean_bps"]      = stats.get("spread_mean_bps")
        result["exp_pnl_sum_pct"]      = stats.get("exp_pnl_sum_pct")
        # damos preferencia a exp_pnl_sum_usd si viene
        result["exp_pnl_sum_usd"]      = stats.get("exp_pnl_sum_usd")

    # Completa/valida con el CSV del plan
    df = read_csv_rows(plan_path)
    if len(df) > 0:
        # Usa nombres de columnas del plan que ya estás generando
        # entry_price, exposure, exp_pnl_pct, prob_win, p_tp_before_sl, ETTH, spread_bps
        try:
            import pandas as pd
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(list(df))

            # Normaliza columnas si vienen con mayúsculas/minúsculas distintas
            cols = {c.lower(): c for c in df.columns}
            def getcol(name):
                return cols.get(name.lower())

            # num trades / exposure
            exposure_col = getcol("exposure")
            if exposure_col in df.columns:
                exposure_total = float(pd.to_numeric(df[exposure_col], errors="coerce").fillna(0).sum())
                result["exposure_total"] = exposure_total

            result["num_plan_trades"] = int(len(df))

            # medias
            for src, dest in [
                ("prob_win", "prob_win_mean"),
                ("p_tp_before_sl", "p_tp_before_sl_mean"),
                ("spread_bps", "spread_mean_bps")
            ]:
                c = getcol(src)
                if c in df.columns:
                    val = pd.to_numeric(df[c], errors="coerce")
                    m = float(val.mean()) if len(val) else None
                    result[dest] = m

            # mediana ETTH
            c_etth = getcol("etth")
            if c_etth in df.columns:
                et = pd.to_numeric(df[c_etth], errors="coerce")
                med = float(et.median()) if len(et) else None
                result["etth_median_days"] = med

            # exp_pnl
            c_pct = getcol("exp_pnl_pct")
            if c_pct in df.columns:
                pct = pd.to_numeric(df[c_pct], errors="coerce").fillna(0.0)
                result["exp_pnl_sum_pct"] = float(pct.sum())

                if exposure_col in df.columns:
                    exp = pd.to_numeric(df[exposure_col], errors="coerce").fillna(0.0)
                    exp_usd = (pct * exp).sum()
                    if result["exp_pnl_sum_usd"] is None:
                        result["exp_pnl_sum_usd"] = float(exp_usd)

        except Exception as e:
            # si pandas falla, deja una nota
            result["notes"] = f"CSV parse fallback: {e}"

    # Defaults blandos si faltan
    for k in ["num_candidates","num_plan_trades","exposure_total"]:
        if result[k] is None: result[k] = 0
    for k in ["prob_win_mean","p_tp_before_sl_mean","etth_median_days","spread_mean_bps","exp_pnl_sum_pct","exp_pnl_sum_usd"]:
        if result[k] is None: result[k] = 0.0

    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="reports/intraday", help="Directorio raíz con carpetas YYYY-MM-DD")
    ap.add_argument("--tag", default="", help="Etiqueta de política/escenario (ej. A o B)")
    ap.add_argument("--out", default="paper_summary.csv", help="Archivo CSV de salida (append si existe)")
    args = ap.parse_args()

    root = Path(args.root)
    out  = Path(args.out)
    tag  = args.tag.strip()

    day_dirs = list_day_dirs(root)
    if not day_dirs:
        print(f"[collect] No se encontraron días en {root}")
        sys.exit(0)

    # Recolecta
    rows = []
    for d in day_dirs:
        r = compute_day_metrics(d)
        r["tag"] = tag
        rows.append(r)

    # Esquema columnas estable
    fieldnames = [
        "tag","date","num_candidates","num_plan_trades","exposure_total",
        "prob_win_mean","p_tp_before_sl_mean","etth_median_days","spread_mean_bps",
        "exp_pnl_sum_pct","exp_pnl_sum_usd","notes"
    ]

    # Append seguro (crea encabezado solo si no existe)
    write_header = not out.exists()
    with out.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    # Resumen por consola
    total_days = len(rows)
    total_trades = sum(int(r["num_plan_trades"]) for r in rows)
    total_exp_usd = sum(parse_float(r["exp_pnl_sum_usd"]) for r in rows)
    mean_prob_win = sum(parse_float(r["prob_win_mean"]) for r in rows if r["num_plan_trades"]>0)
    cnt_prob = sum(1 for r in rows if r["num_plan_trades"]>0)
    mean_prob_win = (mean_prob_win / cnt_prob) if cnt_prob else 0.0

    print("============================================================")
    print(f"[collect] Resumen '{tag or '-'}'  en {args.root}")
    print(f"  Dias: {total_days}")
    print(f"  Trades totales: {total_trades}")
    print(f"  E[PnL] total (USD): {total_exp_usd:.2f}")
    print(f"  Prob_win media (dias con trades): {mean_prob_win:.3f}")
    print(f"  CSV -> {out}")
    print("============================================================")

if __name__ == "__main__":
    main()
