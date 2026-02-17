#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auditor de modelos entrenados (.pkl / .joblib)

- Recorre el árbol de carpetas a partir de --root
- Detecta archivos de modelo, intenta cargarlos y extrae metadatos:
  * class_name, is_pipeline, steps, has_predict_proba, n_features_in_ (si existe)
  * sklearn_version detectada
- Empareja métricas cercanas en la misma carpeta (metrics_*.json, metrics_summary.csv)
- Calcula hash SHA-256, tamaño, mtime
- Heurística de "confiabilidad" (0-100) según:
  * carga_ok, has_predict_proba, existe metrics_json, roc_auc >= 0.7, fecha reciente
- Exporta:
  * models_inventory.csv
  * models_inventory.json
  * models_inventory_report.md

Uso:
  python detect_models.py --root . --outdir reports/model_audit --days-fresh 120
"""

import argparse
import os
import sys
from pathlib import Path
import hashlib
import json
import time
from datetime import datetime, timedelta

import pandas as pd

try:
    import joblib
except Exception as e:
    joblib = None

def sha256_of_file(fp, chunk=65536):
    h = hashlib.sha256()
    with open(fp, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()

def find_metric_files(dirpath: Path):
    mets = []
    for p in dirpath.glob("metrics_*.json"):
        mets.append(p)
    # Opcional: metrics_summary.csv
    ms = dirpath / "metrics_summary.csv"
    if ms.exists():
        mets.append(ms)
    return mets

def load_json(fp: Path):
    try:
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def try_load_model(fp: Path):
    info = {
        "load_ok": False,
        "class_name": None,
        "is_pipeline": False,
        "steps": None,
        "has_predict_proba": None,
        "n_features_in": None,
        "sklearn_version": None,
    }
    if joblib is None:
        return info

    try:
        mdl = joblib.load(str(fp))
        info["load_ok"] = True
        cls = mdl.__class__.__name__
        info["class_name"] = cls

        # Detect pipeline
        try:
            from sklearn.pipeline import Pipeline
            info["is_pipeline"] = isinstance(mdl, Pipeline)
            if info["is_pipeline"]:
                try:
                    info["steps"] = [name for name, _ in mdl.steps]
                    # Busca el último estimador para saber si tiene predict_proba
                    last_est = mdl.steps[-1][1]
                    info["has_predict_proba"] = hasattr(last_est, "predict_proba")
                    if hasattr(last_est, "n_features_in_"):
                        info["n_features_in"] = int(getattr(last_est, "n_features_in_"))
                except Exception:
                    pass
            else:
                info["has_predict_proba"] = hasattr(mdl, "predict_proba")
                if hasattr(mdl, "n_features_in_"):
                    info["n_features_in"] = int(getattr(mdl, "n_features_in_"))
        except Exception:
            pass

        # sklearn_version
        try:
            import sklearn
            info["sklearn_version"] = sklearn.__version__
        except Exception:
            pass

    except Exception:
        info["load_ok"] = False

    return info

def parse_metrics_nearby(dirpath: Path):
    """Intenta leer métricas útiles: busca metrics_*.json y toma la mejor roc_auc/f1."""
    best = {
        "metrics_found": False,
        "metric_file": None,
        "roc_auc": None,
        "f1": None,
        "accuracy": None,
        "pr_auc": None,
        "brier": None,
    }
    # Preferimos metrics_*.json sobre summary, porque es por-modelo
    json_files = sorted(dirpath.glob("metrics_*.json"))
    if json_files:
        # Tomar el mejor por roc_auc si existe
        rows = []
        for jf in json_files:
            data = load_json(jf)
            if not isinstance(data, dict):
                continue
            rows.append({
                "file": jf.name,
                "roc_auc": data.get("roc_auc"),
                "f1": data.get("f1"),
                "accuracy": data.get("accuracy"),
                "pr_auc": data.get("pr_auc"),
                "brier": data.get("brier")
            })
        if rows:
            df = pd.DataFrame(rows)
            # Orden por roc_auc, luego f1
            df["_roc"] = df["roc_auc"].fillna(-1)
            df["_f1"] = df["f1"].fillna(-1)
            df = df.sort_values(["_roc","_f1"], ascending=False)
            r = df.iloc[0].to_dict()
            best.update({
                "metrics_found": True,
                "metric_file": r["file"],
                "roc_auc": float(r["roc_auc"]) if r["roc_auc"]==r["roc_auc"] else None,
                "f1": float(r["f1"]) if r["f1"]==r["f1"] else None,
                "accuracy": float(r["accuracy"]) if r["accuracy"]==r["accuracy"] else None,
                "pr_auc": float(r["pr_auc"]) if r["pr_auc"]==r["pr_auc"] else None,
                "brier": float(r["brier"]) if r["brier"]==r["brier"] else None,
            })
            return best

    # Si no hay metrics_*.json, intenta metrics_summary.csv
    ms = dirpath / "metrics_summary.csv"
    if ms.exists():
        try:
            df = pd.read_csv(ms)
            for col in ["roc_auc","f1","accuracy","pr_auc","brier"]:
                if col not in df.columns:
                    df[col] = None
            df["_roc"] = df["roc_auc"].fillna(-1)
            df["_f1"] = df["f1"].fillna(-1)
            df = df.sort_values(["_roc","_f1"], ascending=False)
            r = df.iloc[0].to_dict()
            best.update({
                "metrics_found": True,
                "metric_file": "metrics_summary.csv",
                "roc_auc": float(r["roc_auc"]) if r["roc_auc"]==r["roc_auc"] else None,
                "f1": float(r["f1"]) if r["f1"]==r["f1"] else None,
                "accuracy": float(r["accuracy"]) if r["accuracy"]==r["accuracy"] else None,
                "pr_auc": float(r["pr_auc"]) if r["pr_auc"]==r["pr_auc"] else None,
                "brier": float(r["brier"]) if r["brier"]==r["brier"] else None,
            })
        except Exception:
            pass

    return best

def reliability_score(row, days_fresh: int):
    score = 0
    # 1) Carga correcta
    if row.get("load_ok"):
        score += 35
    # 2) Probas disponibles
    if row.get("has_predict_proba"):
        score += 20
    # 3) Métricas presentes
    if row.get("metrics_found"):
        score += 20
        roc = row.get("roc_auc")
        f1  = row.get("f1")
        if roc is not None and roc >= 0.70:
            score += 10
        if f1 is not None and f1 >= 0.60:
            score += 5
    # 4) Frescura del archivo
    try:
        mtime = datetime.fromisoformat(row["mtime_iso"])
        if datetime.now() - mtime <= timedelta(days=days_fresh):
            score += 10
    except Exception:
        pass
    # 5) Pipeline con pasos (prep + clf) ayuda reproducibilidad
    steps = row.get("steps") or []
    if isinstance(steps, list) and len(steps) >= 2:
        score += 5

    return min(score, 100)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="Carpeta raíz a escanear")
    ap.add_argument("--outdir", default="reports/model_audit", help="Carpeta de salida")
    ap.add_argument("--days-fresh", type=int, default=120, help="Días para considerar un modelo 'reciente'")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    model_paths = []
    for ext in ("*.pkl","*.joblib"):
        model_paths += list(root.rglob(ext))

    rows = []
    for mp in sorted(model_paths):
        try:
            size = mp.stat().st_size
            mtime = mp.stat().st_mtime
            mtime_iso = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
            sha = sha256_of_file(mp)
        except Exception:
            size, mtime_iso, sha = None, None, None

        # Carga y metadatos
        info = try_load_model(mp)

        # Métricas cercanas (misma carpeta)
        mets = parse_metrics_nearby(mp.parent)

        row = {
            "file": str(mp),
            "dir": str(mp.parent),
            "name": mp.name,
            "size_bytes": size,
            "sha256": sha,
            "mtime_iso": mtime_iso,

            "load_ok": info["load_ok"],
            "class_name": info["class_name"],
            "is_pipeline": info["is_pipeline"],
            "steps": info["steps"],
            "has_predict_proba": info["has_predict_proba"],
            "n_features_in": info["n_features_in"],
            "sklearn_version_runtime": info["sklearn_version"],

            "metrics_found": mets["metrics_found"],
            "metrics_source": mets["metric_file"],
            "roc_auc": mets["roc_auc"],
            "f1": mets["f1"],
            "accuracy": mets["accuracy"],
            "pr_auc": mets["pr_auc"],
            "brier": mets["brier"],
        }
        row["reliability_score"] = reliability_score(row, args.days_fresh)

        # Señales/banderas rápidas
        flags = []
        if not row["load_ok"]:
            flags.append("LOAD_FAIL")
        if row["load_ok"] and not row["has_predict_proba"]:
            flags.append("NO_PROBA")
        if not row["metrics_found"]:
            flags.append("NO_METRICS")
        if row["reliability_score"] >= 80:
            flags.append("CERTIFIABLE")
        row["flags"] = ",".join(flags) if flags else ""

        rows.append(row)

    df = pd.DataFrame(rows).sort_values(["reliability_score","roc_auc","f1"], ascending=False)
    csv_path = outdir / "models_inventory.csv"
    json_path = outdir / "models_inventory.json"
    md_path = outdir / "models_inventory_report.md"

    df.to_csv(csv_path, index=False)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(df.to_dict(orient="records"), f, indent=2, ensure_ascii=False)

    # Reporte breve en Markdown
    lines = []
    lines.append(f"# Inventario de modelos ({datetime.now().isoformat(timespec='seconds')})")
    lines.append(f"- Raíz escaneada: `{root}`")
    lines.append(f"- Modelos encontrados: **{len(df)}**")
    top = df.head(10)[["name","class_name","steps","roc_auc","f1","reliability_score","flags","dir"]]
    lines.append("\n## Top 10 por confiabilidad\n")
    lines.append(top.to_markdown(index=False))
    lines.append("\n## Recomendaciones\n")
    lines.append("- Reentrena los marcados con `LOAD_FAIL` o `NO_METRICS` si son candidatos a uso productivo.")
    lines.append("- Prioriza los `CERTIFIABLE` (score ≥ 80) para gatear señales y despliegue.")
    lines.append("- Verifica que las métricas correspondan al **mismo conjunto temporal** que usarás en inferencia (consistencia WF).")
    md = "\n".join(lines)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    print("✅ Auditoría terminada")
    print(f"📄 CSV: {csv_path}")
    print(f"🧾 JSON: {json_path}")
    print(f"📝 Reporte: {md_path}")

if __name__ == "__main__":
    main()
