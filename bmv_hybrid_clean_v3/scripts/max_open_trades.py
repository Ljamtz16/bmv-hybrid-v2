import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

# Candidatas a columnas de tiempo (minúsculas para matching case-insensitive)
CANDIDATES = [
    ("entry_time", "exit_time"),
    ("entry_dt", "exit_dt"),
    ("open_time", "close_time"),
    ("open_dt", "close_dt"),
    ("start_time", "end_time"),
    ("entry", "exit"),
    ("entry_timestamp", "exit_timestamp"),
    ("entry_ts", "exit_ts"),
    ("entry_datetime", "exit_datetime"),
    ("open_datetime", "close_datetime"),
    ("opened_at", "closed_at"),
    ("entry_time_utc", "exit_time_utc"),
    ("entry_dt_utc", "exit_dt_utc"),
]

def detect_cols(df: pd.DataFrame, entry_override: str = "", exit_override: str = ""):
    cols = list(df.columns)
    lower_map = {c.lower(): c for c in cols}

    # Overrides manuales
    if entry_override and exit_override:
        if entry_override in cols and exit_override in cols:
            return entry_override, exit_override
        raise ValueError(f"Overrides no válidos. Columnas en CSV: {cols}")

    # Match exacto por candidatos conocidos
    for a, b in CANDIDATES:
        if a in lower_map and b in lower_map:
            return lower_map[a], lower_map[b]

    # Fuzzy: algo tipo entry/open/start y exit/close/end con pista de tiempo
    def is_timey(name: str) -> bool:
        n = name.lower()
        return any(k in n for k in ["time", "date", "dt", "ts", "timestamp", "datetime"])

    entry_candidates = [
        c for c in cols
        if (("entry" in c.lower()) or ("open" in c.lower()) or ("start" in c.lower())) and is_timey(c)
    ]
    exit_candidates = [
        c for c in cols
        if (("exit" in c.lower()) or ("close" in c.lower()) or ("end" in c.lower())) and is_timey(c)
    ]

    if entry_candidates and exit_candidates:
        return entry_candidates[0], exit_candidates[0]

    sample = ", ".join(cols)
    raise ValueError(
        "No pude detectar columnas de tiempo (entry/exit). "
        f"Encabezados encontrados: {sample}\n"
        "Pasa --entry-col y --exit-col, o renombra para incluir 'entry/exit' + 'time|date|dt|ts'."
    )

def build_events(df: pd.DataFrame, entry_col: str, exit_col: str) -> pd.DataFrame:
    ev_open = pd.DataFrame({"t": pd.to_datetime(df[entry_col], errors="coerce"), "delta": 1})
    ev_close = pd.DataFrame({"t": pd.to_datetime(df[exit_col], errors="coerce"), "delta": -1})
    events = pd.concat([ev_open, ev_close], ignore_index=True)
    events = events.dropna(subset=["t"])
    return events

def sort_events(events: pd.DataFrame, ties: str) -> pd.DataFrame:
    """
    Empates (mismo timestamp):
      - 'open-first'  -> aperturas (+1) antes que cierres (-1)  => ascending=[True, False]
      - 'close-first' -> cierres (-1) antes que aperturas (+1) => ascending=[True, True]
    """
    if ties not in ("open-first", "close-first"):
        ties = "open-first"
    ascending = [True, False] if ties == "open-first" else [True, True]
    return events.sort_values(["t", "delta"], ascending=ascending).reset_index(drop=True)

def sweep_max_open(sorted_events: pd.DataFrame) -> pd.DataFrame:
    open_now = 0
    opens = []
    for _, row in sorted_events.iterrows():
        open_now += int(row["delta"])
        opens.append(open_now)
    out = sorted_events.copy()
    out["open"] = opens
    return out

def peak_segments_from_events(sorted_events: pd.DataFrame, max_open: int):
    ev = sorted_events.copy()
    # ev ya tiene 'open' si vino de sweep; si no, calcúlala:
    if "open" not in ev.columns:
        ev["open"] = ev["delta"].cumsum()
    at_peak = ev.loc[ev["open"] == max_open, ["t", "open"]].reset_index(drop=True)
    segs = []
    if len(at_peak) == 0:
        return segs

    start = None
    for i in range(len(at_peak)):
        if start is None:
            start = at_peak.loc[i, "t"]
        is_last = i == len(at_peak) - 1
        if not is_last:
            gap = at_peak.loc[i + 1, "t"] - at_peak.loc[i, "t"]
            # si hay salto temporal, cerramos segmento
            if gap.total_seconds() > 0:
                end = at_peak.loc[i, "t"]
                mins = round((end - start).total_seconds() / 60.0, 2)
                segs.append({"Start": start, "End": end, "Minutes": mins})
                start = None
        else:
            end = at_peak.loc[i, "t"]
            mins = round((end - start).total_seconds() / 60.0, 2)
            segs.append({"Start": start, "End": end, "Minutes": mins})
            start = None
    return segs

def try_read_kpi_json_strict(csv_path: Path):
    """
    Primero intenta el KPI que coincide EXACTO con el patrón policy_... del CSV.
    Si no existe, cae al último KPI por mtime.
    Devuelve dict con los campos útiles + '_kpi_file'.
    """
    folder = csv_path.parent
    m = re.search(r"policy_([0-9.]+)_([0-9.]+)_H(\d+)", csv_path.name)
    if m:
        tp, sl, H = m.group(1), m.group(2), m.group(3)
        exact = folder / f"kpi_policy_{tp}_{sl}_H{H}.json"
        if exact.exists():
            try:
                data = json.loads(exact.read_text(encoding="utf-8"))
                data["_kpi_file"] = str(exact)
                return data
            except Exception:
                pass

    # Fallback amplio
    cands = []
    for pat in ["kpi_policy_*.json", "kpi_*.json", "*kpi*.json"]:
        cands.extend(folder.glob(pat))
    if not cands:
        return {}
    latest = max(cands, key=lambda p: p.stat().st_mtime)
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
        data["_kpi_file"] = str(latest)
        return data
    except Exception:
        return {}

def main():
    ap = argparse.ArgumentParser(description="Calcular máximo de posiciones simultáneas y capital requerido.")
    ap.add_argument("--csv", required=True, help="Ruta al CSV con entry/exit (o .with_times.csv).")
    ap.add_argument("--out", default="", help="Ruta para exportar resumen diario (CSV). También genera .segments.csv y .timeline.csv")
    ap.add_argument("--per-trade-cash", type=float, default=0.0, help="Monto por operación. Si 0, se intenta leer del KPI JSON del mismo folder.")
    ap.add_argument("--entry-col", default="", help="Override: nombre exacto de la columna de entrada.")
    ap.add_argument("--exit-col", default="", help="Override: nombre exacto de la columna de salida.")
    ap.add_argument("--ties", choices=["open-first", "close-first"], default="open-first",
                    help="Orden en empates (mismo timestamp). 'open-first' = +1 antes que -1; 'close-first' = -1 antes que +1.")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"No existe el CSV: {csv_path}")

    # 1) Cargar CSV y detectar columnas
    df = pd.read_csv(csv_path)
    entry_col, exit_col = detect_cols(df, args.entry_col, args.exit_col)

    # 2) Construir y ordenar eventos según política de empates
    events = build_events(df, entry_col, exit_col)
    events_sorted = sort_events(events, args.ties)

    # 3) Sweep -> timeline con 'open' y máximo simultáneo
    timeline = sweep_max_open(events_sorted)
    max_open = int(timeline["open"].max()) if len(timeline) else 0

    # 4) Diarios
    daily = timeline.groupby(timeline["t"].dt.date)["open"].max().reset_index()
    daily.columns = ["Day", "MaxOpen"]

    # 5) Segmentos pico
    segments = peak_segments_from_events(timeline[["t", "delta", "open"]], max_open)

    # 6) KPI y per_trade_cash
    kpi = try_read_kpi_json_strict(csv_path)
    per_trade_cash = args.per_trade_cash if args.per_trade_cash > 0 else kpi.get("per_trade_cash", None)
    capital_needed = (per_trade_cash * max_open) if per_trade_cash is not None else None

    # 7) Percentiles
    pctls = [50, 75, 90, 95, 99]
    opens_array = timeline["open"].to_numpy() if len(timeline) else np.array([0])
    pvals = np.percentile(opens_array, pctls)

    # ---- Reporte en consola ----
    print(f"CSV: {csv_path}")
    print(f"Columnas detectadas: entry='{entry_col}', exit='{exit_col}'")
    print(f"Empates (ties): {args.ties}")
    if kpi:
        print(f"KPI JSON: {kpi.get('_kpi_file')}")
        if "month" in kpi: print(f" - month: {kpi['month']}")
        if set(("tp_pct", "sl_pct", "horizon_days")).issubset(kpi.keys()):
            print(f" - policy: TP={kpi['tp_pct']*100:.2f}%  SL={kpi['sl_pct']*100:.2f}%  H={kpi['horizon_days']} días")
        if "gross_pnl_sum" in kpi and "net_pnl_sum" in kpi:
            print(f" - PnL: gross={kpi['gross_pnl_sum']:.2f}  net={kpi['net_pnl_sum']:.2f}")
    print(f"Máximo de posiciones simultáneas: {max_open}")
    if per_trade_cash is not None:
        print(f"per_trade_cash: {per_trade_cash}")
        print(f"Capital simultáneo requerido: {capital_needed}")

    print("\n--- Máximos por día ---")
    if len(daily):
        with pd.option_context("display.max_rows", None, "display.max_columns", None):
            print(daily.to_string(index=False))
    else:
        print("(sin datos)")

    print(f"\n--- Tramos en pico (open == {max_open}) ---")
    if segments:
        segdf = pd.DataFrame(segments)
        with pd.option_context("display.max_rows", None, "display.max_columns", None):
            print(segdf.to_string(index=False))
    else:
        print("No hubo tramos de pico.")

    print("\n--- Percentiles de simultaneidad ---")
    for p, v in zip(pctls, pvals):
        v_int = int(np.ceil(v))
        if per_trade_cash is not None:
            cap = v_int * per_trade_cash
            print(f"P{p:02d}: {v:.2f} → ceil {v_int} pos → capital ≈ {cap}")
        else:
            print(f"P{p:02d}: {v:.2f} posiciones")

    # 8) Export opcional
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        daily.to_csv(out_path, index=False)
        seg_path = out_path.with_suffix(".segments.csv")
        tl_path = out_path.with_suffix(".timeline.csv")
        pd.DataFrame(segments).to_csv(seg_path, index=False)
        timeline.to_csv(tl_path, index=False)
        print(f"\nReportes guardados:\n - {out_path}\n - {seg_path}\n - {tl_path}")

if __name__ == "__main__":
    main()
