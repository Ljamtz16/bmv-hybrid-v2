import argparse
from pathlib import Path
import pandas as pd
import numpy as np

def parse_args():
    ap = argparse.ArgumentParser(description="Enforce MAX_OPEN verdadero sobre el timeline (usa entry_time/exit_time).")
    ap.add_argument("--in", dest="src", required=True, help="CSV .with_times con entry_time/exit_time")
    ap.add_argument("--out", dest="dst", required=True, help="CSV filtrado que respeta MAX_OPEN")
    ap.add_argument("--max-open", type=int, required=True, help="Tope global de posiciones simultáneas")
    ap.add_argument("--per-trade-cash", type=float, default=0.0, help="(Opcional) solo informativo en logs")
    ap.add_argument("--score-col", default="", help="Columna de score para priorizar (ej. 'score', 'ev'). Si vacío, usa prob*ev si existen.")
    ap.add_argument("--ties", choices=["open-first","close-first"], default="close-first",
                    help="Orden en empates de timestamp (recomendado close-first para estimación de capital).")
    return ap.parse_args()

def compute_score_row(r, score_col=""):
    if score_col and score_col in r and pd.notna(r[score_col]):
        return float(r[score_col])
    # fallback a prob*ev si existen
    prob = float(r["prob"]) if "prob" in r and pd.notna(r["prob"]) else 0.0
    ev   = float(r["ev"])   if "ev"   in r and pd.notna(r["ev"])   else 1.0
    return prob * ev

def main():
    args = parse_args()
    src = Path(args.src); dst = Path(args.dst)

    df = pd.read_csv(src)
    need = {"entry_time","exit_time"}
    if not need.issubset(df.columns):
        raise SystemExit(f"Faltan columnas {need} en {src}. ¿Pasaste antes por build_entry_exit_from_policy.py?")

    # Score
    if args.score_col and args.score_col in df.columns:
        df["_score"] = pd.to_numeric(df[args.score_col], errors="coerce").fillna(0.0)
    else:
        df["_score"] = [compute_score_row(r, args.score_col) for _, r in df.iterrows()]

    # Orden temporal + política de empates:
    #   close-first -> cierres (-1) antes de aperturas (+1) en el mismo timestamp (más conservador)
    #   open-first  -> aperturas primero (más exigente en capital)
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"]  = pd.to_datetime(df["exit_time"])

    opens  = df[["entry_time","_score"]].copy()
    opens.rename(columns={"entry_time":"t"}, inplace=True)
    opens["delta"]  = 1

    closes = df[["exit_time","_score"]].copy()
    closes.rename(columns={"exit_time":"t"}, inplace=True)
    closes["delta"] = -1

    events = pd.concat([opens, closes], ignore_index=True)
    ascending = [True, True] if args.ties == "close-first" else [True, False]
    events = events.sort_values(["t","delta"], ascending=ascending).reset_index(drop=True)

    # Para poder decidir qué abrir cuando hay conflicto, necesitamos los trades por timestamp
    # Reconstruimos un índice por trade:
    df = df.reset_index(drop=False).rename(columns={"index":"_trade_id"})
    # mapeo entry/exit -> trade_id
    entry_map = dict(zip(df["entry_time"], df["_trade_id"]))
    exit_map  = dict(zip(df["exit_time"],  df["_trade_id"]))

    # Pero timestamps pueden repetirse -> hacemos listas por timestamp
    from collections import defaultdict
    entries_at = defaultdict(list)
    exits_at   = defaultdict(list)
    for i, r in df.iterrows():
        entries_at[r["entry_time"]].append(int(r["_trade_id"]))
        exits_at[r["exit_time"]].append(int(r["_trade_id"]))

    # Estado de abiertos y selección final
    open_set = set()
    keep_ids = set()

    # Necesitamos decidir orden cuando múltiples aperturas caen en el mismo instante y romperían MAX_OPEN:
    # -> priorizamos por score descendente
    by_id_score = dict(zip(df["_trade_id"], df["_score"]))

    # Recorremos todos los timestamps únicos en orden:
    times = sorted(set(events["t"].dropna().tolist()))
    for t in times:
        # 1) procesar cierres
        for tid in exits_at.get(t, []):
            if tid in open_set:
                open_set.remove(tid)
        # 2) procesar aperturas
        new_entries = entries_at.get(t, [])
        if not new_entries:
            continue
        # ordenar por score desc
        new_entries = sorted(new_entries, key=lambda tid: by_id_score.get(tid, 0.0), reverse=True)
        for tid in new_entries:
            if len(open_set) < args.max_open:
                open_set.add(tid)
                keep_ids.add(tid)
            else:
                # no se puede abrir -> descartado
                pass

    out = df[df["_trade_id"].isin(keep_ids)].drop(columns=["_trade_id","_score"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dst, index=False)

    print(f"✅ Enforced MAX_OPEN={args.max_open}. Guardado: {dst} (filas={len(out)})")
    if args.per_trade_cash > 0:
        print(f"ℹ Capital pico teórico ≤ {args.max_open} × {args.per_trade_cash} = {args.max_open * args.per_trade_cash:.2f}")

if __name__ == "__main__":
    main()

