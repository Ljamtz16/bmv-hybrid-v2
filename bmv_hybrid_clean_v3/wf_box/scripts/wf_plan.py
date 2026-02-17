# -*- coding: utf-8 -*-
"""
wf_plan.py — Automatiza el flujo:
- Enero 2025 (tuning/validación): train_end = --train-end-jan (ej. 2024-12)
- Febrero 2025 (prueba ciega): train_end igual que enero
- Marzo y Abril 2025 (predicción forward): train_end = --train-end-forward (ej. 2025-02)

Novedades:
- Genera/usa policy_selected_walkforward.csv (invoca policy_tuner.py si falta)
- Lector de política robusto (normaliza encabezados y acepta alias)
- Parser de resumen de simulate_trading tolerante a dict con comillas simples (ast.literal_eval)
- Guarda summary_2025Q1Q2.{csv,json} y summary_2025Q1Q2_policy_run.{csv,json}
"""
import os
import argparse
import subprocess
import shlex
import sys
import json
import csv
import re
import ast
import pandas as pd
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
REPORTS = os.path.join(ROOT, "reports")

FORECAST_DIR = os.path.join(REPORTS, "forecast")
POLICY_CSV = os.path.join(FORECAST_DIR, "policy_selected_walkforward.csv")

WALKFORWARD_DEFAULTS = {
    "tp_pct": 0.03,
    "sl_pct": 0.02,
    "horizon_days": 4,
    "min_abs_y": 0.03,
    "long_only": True,
    "capital_initial": 10000,
    "fixed_cash_per_trade": 2000,
    "commission_side": 5.0,
}

REQUIRED_COLS = [
    "month","tp_pct","sl_pct","horizon_days","min_abs_y",
    "long_only","capital_initial","fixed_cash_per_trade","commission_side"
]

MONTHS = ["2025-01","2025-02","2025-03","2025-04"]

# -------------------- utils --------------------
def run_cmd(cmd):
    print(">>", " ".join([shlex.quote(c) for c in cmd]))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT)
    for line in p.stdout:
        print(line, end="")
    rc = p.wait()
    if rc != 0:
        raise RuntimeError(f"Comando falló: {' '.join(cmd)} (rc={rc})")

def run_cmd_capture(cmd):
    print(">>", " ".join([shlex.quote(c) for c in cmd]))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT)
    lines = []
    for line in p.stdout:
        print(line, end="")
        lines.append(line.rstrip("\n"))
    rc = p.wait()
    if rc != 0:
        raise RuntimeError(f"Comando falló: {' '.join(cmd)} (rc={rc})")
    return lines

def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)

# -------------------- pasos previos --------------------
def ensure_kpis(month):
    cmd = [sys.executable, os.path.join(HERE, "kpi_validation_summary.py"), "--month", month]
    try:
        run_cmd(cmd)
    except Exception as e:
        print(f"Advertencia: KPI para {month} no generado: {e}")

def make_forecast(month, train_end):
    run_cmd([sys.executable, os.path.join(HERE, "make_month_forecast.py"),
             "--month", month, "--train-end", train_end])

def collect_month_kpis(month):
    pred_path = os.path.join(REPORTS, "forecast", month, "validation", "predictions.csv")
    if not os.path.exists(pred_path):
        return None
    df = pd.read_csv(pred_path, parse_dates=["Date"])
    if df["y_true"].notna().sum() > 0:
        df2 = df.dropna(subset=["y_true"]).copy()
        err = (df2["y_true"] - df2["y_pred"]).abs()
        mape = (err / df2["y_true"].abs().replace(0, 1e-12)).mean()
        mae = err.mean()
        within = (df2["within_10pct"] == 1).mean()
        return {
            "month": month,
            "rows": int(len(df2)),
            "mae": float(mae),
            "mape": float(mape),
            "within_10pct_rate": float(within),
        }
    else:
        return {"month": month, "rows": 0, "mae": None, "mape": None, "within_10pct_rate": None}

# -------------------- política (robusta) --------------------
def ensure_policy_file(args):
    if os.path.exists(POLICY_CSV):
        print(f"[wf_plan] Usando política existente: {POLICY_CSV}")
        return
    print("[wf_plan] No existe política. Invocando policy_tuner.py para generarla...")
    cmd = [
        sys.executable, os.path.join(HERE, "policy_tuner.py"),
        "--targets", *MONTHS,
        "--back-k", str(args.back_k),
        "--metric", args.metric,
        "--lambda", str(args.lmbda),
    ]
    run_cmd(cmd)
    if not os.path.exists(POLICY_CSV):
        raise FileNotFoundError(f"No se generó {POLICY_CSV}. Revisa policy_tuner.py/permisos.")

def _norm_col(s: str) -> str:
    # minúsculas, quita BOM/espacios, cambia separadores a '_', elimina chars raros
    s = s.replace("\ufeff", "")
    s = s.strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^\w]", "", s)  # solo [a-z0-9_]
    return s

ALIASES = {
    "month": {"month","mes","period","target_month","fecha","target"},
    "tp_pct": {"tp_pct","takeprofit","tp","take_profit"},
    "sl_pct": {"sl_pct","stoploss","sl","stop_loss"},
    "horizon_days": {"horizon_days","horizon","h","days","hold_days"},
    "min_abs_y": {"min_absy","min_abs_y","minabs","min_abs","min_signal","min_y"},
    "long_only": {"long_only","longonly","onlylong"},
    "capital_initial": {"capital_initial","initial_capital","cap0","capital"},
    "fixed_cash_per_trade": {"fixed_cash_per_trade","fixed_cash","cash_per_trade","per_trade_cash"},
    "commission_side": {"commission_side","commission","fee_per_side","fee"},
}

def _build_header_map(fieldnames):
    # normaliza y mapea alias -> nombre canónico
    normalized = [_norm_col(c) for c in (fieldnames or [])]
    print(f"[wf_plan] Columnas detectadas en política: {normalized}")
    header_map = {}
    for canon, aliases in ALIASES.items():
        for i, c in enumerate(normalized):
            if c in { _norm_col(a) for a in aliases }:
                header_map[canon] = fieldnames[i]
                break
    return header_map

def load_policy_csv(path):
    if not os.path.exists(path):
        return {}
    policy = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print(f"[wf_plan] WARNING: {path} sin encabezados.")
            return {}
        header_map = _build_header_map(reader.fieldnames)

        missing = [c for c in REQUIRED_COLS if c not in header_map]
        if missing:
            print(f"[wf_plan] WARNING: faltan columnas (canónicas) en {path}: {missing}")
            return {}

        for row in reader:
            # valor helper
            def get(canon):
                raw_key = header_map[canon]
                v = row.get(raw_key, "")
                return v.strip() if isinstance(v, str) else v

            m = get("month")
            if not m:
                continue
            try:
                tp = float(get("tp_pct"))
                sl = float(get("sl_pct"))
                hz = int(float(get("horizon_days")))
                minabs = float(get("min_abs_y"))
                lo = str(get("long_only")).lower() in ("true","1","t","yes","y")
                cap0 = int(float(get("capital_initial") or WALKFORWARD_DEFAULTS["capital_initial"]))
                fc   = int(float(get("fixed_cash_per_trade") or WALKFORWARD_DEFAULTS["fixed_cash_per_trade"]))
                com  = float(get("commission_side") or WALKFORWARD_DEFAULTS["commission_side"])
            except Exception as e:
                print(f"[wf_plan] WARNING: fila inválida en {path} para month={m}: {e}")
                continue

            if hz <= 0:
                print(f"[wf_plan] WARNING: horizon_days <= 0 ({hz}) para {m}")
            policy[m] = {
                "tp_pct": tp, "sl_pct": sl, "horizon_days": hz, "min_abs_y": minabs,
                "long_only": lo, "capital_initial": cap0, "fixed_cash_per_trade": fc,
                "commission_side": com,
            }
    return policy

def get_policy_for_month(policy_dict, month):
    p = policy_dict.get(month, {})
    res = {**WALKFORWARD_DEFAULTS, **p}
    if res["horizon_days"] <= 0 or res["tp_pct"] >= 1 or res["sl_pct"] >= 1:
        raise ValueError(f"Política inválida para {month}: {res}")
    return res

# -------------------- parser de resumen robusto --------------------
ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")  # quita secuencias ANSI
RESUMEN_LINE_RE = re.compile(r"Simulación terminada\. Resumen:\s*(\{.*\})\s*$")

def _clean_line(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = ANSI_RE.sub("", s).strip()
    return s

def parse_resumen_from_lines(lines):
    # Busca de atrás hacia adelante una línea con el patrón
    for ln in reversed(lines):
        ln2 = _clean_line(ln)
        m = RESUMEN_LINE_RE.search(ln2)
        if not m:
            continue
        blob = m.group(1)  # texto {...} con comillas simples (dict de Python)
        # 1) intento literal_eval (dict Python)
        try:
            data = ast.literal_eval(blob)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        # 2) plan B: intentar JSON (por si alguna versión imprime JSON válido)
        try:
            return json.loads(blob)
        except Exception:
            continue
    return None

def simulate_with_policy(month, p):
    cmd = [
        sys.executable, os.path.join(HERE, "simulate_trading.py"),
        "--month", month,
        "--capital-initial", str(p["capital_initial"]),
        "--fixed-cash", str(p["fixed_cash_per_trade"]),
        "--tp-pct", str(p["tp_pct"]),
        "--sl-pct", str(p["sl_pct"]),
        "--horizon-days", str(p["horizon_days"]),
        "--commission-side", str(p["commission_side"]),
        "--min-abs-y", str(p["min_abs_y"]),
    ]
    if p.get("long_only", True):
        cmd.append("--long-only")
    lines = run_cmd_capture(cmd)
    resumen = parse_resumen_from_lines(lines)
    if resumen is None:
        print(f"[wf_plan] WARNING: no pude parsear el resumen para {month}")
    return resumen

# -------------------- main --------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-end-jan", required=True, help="YYYY-MM (ej. 2024-12)")
    ap.add_argument("--train-end-forward", required=True, help="YYYY-MM (ej. 2025-02)")
    ap.add_argument("--back-k", type=int, default=2, help="ventana back para policy_tuner (si se genera)")
    ap.add_argument("--metric", default="net_rr", help="métrica para policy_tuner (si se genera)")
    ap.add_argument("--lambda", dest="lmbda", type=float, default=0.5, help="lambda para policy_tuner")
    args = ap.parse_args()

    # 1) Forecasts + KPIs
    make_forecast("2025-01", args.train_end_jan); ensure_kpis("2025-01")
    make_forecast("2025-02", args.train_end_jan); ensure_kpis("2025-02")
    for m in ["2025-03", "2025-04"]:
        make_forecast(m, args.train_end_forward); ensure_kpis(m)

    # 2) Resumen KPIs
    rows = []
    for m in MONTHS:
        r = collect_month_kpis(m)
        if r: rows.append(r)
    ensure_dir(FORECAST_DIR)
    if rows:
        pd.DataFrame(rows).to_csv(os.path.join(FORECAST_DIR, "summary_2025Q1Q2.csv"), index=False)
        with open(os.path.join(FORECAST_DIR, "summary_2025Q1Q2.json"), "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
        print("Resumen KPIs guardado en reports/forecast/summary_2025Q1Q2.{csv,json}")
    else:
        print("No hay filas para resumen de KPIs.")

    # 3) Política
    ensure_policy_file(args)
    policy = load_policy_csv(POLICY_CSV)
    if policy:
        print(f"[wf_plan] Usando política existente: {POLICY_CSV}")
    else:
        print("[wf_plan] WARNING: no se pudo cargar la política; se usarán defaults.")

    # 4) Simulación con política mes a mes
    policy_rows = []
    for m in MONTHS:
        p = get_policy_for_month(policy, m)
        print(f"[wf_plan] Aplicando política {p} para {m}")
        resumen = simulate_with_policy(m, p)
        if resumen:
            policy_rows.append({
                "month": resumen.get("month", m),
                "trades": resumen.get("trades"),
                "tp_rate": resumen.get("tp_rate"),
                "sl_rate": resumen.get("sl_rate"),
                "timeout_rate": resumen.get("timeout_rate"),
                "gross_pnl_sum": resumen.get("gross_pnl_sum"),
                "net_pnl_sum": resumen.get("net_pnl_sum"),
                "capital_final": resumen.get("capital_final"),
                "tp_pct": resumen.get("params", {}).get("tp_pct", p["tp_pct"]),
                "sl_pct": resumen.get("params", {}).get("sl_pct", p["sl_pct"]),
                "horizon_days": resumen.get("params", {}).get("horizon_days", p["horizon_days"]),
                "commission_side": resumen.get("params", {}).get("commission_side", p["commission_side"]),
                "min_abs_y": resumen.get("params", {}).get("min_abs_y", p["min_abs_y"]),
                "long_only": resumen.get("params", {}).get("long_only", p["long_only"]),
            })
        else:
            policy_rows.append({
                "month": m, "trades": None, "tp_rate": None, "sl_rate": None, "timeout_rate": None,
                "gross_pnl_sum": None, "net_pnl_sum": None, "capital_final": None,
                "tp_pct": p["tp_pct"], "sl_pct": p["sl_pct"], "horizon_days": p["horizon_days"],
                "commission_side": p["commission_side"], "min_abs_y": p["min_abs_y"], "long_only": p["long_only"]
            })

    # 5) Guardar resumen de simulaciones
    if policy_rows:
        dfp = pd.DataFrame(policy_rows)
        dfp.to_csv(os.path.join(FORECAST_DIR, "summary_2025Q1Q2_policy_run.csv"), index=False)
        with open(os.path.join(FORECAST_DIR, "summary_2025Q1Q2_policy_run.json"), "w", encoding="utf-8") as f:
            json.dump(policy_rows, f, indent=2, ensure_ascii=False)
        print("Resumen de simulaciones (política) guardado en reports/forecast/summary_2025Q1Q2_policy_run.{csv,json}")
    else:
        print("No fue posible compilar el resumen de simulaciones con política.")

if __name__ == "__main__":
    main()
