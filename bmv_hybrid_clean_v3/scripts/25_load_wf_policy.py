# scripts/25_load_wf_policy.py
from __future__ import annotations
import argparse, json, sys, re
from pathlib import Path

def _parse_float(x, default=None):
    if x is None: return default
    if isinstance(x, (int, float)): return float(x)
    s = str(x).strip()
    if s.endswith("%"):
        try: return float(s[:-1].strip())/100.0
        except: return default
    s = s.replace(",", "")
    try: return float(s)
    except: return default

def _parse_int(x, default=None):
    if x is None: return default
    try: return int(float(x))
    except: return default

def _parse_bool(x, default=None):
    if x is None: return default
    if isinstance(x, bool): return x
    s = str(x).strip().lower()
    if s in ("1","true","t","yes","y","si","sí"): return True
    if s in ("0","false","f","no","n"): return False
    return default

def _read_yaml(p: Path):
    try:
        import yaml
    except ImportError:
        print("ERROR: PyYAML no instalado. Instala con: pip install pyyaml", file=sys.stderr)
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def _read_csv(p: Path):
    import csv
    rows = []
    with open(p, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({k.strip(): (v.strip() if isinstance(v,str) else v) for k,v in r.items()})
    return rows

# Sinónimos aceptados
KEYS = {
    "month": ["month","mes","period","periodo","yyyy-mm"],
    "tp": ["tp_pct","tp","take_profit","takeprofit","tp_percent","tp_perc"],
    "sl": ["sl_pct","sl","stop_loss","stoploss","sl_percent","sl_perc"],
    "horizon": ["horizon_days","horizon","days","dias","días","H"],
    "min_abs_y": ["min_abs_y","min_abs_ret","min_abs","min_y_abs","minret"],
    "long_only": ["long_only","longonly","only_long","solo_long"],
    "per_trade_cash": ["per_trade_cash","fixed_cash","cash_per_trade","monto_por_trade","monto_trade"],
    "commission_side": ["commission_side","commission","comision","comisión","fee_side","fee"],
}

def _get_any(d: dict, names: list[str]):
    for k in names:
        if k in d and d[k] not in (None,""):
            return d[k]
    # intenta case-insensitive
    low = {k.lower(): v for k,v in d.items()}
    for k in names:
        if k.lower() in low and low[k.lower()] not in (None,""):
            return low[k.lower()]
    return None

def _list_months_from_container(container):
    months = []
    if isinstance(container, list):
        for r in container:
            if isinstance(r, dict):
                m = _get_any(r, KEYS["month"])
                if m: months.append(str(m).strip())
    elif isinstance(container, dict):
        # caso yaml dict con policies o mapeo por mes
        policies = container.get("policies") or container.get("items") or container.get("policy")
        if isinstance(policies, dict):
            # puede ser { "2025-05": {...}, "2025-06": {...} }
            months.extend([str(k).strip() for k in policies.keys()])
        elif isinstance(policies, list):
            for r in policies:
                if isinstance(r, dict):
                    m = _get_any(r, KEYS["month"])
                    if m: months.append(str(m).strip())
        else:
            # quizá el dict es directamente { "2025-05": {...} }
            for k,v in container.items():
                if isinstance(v, dict) and re.match(r"^\d{4}-\d{2}$", str(k)):
                    months.append(str(k))
    return sorted(set(months))

def _extract_policy_dict(raw, month: str):
    # 1) lista de dicts con columna month
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        rows = raw
        # si no hay columna month y solo hay una fila → úsala
        if all(_get_any(r, KEYS["month"]) in (None,"") for r in rows):
            if len(rows) == 1:
                return rows[0]
            # varias filas sin month → ambigua
            raise ValueError("Se encontraron múltiples filas sin columna 'month'; especifica el mes en el archivo.")
        # buscar match exacto o flexible
        for r in rows:
            m = _get_any(r, KEYS["month"])
            if m and str(m).strip() == month:
                return r
        # intentamos match por inicio (ej. "2025-05-01")
        for r in rows:
            m = _get_any(r, KEYS["month"])
            if m and str(m).strip().startswith(month):
                return r
        raise_lookup_error(raw, month)

    # 2) dict con clave "policies" (lista o dict)
    if isinstance(raw, dict):
        policies = raw.get("policies") or raw.get("items") or raw.get("policy")
        if isinstance(policies, list):
            for r in policies:
                if isinstance(r, dict):
                    m = _get_any(r, KEYS["month"])
                    if m and str(m).strip() == month:
                        return r
            # fallback: única política sin mes
            if len(policies) == 1 and _get_any(policies[0], KEYS["month"]) in (None,""):
                return policies[0]
            raise_lookup_error(policies, month)
        elif isinstance(policies, dict):
            # mapeo por mes: {"2025-05": {...}}
            for k,v in policies.items():
                if str(k).strip() == month:
                    return v if isinstance(v, dict) else {"policy": v}
            raise_lookup_error(policies, month)
        else:
            # 3) dict mapeado por meses directo
            for k,v in raw.items():
                if isinstance(v, dict) and str(k).strip() == month:
                    return v
            # 4) dict con una sola política sin mes
            flat = raw.copy()
            if any(k in flat for k in sum(KEYS.values(), [])):
                return flat
            raise_lookup_error(raw, month)

    raise ValueError("Estructura de archivo no reconocida.")

def raise_lookup_error(container, month):
    avail = _list_months_from_container(container)
    if avail:
        raise ValueError(f"No encontré política para el mes {month}. Meses disponibles: {', '.join(avail)}")
    else:
        raise ValueError(f"No encontré política para el mes {month} y no hay meses listados en el archivo.")

def _maybe_unwrap_nested(d: dict):
    # si viene anidado en 'policy' u otra clave simple
    for k in ("policy","params","values","data"):
        if isinstance(d.get(k), dict):
            return d[k]
    return d

def _cast_policy(d: dict, month: str):
    d = _maybe_unwrap_nested(d)

    tp = _parse_float(_get_any(d, KEYS["tp"]))
    sl = _parse_float(_get_any(d, KEYS["sl"]))
    H  = _parse_int(_get_any(d, KEYS["horizon"]), 4)
    min_abs = _parse_float(_get_any(d, KEYS["min_abs_y"]), 0.0)
    long_only = _parse_bool(_get_any(d, KEYS["long_only"]), True)
    cash = _parse_float(_get_any(d, KEYS["per_trade_cash"]), 1000.0)
    fee  = _parse_float(_get_any(d, KEYS["commission_side"]), 5.0)

    missing = []
    if tp is None: missing.append("tp_pct/tp")
    if sl is None: missing.append("sl_pct/sl")
    if missing:
        # Muestra claves disponibles para diagnóstico
        keys = ", ".join(sorted(d.keys()))
        raise TypeError(f"Faltan campos en la política: {', '.join(missing)}. Claves disponibles: {keys}")

    return {
        "month": month,
        "tp_pct": tp,
        "sl_pct": sl,
        "horizon_days": H,
        "min_abs_y": min_abs,
        "long_only": bool(long_only),
        "per_trade_cash": cash,
        "commission_side": fee,
    }

def main():
    ap = argparse.ArgumentParser(description="Carga una política de wf_box (YAML/CSV) y la exporta normalizada a JSON.")
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--wf-policy", required=True, help="Ruta a YAML/CSV de wf_box (policy_selected_walkforward.*)")
    ap.add_argument("--out-json", required=True, help="Ruta de salida JSON")
    args = ap.parse_args()

    p = Path(args.wf_policy)
    if not p.exists():
        print(f"ERROR: No existe {p}", file=sys.stderr); sys.exit(1)

    if p.suffix.lower() in (".yaml",".yml"):
        raw = _read_yaml(p)
    elif p.suffix.lower()==".csv":
        raw = _read_csv(p)
    else:
        print("ERROR: Formato no soportado (usa .yaml/.yml o .csv)", file=sys.stderr); sys.exit(1)

    try:
        row = _extract_policy_dict(raw, args.month)
        pol = _cast_policy(row, args.month)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    outp = Path(args.out_json)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(pol, f, ensure_ascii=False, indent=2)

    flags = (
        f"--tp-pct {pol['tp_pct']} --sl-pct {pol['sl_pct']} "
        f"--horizon-days {pol['horizon_days']} --min-abs-y {pol['min_abs_y']} "
        f"{'--long-only' if pol['long_only'] else ''} "
        f"--per-trade-cash {pol['per_trade_cash']} --commission-side {pol['commission_side']}"
    ).strip()
    print(flags)

if __name__ == "__main__":
    main()
