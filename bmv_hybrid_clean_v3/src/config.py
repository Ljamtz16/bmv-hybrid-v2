# src/config.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List
from pathlib import Path
import yaml

@dataclass
class ExecCfg:
    tp_atr_mult: float = 1.5
    sl_atr_mult: float = 1.0
    commission_pct: float = 0.001
    slippage_pct: float = 0.0002
    max_holding_days: int = 3
    trail_atr_mult: float = 0.0
    trail_activation_atr: float = 0.5
    break_even_atr: float = 1.0

@dataclass
class Cfg:
    # básicos
    tickers: List[str] = field(default_factory=list)
    start: str = "2019-01-01"
    end: str = "2025-02-01"
    session: str = "07:00-14:00"
    data_dir: str = "data"
    reports_dir: str = "reports"

    # anidados
    exec: ExecCfg = field(default_factory=ExecCfg)
    calibration: Dict[str, Any] = field(default_factory=dict)
    evaluation: Dict[str, Any] = field(default_factory=dict)
    models: Dict[str, Any] = field(default_factory=dict)

    # opcionales / nuevos
    aliases: Dict[str, str] = field(default_factory=dict)
    disabled: List[str] = field(default_factory=list)
    signals: Dict[str, Any] = field(default_factory=dict)

    # cualquier otra clave desconocida del YAML
    extra: Dict[str, Any] = field(default_factory=dict)

def _get(d: Dict[str, Any], k: str, default):
    v = d.get(k, default)
    return v if v is not None else default

def load_cfg(path: str | Path) -> Cfg:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de configuración: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # exec → ExecCfg
    ex_raw = raw.get("exec", {}) or {}
    ex = ExecCfg(
        tp_atr_mult=float(_get(ex_raw, "tp_atr_mult", 1.5)),
        sl_atr_mult=float(_get(ex_raw, "sl_atr_mult", 1.0)),
        commission_pct=float(_get(ex_raw, "commission_pct", 0.001)),
        slippage_pct=float(_get(ex_raw, "slippage_pct", 0.0002)),
        max_holding_days=int(_get(ex_raw, "max_holding_days", 3)),
        trail_atr_mult=float(_get(ex_raw, "trail_atr_mult", 0.0)),
        trail_activation_atr=float(_get(ex_raw, "trail_activation_atr", 0.5)),
        break_even_atr=float(_get(ex_raw, "break_even_atr", 1.0)),
    )

    cfg = Cfg(
        tickers=list(raw.get("tickers", []) or []),
        start=str(raw.get("start", "2019-01-01")),
        end=str(raw.get("end", "2025-02-01")),
        session=str(raw.get("session", "07:00-14:00")),
        data_dir=str(raw.get("data_dir", "data")),
        reports_dir=str(raw.get("reports_dir", "reports")),
        exec=ex,
        calibration=dict(raw.get("calibration", {}) or {}),
        evaluation=dict(raw.get("evaluation", {}) or {}),
        models=dict(raw.get("models", {}) or {}),
        aliases=dict(raw.get("aliases", {}) or {}),
        disabled=list(raw.get("disabled", []) or []),
        signals=dict(raw.get("signals", {}) or {}),
    )

    known = {
        "tickers","start","end","session","data_dir","reports_dir",
        "exec","calibration","evaluation","models","aliases","disabled","signals"
    }
    cfg.extra = {k: v for k, v in raw.items() if k not in known}
    return cfg
