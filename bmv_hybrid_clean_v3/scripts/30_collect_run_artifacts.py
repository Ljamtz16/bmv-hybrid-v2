# scripts/30_collect_run_artifacts.py
from __future__ import annotations
import argparse, json, shutil, time
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd
import glob

def now_tag() -> str:
    return time.strftime("%Y%m%d_%H%M%S")

def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def glob_copy(pattern: str, dst_dir: Path) -> List[str]:
    ensure_dir(dst_dir)
    out_paths = []
    for src in glob.glob(pattern):
        src_p = Path(src)
        if src_p.is_file():
            dst = dst_dir / src_p.name
            shutil.copy2(src_p, dst)
            out_paths.append(str(dst))
    return out_paths

def read_json_safe(p: Path) -> Dict[str, Any]:
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def write_json(p: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(p.parent)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def update_runs_index(index_csv: Path, row: Dict[str, Any]) -> None:
    # crea o agrega fila normalizando columnas
    if index_csv.exists():
        df = pd.read_csv(index_csv)
    else:
        df = pd.DataFrame()

    # unifica columnas
    cols = sorted(set(df.columns.tolist()) | set(row.keys()))
    if not df.empty:
        df = df.reindex(columns=cols)
    new_row = {c: row.get(c, None) for c in cols}
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(index_csv, index=False, encoding="utf-8")

def main():
    ap = argparse.ArgumentParser(description="Empaqueta artefactos de una corrida y actualiza runs_index.csv")
    ap.add_argument("--month", required=True, help="Mes del run, ej. 2025-05")
    ap.add_argument("--label", default="", help="Etiqueta opcional del run (ej. baselineA)")
    ap.add_argument("--zip", action="store_true", help="Crear .zip del paquete")
    ap.add_argument("--include-models", action="store_true", help="Copiar carpeta models/")
    ap.add_argument("--include-config", action="store_true", help="Copiar carpeta config/")
    args = ap.parse_args()

    month = args.month
    tag = now_tag()
    run_id = f"{month}_{tag}" + (f"_{args.label}" if args.label else "")
    root = Path(".").resolve()
    runs_dir = ensure_dir(root / "runs")
    out_dir = ensure_dir(runs_dir / run_id)

    # --- Ubicaciones base ---
    fc_dir  = Path("reports/forecast") / month
    val_dir = fc_dir / "validation"

    # 1) Forecast CSVs/JSON/meta
    copies = {"forecast": [], "validation": [], "extras": []}

    # forecast: base/no_gate/with_gate y meta
    for patt in [
        f"{fc_dir}/forecast_{month}_base.csv",
        f"{fc_dir}/forecast_{month}_no_gate.csv",
        f"{fc_dir}/forecast_{month}_with_gate.csv",
        f"{fc_dir}/meta.json",
    ]:
        copies["forecast"] += glob_copy(patt, out_dir / "forecast")

    # 2) Validation CSVs + JSON (incluye kpi_mxn.json)
    for patt in [
        str(val_dir / "validation_trades_*.csv"),
        str(val_dir / "validation_by_ticker_*.csv"),
        str(val_dir / "validation_join_*.csv"),
        str(val_dir / "forecast_vs_real.csv"),
        str(val_dir / "*.json"),                 # <- KPI MXN y otros JSON
    ]:
        copies["validation"] += glob_copy(patt, out_dir / "validation")

    # 3) Últimos features y forecast con returns (si existen)
    copies["extras"] += glob_copy("reports/forecast/latest_forecast_features.csv", out_dir / "extras")
    copies["extras"] += glob_copy("reports/forecast/latest_forecast_with_returns.csv", out_dir / "extras")

    # 4) (Opcional) models/ y config/
    if args.include_models and Path("models").exists():
        shutil.copytree("models", out_dir / "models", dirs_exist_ok=True)
    if args.include_config and Path("config").exists():
        shutil.copytree("config", out_dir / "config", dirs_exist_ok=True)

    # 5) Manifest + KPIs
    summary_kpis_path = val_dir / "summary_kpis.json"
    summary_kpis = read_json_safe(summary_kpis_path)

    kpi_mxn_path = val_dir / "kpi_mxn.json"
    kpi_mxn = read_json_safe(kpi_mxn_path)

    manifest = {
        "run_id": run_id,
        "month": month,
        "label": args.label,
        "timestamp": tag,
        "paths": copies,
        "kpis": {
            "summary": summary_kpis,   # KPIs “clásicos” (Trades, WinRate_%, PnL_sum, MDD, Sharpe, Expectancy…)
            "mxn": kpi_mxn,            # KPIs MXN si existen
        },
    }
    write_json(out_dir / "manifest.json", manifest)

    # 6) Actualizar runs_index.csv con KPIs “clásicos” + MXN (si existen)
    # Campos clásicos esperados
    idx_row: Dict[str, Any] = {
        "run_id": run_id,
        "month": month,
        "label": args.label,
        "timestamp": tag,
    }
    # del summary_kpis.json
    # (usa .get en caso de faltar WinRate_% etc.)
    idx_row.update({
        "Trades": summary_kpis.get("Trades"),
        "WinRate_%": summary_kpis.get("WinRate_%"),
        "PnL_sum": summary_kpis.get("PnL_sum"),
        "MDD": summary_kpis.get("MDD"),
        "Sharpe": summary_kpis.get("Sharpe"),
        "Expectancy": summary_kpis.get("Expectancy"),
    })
    # del kpi_mxn.json (si existe)
    if kpi_mxn:
        idx_row.update({
            "trades_validos_mxn": kpi_mxn.get("trades_validos"),
            "winrate_mxn_%": kpi_mxn.get("winrate_pct"),
            "ganancia_total_mxn": kpi_mxn.get("ganancia_total_mxn"),
            "ganancia_prom_trade_mxn": kpi_mxn.get("ganancia_promedio_por_trade_mxn"),
            "mdd_mxn": kpi_mxn.get("mdd_mxn"),
            "sharpe_mxn": kpi_mxn.get("sharpe_aprox"),
        })

    update_runs_index(runs_dir / "runs_index.csv", idx_row)

    # 7) ZIP (opcional)
    if args.zip:
        zip_path = shutil.make_archive(str(out_dir), "zip", root_dir=out_dir)
        print(f"📦 ZIP creado: {zip_path}")

    print(f"✅ Run empaquetado en: {out_dir}")
    print(f"📝 Manifest: {out_dir/'manifest.json'}")
    print(f"📚 runs_index.csv actualizado en: {runs_dir/'runs_index.csv'}")

if __name__ == "__main__":
    main()
    