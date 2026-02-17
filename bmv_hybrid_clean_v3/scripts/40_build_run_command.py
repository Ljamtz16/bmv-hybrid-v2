# scripts/40_build_run_command.py
from __future__ import annotations
import os, sys, shlex
from pathlib import Path

def is_windows() -> bool:
    return os.name == "nt"

def default_python() -> str:
    if is_windows():
        p = Path(".venv") / "Scripts" / "python.exe"
    else:
        p = Path(".venv") / "bin" / "python"
    return str(p if p.exists() else sys.executable)

def ask(msg: str, default: str | None = None) -> str:
    d = f" [{default}]" if default is not None else ""
    val = input(f"{msg}{d}: ").strip()
    return val if val else (default or "")

def ask_yesno(msg: str, default: bool=True) -> bool:
    d = " [Y/n]" if default else " [y/N]"
    val = input(f"{msg}{d}: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes", "s", "si", "sí")

def tokens_to_list(s: str) -> list[str]:
    s = (s or "").strip()
    if not s: return []
    return [t for t in s.replace(",", " ").split() if t]

def horizons_to_list(s: str) -> list[int]:
    out = []
    for t in tokens_to_list(s):
        try:
            v = int(t)
            if v>0: out.append(v)
        except: pass
    return sorted(set(out))

def build_cmd(
    py: str,
    cfg: str,
    months: list[str],
    horizons: list[int],
    target_kind: str,
    forecast_month: str,
    infer_h: int | None,
    rank_topn: int,
    date_col: str,
    price_col: str,
    ticker_col: str,
    skip_download: bool,
    skip_features: bool,
    skip_prob_train: bool,
    skip_return_train: bool,
    validate_only: bool,
    predict_only: bool,
    kpi_skip: bool,
    kpi_sizing: str,
    kpi_fixed_cash: float,
    kpi_fixed_shares: int,
    kpi_risk_pct: float,
    kpi_commission: float,
    collect_run: bool,
    collect_label: str,
    collect_zip: bool,
    collect_include_models: bool,
    collect_include_config: bool,
):
    cmd = [py, "scripts/run_pipeline.py"]

    # Config
    if cfg:
        cmd += ["--cfg", cfg]

    # Entrenamiento y forecast
    if months:
        cmd += ["--months", *months]
    if horizons:
        cmd += ["--return-horizons", ",".join(str(h) for h in horizons)]
    if target_kind:
        cmd += ["--target-kind", target_kind]
    if forecast_month:
        cmd += ["--forecast-month", forecast_month]
    if infer_h:
        cmd += ["--infer-h", str(infer_h)]
    if rank_topn and rank_topn>0:
        cmd += ["--rank-topn", str(rank_topn)]

    # Columnas 20b
    if date_col:   cmd += ["--date-col", date_col]
    if price_col:  cmd += ["--price-col", price_col]
    if ticker_col: cmd += ["--ticker-col", ticker_col]

    # Flags de flujo
    if skip_download:     cmd += ["--skip-download"]
    if skip_features:     cmd += ["--skip-features"]
    if skip_prob_train:   cmd += ["--skip-prob-train"]
    if skip_return_train: cmd += ["--skip-return-train"]
    if validate_only:     cmd += ["--validate-only"]
    if predict_only:      cmd += ["--predict-only"]

    # KPI MXN (si el pipeline los soporta; si kpi_skip -> no se añaden)
    if not kpi_skip:
        cmd += [
            "--kpi-sizing", kpi_sizing,
            "--kpi-fixed-cash", str(kpi_fixed_cash),
            "--kpi-fixed-shares", str(kpi_fixed_shares),
            "--kpi-risk-pct", str(kpi_risk_pct),
            "--kpi-commission", str(kpi_commission),
        ]
    else:
        cmd += ["--kpi-skip"]

    # Empaquetado de corrida (colección de artefactos)
    if collect_run:
        cmd += ["--collect-run"]
        if collect_label:
            cmd += ["--label", collect_label]
        if collect_zip:
            cmd += ["--zip"]
        if collect_include_models:
            cmd += ["--include-models"]
        if collect_include_config:
            cmd += ["--include-config"]

    return cmd

def quote_ps(arg: str) -> str:
    # En PowerShell las comillas dobles suelen bastar; escapamos dobles
    if any(c.isspace() for c in arg) or any(c in arg for c in ('"', "'", "`")):
        return f'"{arg.replace("\"", "\\\"")}"'
    return arg

def main():
    print("=== Asistente para construir el comando de run_pipeline.py ===\n")

    # Python
    py = ask("Ruta a Python", default_python())

    # CFG
    cfg = ask("Ruta a config YAML (o vacío para default)", "")

    # Meses de entrenamiento
    months_raw = ask("Meses para entrenamiento (YYYY-MM separados por espacio/comas)", "2025-03 2025-04 2025-05")
    months = tokens_to_list(months_raw)

    # Forecast
    forecast_month = ask("Mes a pronosticar (YYYY-MM)", "2025-06")

    # Horizontes
    horizons = horizons_to_list(ask("Horizontes retorno (p.e. 3,5,10)", "5"))
    infer_h = None
    if horizons:
        ih_raw = ask(f"H a aplicar en forecast (default {horizons[0]})", str(horizons[0]))
        try:
            infer_h = int(ih_raw)
        except:
            infer_h = horizons[0]

    # Tipo de target
    target_kind = ask("Target de retornos (raw/volnorm)", "raw").strip().lower()
    if target_kind not in ("raw", "volnorm"):
        target_kind = "raw"

    # Rank
    rank_topn = 0
    try:
        rank_topn = int(ask("TOP-N para ranking por EV (0 = no rankear)", "0"))
    except:
        rank_topn = 0

    # Columnas para 20b
    date_col   = ask("Columna fecha para 20b", "entry_date")
    price_col  = ask("Columna precio para 20b", "entry_price")
    ticker_col = ask("Columna ticker para 20b", "ticker")

    # Flags de flujo
    skip_download     = ask_yesno("¿Saltar descarga de datos (01)?", False)
    skip_features     = ask_yesno("¿Saltar features (02)?", False)
    skip_prob_train   = ask_yesno("¿Saltar entrenamiento prob (21)?", False)
    skip_return_train = ask_yesno("¿Saltar 20b+22 (targets y modelos retorno)?", False)
    validate_only     = ask_yesno("¿Solo validar (requiere forecast previo)?", False)
    predict_only      = ask_yesno("¿Solo predecir (sin validar)?", False)

    # KPI MXN
    kpi_skip = not ask_yesno("¿Calcular KPI MXN al final?", True)
    kpi_sizing = ask("Sizing (fixed_cash/fixed_shares/percent_risk)", "percent_risk")
    try:
        kpi_fixed_cash = float(ask("fixed_cash", "200000"))
    except:
        kpi_fixed_cash = 200000.0
    try:
        kpi_fixed_shares = int(ask("fixed_shares", "100"))
    except:
        kpi_fixed_shares = 100
    try:
        kpi_risk_pct = float(ask("risk_pct (0-1)", "0.01"))
    except:
        kpi_risk_pct = 0.01
    try:
        kpi_commission = float(ask("Comisión por trade (MXN)", "5"))
    except:
        kpi_commission = 5.0

    # Empaquetado / recolección de artefactos
    collect_run = ask_yesno("¿Empaquetar la corrida al finalizar (runs/…)?", False)
    collect_label = ask("Etiqueta para la corrida (label)", "ev_top20") if collect_run else ""
    collect_zip = ask_yesno("¿Crear .zip del run?", True) if collect_run else False
    collect_include_models = ask_yesno("¿Incluir modelos en el paquete?", False) if collect_run else False
    collect_include_config = ask_yesno("¿Incluir config en el paquete?", True) if collect_run else False

    # Construir comando
    cmd = build_cmd(
        py=py,
        cfg=cfg,
        months=months,
        horizons=horizons,
        target_kind=target_kind,
        forecast_month=forecast_month,
        infer_h=infer_h,
        rank_topn=rank_topn,
        date_col=date_col,
        price_col=price_col,
        ticker_col=ticker_col,
        skip_download=skip_download,
        skip_features=skip_features,
        skip_prob_train=skip_prob_train,
        skip_return_train=skip_return_train,
        validate_only=validate_only,
        predict_only=predict_only,
        kpi_skip=kpi_skip,
        kpi_sizing=kpi_sizing,
        kpi_fixed_cash=kpi_fixed_cash,
        kpi_fixed_shares=kpi_fixed_shares,
        kpi_risk_pct=kpi_risk_pct,
        kpi_commission=kpi_commission,
        collect_run=collect_run,
        collect_label=collect_label,
        collect_zip=collect_zip,
        collect_include_models=collect_include_models,
        collect_include_config=collect_include_config,
    )

    # Salidas listas para copiar/pegar
    print("\n===== Comando listo (PowerShell/Windows) =====")
    ps = " ".join(quote_ps(str(c)) for c in cmd)
    print(ps)

    print("\n===== Comando listo (bash/Linux/macOS) =====")
    bash = " ".join(shlex.quote(str(c)) for c in cmd)
    print(bash)

    # Además, mostramos un resumen útil
    print("\n===== Resumen =====")
    print(f"Python:         {py}")
    print(f"CFG:            {cfg or '(default)'}")
    print(f"Meses train:    {months or '(ninguno)'}")
    print(f"Forecast mes:   {forecast_month or '(no definido)'}")
    print(f"Horizontes:     {horizons or '(ninguno)'} (infer_h={infer_h})")
    print(f"Target kind:    {target_kind}")
    print(f"Rank TOP-N:     {rank_topn}")
    print(f"20b columns:    date={date_col} | price={price_col} | ticker={ticker_col}")
    print(f"Flags:          skip_download={skip_download}, skip_features={skip_features}, "
          f"skip_prob_train={skip_prob_train}, skip_return_train={skip_return_train}, "
          f"predict_only={predict_only}, validate_only={validate_only}")
    print(f"KPI MXN:        skip={kpi_skip}, sizing={kpi_sizing}, fixed_cash={kpi_fixed_cash}, "
          f"fixed_shares={kpi_fixed_shares}, risk_pct={kpi_risk_pct}, commission={kpi_commission}")
    print(f"Collect run:    {collect_run} (label={collect_label}, zip={collect_zip}, "
          f"include_models={collect_include_models}, include_config={collect_include_config})")

if __name__ == "__main__":
    main()
