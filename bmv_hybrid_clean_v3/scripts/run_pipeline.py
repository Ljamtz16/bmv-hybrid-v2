# scripts/run_pipeline.py
from __future__ import annotations
import string
import argparse, os, sys, subprocess, shlex
from pathlib import Path

# ---------- utilidades ----------
def is_windows() -> bool:
    return os.name == "nt"

def default_python() -> str:
    if is_windows():
        p = Path(".venv") / "Scripts" / "python.exe"
    else:
        p = Path(".venv") / "bin" / "python"
    return str(p if p.exists() else sys.executable)

def ensure_pythonpath(env: dict) -> None:
    """Asegura que el root del proyecto esté en PYTHONPATH para poder importar src.*"""
    root = str(Path(__file__).resolve().parents[1])
    cur = env.get("PYTHONPATH", "")
    parts = [p for p in cur.split(os.pathsep) if p]
    if root not in parts:
        parts.insert(0, root)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    print(f"• PYTHONPATH={env['PYTHONPATH']}")

def run(cmd, title: str="", env=None):
    if isinstance(cmd, str):
        printable = cmd
    else:
        printable = " ".join(shlex.quote(str(c)) for c in cmd)
    print(f"\n▶ {title or 'Run'}:\n{printable}")
    proc = subprocess.run(cmd, env=env)
    if proc.returncode != 0:
        raise SystemExit(f"❌ Falló: {title} (code {proc.returncode})")

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

def suggest_tp_sl(trades_df):
    """
    Sugiere valores óptimos de tp/sl multiplicadores usando el historial de trades.
    """
    import numpy as np
    best_score = -np.inf
    best_tp, best_sl = None, None
    for tp in np.arange(1.0, 2.5, 0.1):
        for sl in np.arange(0.5, 1.5, 0.1):
            wins = (trades_df['pnl'] > 0).sum()
            total = len(trades_df)
            score = trades_df['pnl'].sum() + wins * 10  # Ejemplo: pondera aciertos
            if score > best_score:
                best_score = score
                best_tp, best_sl = tp, sl
    return best_tp, best_sl

def get_kpi_preset(preset):
    presets = {
        "paper": dict(kpi_sizing="fixed_cash", kpi_fixed_cash=10000, kpi_fixed_shares=100, kpi_risk_pct=0.01, kpi_commission=0.0),
        "realista_bajo": dict(kpi_sizing="percent_risk", kpi_fixed_cash=50000, kpi_fixed_shares=100, kpi_risk_pct=0.005, kpi_commission=5.0),
        "realista_alto": dict(kpi_sizing="percent_risk", kpi_fixed_cash=200000, kpi_fixed_shares=100, kpi_risk_pct=0.01, kpi_commission=10.0)
    }
    return presets.get(preset, presets["paper"])

# ---------- flujo ----------
def main():
    ap = argparse.ArgumentParser(
        description="Orquestador interactivo/no-interactivo para reentrenar, predecir, validar y empaquetar corridas."
    )
    # No-interactivo (si los pasas, no pregunta)
    ap.add_argument("--cfg", default="", help="Ruta config YAML (opcional), p.ej. config/base.yaml")
    ap.add_argument("--months", nargs="+", help="Meses para training (YYYY-MM ...). Ej: 2025-03 2025-04 2025-05")
    ap.add_argument("--return-horizons", default="5", help="Horizontes de retorno. Ej: 3,5,10")
    ap.add_argument("--target-kind", choices=["raw","volnorm"], default="raw")
    ap.add_argument("--forecast-month", help="Mes a pronosticar (YYYY-MM), ej 2025-09")
    ap.add_argument("--infer-h", type=int, help="H a aplicar en forecast (si no se indica, toma el primero de --return-horizons)")
    ap.add_argument("--rank-topn", type=int, default=0, help="TOP-N para rankear señales por EV (0 = no rankear)")

    # Columnas/20b
    ap.add_argument("--date-col", default="entry_date", help="Columna fecha para 20b (default: entry_date)")
    ap.add_argument("--price-col", default="entry_price", help="Columna precio para 20b (default: entry_price)")
    ap.add_argument("--ticker-col", default="ticker", help="Columna ticker para 20b (default: ticker)")

    # Skips
    ap.add_argument("--skip-download", action="store_true", help="Saltar 01_download_data.py")
    ap.add_argument("--skip-features", action="store_true", help="Saltar 02_build_features.py")
    ap.add_argument("--skip-prob-train", action="store_true", help="Saltar 21_train_prob_model.py")
    ap.add_argument("--skip-return-train", action="store_true", help="Saltar 20b + 22 (targets y modelos de retorno)")
    ap.add_argument("--validate-only", action="store_true", help="Solo validar el mes (requiere forecast previo)")
    ap.add_argument("--predict-only", action="store_true", help="Solo predecir (no validar)")

    # KPI MXN
    ap.add_argument("--skip-kpi-mxn", action="store_true", help="No calcular KPI en MXN al final")
    ap.add_argument("--kpi-sizing", choices=["fixed_shares","fixed_cash","percent_risk"], default="fixed_cash")
    ap.add_argument("--kpi-fixed-shares", type=int, default=100)
    ap.add_argument("--kpi-fixed-cash", type=float, default=10000.0, help="Efectivo por trade o capital_total en percent_risk")
    ap.add_argument("--kpi-risk-pct", type=float, default=0.01, help="Riesgo % por trade si sizing=percent_risk (0.01 = 1%)")
    ap.add_argument("--kpi-commission", type=float, default=0.0, help="Comisión MXN por trade")
    ap.add_argument("--kpi-mxn-preset", choices=["paper","realista_bajo","realista_alto"], default=None, help="Preset de sizing para KPIs MXN")
    # Empaquetado
    ap.add_argument("--collect-run", action="store_true", help="Empaquetar artefactos de la corrida con 30_collect_run_artifacts.py")
    ap.add_argument("--label", default="", help="Etiqueta para la carpeta del run (ej. baselineA)")
    ap.add_argument("--zip", dest="mkzip", action="store_true", help="Crear .zip del run")
    ap.add_argument("--include-models", action="store_true", help="Incluir modelos en el paquete")
    ap.add_argument("--include-config", action="store_true", help="Incluir config en el paquete")

    ap.add_argument("--python", default=default_python(), help="Ruta al Python a usar (default: venv o actual)")
    ap.add_argument("--min-prob", type=float, default=0.0, help="Umbral mínimo de probabilidad para filtrar señales")
    # Backtest extendido
    ap.add_argument("--backtest-start", default=None, help="Fecha inicio para backtest extendido (YYYY-MM-DD)")
    ap.add_argument("--backtest-end", default=None, help="Fecha fin para backtest extendido (YYYY-MM-DD)")
    args = ap.parse_args()

    py = args.python
    env = os.environ.copy()
    ensure_pythonpath(env)
    if args.cfg:
        env["CFG"] = args.cfg
        print(f"• CFG={args.cfg}")

    # ---------- modo interactivo si faltan datos ----------
    if not args.months and not args.validate_only:
        ms = ask("Meses para entrenamiento (ej. 2025-03 2025-04 2025-05)", "2025-03 2025-04 2025-05")
        args.months = ms.split()

    if not args.forecast_month:
        args.forecast_month = ask("Mes a pronosticar (YYYY-MM)", "2025-06")

    if not args.return_horizons:
        args.return_horizons = ask("Horizontes retorno (coma o espacio, ej. 3,5,10)", "5")

    # normaliza horizons → lista de enteros
    horizons = []
    for token in args.return_horizons.replace(",", " ").split():
        try:
            h = int(token)
            if h > 0:
                horizons.append(h)
        except:
            pass
    if not horizons:
        raise SystemExit("Debes indicar al menos un horizonte válido (>0).")
    horizons = sorted(set(horizons))
    infer_h = args.infer_h if args.infer_h else horizons[0]

    print("\n===== Resumen de parámetros =====")
    print(f"Python:         {py}")
    print(f"CFG:            {args.cfg or '(default)'}")
    print(f"Meses train:    {args.months}")
    print(f"Forecast mes:   {args.forecast_month}")
    print(f"Horizontes:     {horizons} (infer_h={infer_h})")
    print(f"Target kind:    {args.target_kind}")
    print(f"Rank TOP-N:     {args.rank_topn}")
    print(f"20b columns:    date={args.date_col} | price={args.price_col} | ticker={args.ticker_col}")
    print(f"KPI MXN:        sizing={args.kpi-string if hasattr(args,'kpi-sizing') else args.kpi_sizing}, "
          f"fixed_cash={args.kpi_fixed_cash}, fixed_shares={args.kpi_fixed_shares}, "
          f"risk_pct={args.kpi_risk_pct}, commission={args.kpi_commission}, skip={args.skip_kpi_mxn}")
    print(f"Collect run:    {args.collect_run} (label={args.label}, zip={args.mkzip}, "
          f"include_models={args.include_models}, include_config={args.include_config})")
    print(f"Flags:          skip_download={args.skip_download}, skip_features={args.skip_features}, "
          f"skip_prob_train={args.skip_prob_train}, skip_return_train={args.skip_return_train}, "
          f"predict_only={args.predict_only}, validate_only={args.validate_only}")
    if not ask_yesno("¿Continuar con la ejecución?", True):
        raise SystemExit("Cancelado por usuario.")

    # Si hay trades previos, sugerir tp/sl óptimos
    try:
        import pandas as pd
        trades_path = "reports/forecast/latest_forecast_trades.csv"
        if os.path.exists(trades_path):
            df_trades = pd.read_csv(trades_path)
            tp_opt, sl_opt = suggest_tp_sl(df_trades)
            print(f"Sugerencia: tp_atr_mult={tp_opt:.2f}, sl_atr_mult={sl_opt:.2f} (basado en trades previos)")
    except Exception as e:
        print(f"No se pudo sugerir tp/sl óptimos: {e}")

    # ---------- A) Datos y features ----------
    if not args.skip_download and not args.validate_only:
        run([py, "scripts/01_download_data.py"], "01) Descargar datos", env)

    if not args.skip_features and not args.validate_only:
        run([py, "scripts/02_build_features.py"], "02) Construir features", env)

    # ---------- B) Training ----------
    if not args.validate_only:
        if args.months:
            cmd20 = [py, "scripts/20_prepare_training_dataset.py", "--months", *args.months, "--out", "reports/forecast/training_dataset.csv"]
            run(cmd20, "20) Preparar training_dataset.csv", env)

        if not args.skip_prob_train:
            run([py, "scripts/21_train_prob_model.py", "--data", "reports/forecast/training_dataset.csv"],
                "21) Entrenar modelo de probabilidad (clasificación)", env)

        if not args.skip_return_train:
            cmd20b = [
                py, "scripts/20b_add_return_targets.py",
                "--data", "reports/forecast/training_dataset.csv",
                "--out",  "reports/forecast/training_dataset_w_returns.csv",
                "--horizons", ",".join(str(h) for h in horizons),
                "--date-col", args.date_col,
                "--price-col", args.price_col,
                "--ticker-col", args.ticker_col,
            ]
            run(cmd20b, "20b) Generar targets de retorno multi-H", env)

            cmd22 = [
                py, "scripts/22_train_return_model.py",
                "--data", "reports/forecast/training_dataset_w_returns.csv",
                "--horizons", ",".join(str(h) for h in horizons),
                "--kind", args.target_kind,
            ]
            run(cmd22, "22) Entrenar modelos de retorno", env)

    # ---------- C) Forecast + Returns + Rank + Validación ----------
    # Pasar min_prob a los scripts de señales y forecast
    min_prob = args.min_prob
    if args.validate_only:
        run([py, "scripts/12_forecast_and_validate.py",
             "--month", args.forecast_month,
             "--validate-only",
             "--min-prob", str(min_prob)], "12) Validar mes (solo)", env)
    else:
        cmd12 = [
            py, "scripts/12_forecast_and_validate.py",
            "--month", args.forecast_month,
            "--use-return",
            "--infer-h", str(infer_h),
            "--features-csv", "reports/forecast/latest_forecast_features.csv",
            "--min-prob", str(min_prob)
        ]
        if args.rank_topn and args.rank_topn > 0:
            cmd12 += ["--rank-topn", str(args.rank_topn)]
        if args.predict_only:
            cmd12 += ["--predict-only"]
        run(cmd12, "12) Forecast mensual + returns (+rank) [+validación si no --predict-only]", env)

    # ---------- D) KPI MXN (si hay validación hecha) ----------
    # Solo tiene sentido si NO es predict-only (o si validate-only)
    did_validation = (args.validate_only or not args.predict_only)
    if did_validation and not args.skip_kpi_mxn:
        val_dir = Path("reports/forecast") / args.forecast_month / "validation"
        csv_trades = val_dir / "validation_trades_auto.csv"
        csv_join   = val_dir / "validation_join_auto.csv"
        out_json   = val_dir / "kpi_mxn.json"

        if csv_trades.exists():
            cmd_kpi = [
                py, "scripts/kpi_validation_summary_mxn.py",
                "--csv", str(csv_trades),
                "--fallback-join", str(csv_join),
                "--sizing", args.kpi_sizing,
                "--fixed-cash", str(args.kpi_fixed_cash),
                "--fixed-shares", str(args.kpi_fixed_shares),
                "--risk-pct", str(args.kpi_risk_pct),
                    "--commission", str(args.kpi_commission),
                "--out-json", str(out_json),
            ]
            run(cmd_kpi, "KPI MXN: calcular y guardar kpi_mxn.json", env)
        else:
            print(f"⚠️ No se encontró {csv_trades}; omito KPI MXN.")

    # ---------- E) Empaquetar corrida (opcional) ----------
    if args.collect_run:
        cmd_collect = [
            py, "scripts/30_collect_run_artifacts.py",
            "--month", args.forecast_month,
        ]
        if args.label:
            cmd_collect += ["--label", args.label]
        if args.mkzip:
            cmd_collect += ["--zip"]
        if args.include_models:
            cmd_collect += ["--include-models"]
        if args.include_config:
            cmd_collect += ["--include-config"]
        run(cmd_collect, "Empaquetar corrida (30_collect_run_artifacts.py)", env)

    # Backtest extendido: permite elegir periodo histórico
    backtest_start = args.backtest_start or None
    backtest_end = args.backtest_end or None
    if not args.validate_only:
        cmd_backtest = [py, "scripts/06_backtest_eval.py"]
        if backtest_start:
            cmd_backtest += ["--start", backtest_start]
        if backtest_end:
            cmd_backtest += ["--end", backtest_end]
        run(cmd_backtest, "06) Backtest extendido", env)

    print("\n✅ Pipeline completado.")

if __name__ == "__main__":
    # Si hay trades previos, sugerir tp/sl óptimos
    try:
        import pandas as pd
        trades_path = "reports/forecast/latest_forecast_trades.csv"
        if os.path.exists(trades_path):
            df_trades = pd.read_csv(trades_path)
            tp_opt, sl_opt = suggest_tp_sl(df_trades)
            print(f"Sugerencia: tp_atr_mult={tp_opt:.2f}, sl_atr_mult={sl_opt:.2f} (basado en trades previos)")
    except Exception as e:
        print(f"No se pudo sugerir tp/sl óptimos: {e}")
    main()
# scripts/run_pipeline.py