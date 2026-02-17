# src/config/__init__.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import yaml
import pandas as pd

@dataclass
class Config:
    tickers: list[str]
    start: str
    end: str
    data_dir: str
    reports_dir: str | None = None
    session: str | None = None
    aliases: dict | None = None
    disabled: list[str] | None = None

    # Model paths (opcionales)
    rf_path: str | None = None
    svm_path: str | None = None
    lstm_path: str | None = None

def _resolve_repo_root() -> Path:
    # .../bmv_hybrid_clean_v3/bmv_hybrid_clean_v3/src/config/__init__.py -> repo_root = parents[3]
    # (src/config -> src -> project-root)
    return Path(__file__).resolve().parents[2]

def load_cfg(rel_yaml: str = "config/base.yaml") -> Config:
    repo_root = _resolve_repo_root()
    cfg_path = (repo_root / rel_yaml).resolve()
    if not cfg_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de configuración: {cfg_path}")

    with cfg_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # Campos obligatorios
    tickers = list(raw.get("tickers", []))
    if not tickers:
        raise ValueError("La lista 'tickers' en config/base.yaml está vacía o no existe.")

    # Opcionales
    data_dir = raw.get("data_dir", "data")
    reports_dir = raw.get("reports_dir")
    session = raw.get("session")
    aliases = raw.get("aliases") or {}
    disabled = raw.get("disabled") or []

    # Model paths (si existen en yaml)
    models = raw.get("models", {}) or {}
    rf_path = models.get("rf_path")
    svm_path = models.get("svm_path")
    lstm_path = models.get("lstm_path")

    # Aplicar disabled
    if disabled:
        tickers = [t for t in tickers if t not in set(disabled)]

    # Aplicar aliases (para etapas posteriores si quieres reconciliar nombres)
    # Aquí devolvemos los tickers originales; el loader podrá aplicar alias efectivos si es necesario.

    return Config(
        tickers=tickers,
        start=str(raw.get("start", "2019-01-01")),
        end=str(raw.get("end", pd.Timestamp.utcnow().strftime("%Y-%m-%d"))),
        data_dir=str(data_dir),
        reports_dir=reports_dir,
        session=session,
        aliases=aliases,
        disabled=disabled,
        rf_path=rf_path,
        svm_path=svm_path,
        lstm_path=lstm_path,
    )
