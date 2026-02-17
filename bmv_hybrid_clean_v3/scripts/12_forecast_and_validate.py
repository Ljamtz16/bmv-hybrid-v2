# scripts/12_forecast_and_validate.py
from __future__ import annotations
import argparse, os, subprocess, sys
from pathlib import Path

def run(cmd: list[str], env=None, title: str=""):
    print(f"\n▶ {title}:", " ".join(str(c) for c in cmd))
    proc = subprocess.run(cmd, env=env)
    if proc.returncode != 0:
        raise SystemExit(f"❌ Falló: {title} (code {proc.returncode})")

def main():
    p = argparse.ArgumentParser(
        description="Orquesta la predicción mensual, la validación y la integración de la magnitud de movimiento (regresión multi-H)."
    )
    # --- existentes ---
    p.add_argument("--month", required=True, help="Mes objetivo en formato YYYY-MM (p.ej. 2025-03)")
    p.add_argument("--cfg", default="", help="Ruta de config YAML a usar (opcional). Ej: config/paper.yaml")
    p.add_argument("--predict-only", action="store_true", help="Solo generar forecast (no valida)")
    p.add_argument("--validate-only", action="store_true", help="Solo validar (requiere forecast previo)")
    p.add_argument("--python", default=str(Path(".venv") / "Scripts" / "python.exe"),
                   help="Ruta al binario de Python a usar (default .venv/Scripts/python.exe)")

    # --- NUEVO: entrenamiento/aplicación del modelo de regresión ---
    p.add_argument("--use-return", action="store_true",
                   help="Aplica el/los modelo(s) de regresión de retorno para añadir % de movimiento al forecast del mes.")
    p.add_argument("--train-return", action="store_true",
                   help="(Opcional) Genera targets y entrena modelos de retorno antes de predecir.")
    p.add_argument("--return-horizons", default="5",
                   help="Horizontes H en días hábiles para entrenar, ej.: '1,3,5,10'. Default='5'.")
    p.add_argument("--infer-h", type=int, default=None,
                   help="Horizonte H a aplicar al forecast (si no se indica, usa el primero de --return-horizons).")
    p.add_argument("--target-kind", choices=["raw", "volnorm"], default="raw",
                   help="Tipo de target para entrenar: raw=target_return_Hd, volnorm=target_return_Hd_volnorm.")
    p.add_argument("--train-data", default="reports/forecast/training_dataset.csv",
                   help="CSV base para generar targets de retorno (si --train-return).")
    p.add_argument("--train-data-out", default="reports/forecast/training_dataset_w_returns.csv",
                   help="CSV de salida con targets de retorno (si --train-return).")

    # --- integración post-forecast ---
    p.add_argument("--features-csv", default="reports/forecast/latest_forecast_features.csv",
                   help="CSV de features del forecast (exportado por tu paso 09/12).")
    p.add_argument("--forecast-with-returns-out",
                   default="reports/forecast/latest_forecast_with_returns.csv",
                   help="CSV de salida con pred_return_Hd y EV tras aplicar el modelo de retorno.")
    p.add_argument("--rank-topn", type=int, default=0,
                   help="Si >0, genera ranking TOP-N con expected value (usa 23_rank_signals.py).")
    p.add_argument("--rank-out", default="reports/forecast/ranked_signals_topN.csv",
                   help="Ruta del CSV de ranking TOP-N (si --rank-topn > 0).")
    p.add_argument("--min-prob", type=float, default=0.0, help="Umbral mínimo de probabilidad para filtrar señales")

    # === NUEVO: aplicar políticas de wf_box al sistema principal ===
    p.add_argument("--use-wf-policy", action="store_true",
                   help="Si se activa, carga la política seleccionada en wf_box y recalcula PnL/TP/SL/H sobre la validación del sistema principal.")
    p.add_argument("--wf-policy-file",
                   default="wf_box/reports/forecast/policy_selected_walkforward.yaml",
                   help="Ruta al archivo de políticas de wf_box (.yaml/.yml o .csv).")
    p.add_argument("--policy-json-out",
                   help="Ruta de salida del JSON normalizado de política. Default: reports/forecast/<MES>/policy_wfbox.json")
    p.add_argument("--validation-dir",
                   help="Directorio de validación del mes (donde está validation_join_auto.csv). Default: reports/forecast/<MES>/validation")
    p.add_argument("--policy-csv-in",
                   help="Archivo base de validación a revaluar. Default: <validation-dir>/validation_join_auto.csv")
    p.add_argument("--policy-csv-out",
                   help="CSV de salida con la política aplicada. Default: <validation-dir>/validation_trades_policy.csv")
    p.add_argument("--policy-kpi-json-out",
                   help="JSON de KPIs tras aplicar la política. Default: <validation-dir>/kpi_policy.json")

    # --- LIMITES DE SIMULTANEIDAD (opcional) ---
    p.add_argument("--apply-open-limits", action="store_true",
                   help="Aplica tope de simultaneidad/presupuesto al CSV de validación del mes (validation_join_auto.csv).")
    p.add_argument("--max-open", type=int, default=0,
                   help="Máx. posiciones abiertas simultáneas (por día para entradas). 0 = sin tope por conteo.")
    p.add_argument("--per-trade-cash", type=float, default=0.0,
                   help="Capital por operación. Requerido si usas --budget.")
    p.add_argument("--budget", type=float, default=0.0,
                   help="Presupuesto total simultáneo para nuevas entradas del día. 0 = sin tope por presupuesto.")
    p.add_argument("--decision-log", default="reports/forecast/decision_logs/open_decisions.csv",
                   help="Ruta del CSV de auditoría de decisiones OPEN/SKIP.")

    args = p.parse_args()

    # Entorno
    env = os.environ.copy()
    if args.cfg:
        env["CFG"] = args.cfg
        print(f"• CFG={args.cfg}")

    py = args.python

    # Parseo de horizontes y determinación de H a inferir
    horizons_str = str(args.return_horizons).strip()
    horizons = [int(h.strip()) for h in horizons_str.split(",") if h.strip()]
    horizons = sorted(set([h for h in horizons if h > 0]))
    if not horizons:
        raise SystemExit("❌ Debes especificar al menos un horizonte válido en --return-horizons (p. ej. '3,5').")

    infer_h = args.infer_h if args.infer_h is not None else horizons[0]

    print(f"• Horizontes a entrenar: {horizons}")
    print(f"• Horizonte a aplicar en forecast (infer): H={infer_h}")

    # ---------------------------------------------------------------------
    # (A) ENTRENAR MODELOS DE REGRESIÓN (opcional, multi-H)
    # ---------------------------------------------------------------------
    if args.train_return:
        # 1) Generar targets de retorno para TODOS los H indicados
        cmd_targets = [
            py, "scripts/20b_add_return_targets.py",
            "--data", args.train_data,
            "--out",  args.train_data_out,
            "--horizons", ",".join(str(h) for h in horizons)
        ]
        run(cmd_targets, env=env, title=f"Generar targets de retorno (H={horizons})")

        # 2) Entrenar modelos multi-H (raw o volnorm)
        cmd_train_ret = [
            py, "scripts/22_train_return_model.py",
            "--data", args.train_data_out,
            "--horizons", ",".join(str(h) for h in horizons),
            "--kind", args.target_kind,
        ]
        run(cmd_train_ret, env=env, title=f"Entrenar modelos de retorno (kind={args.target_kind}, H={horizons})")

    # ---------------------------------------------------------------------
    # (B) PREDECIR EL MES
    # ---------------------------------------------------------------------
    min_prob = args.min_prob
    if not args.validate_only:
        cmd_forecast = [py, "scripts/09_make_month_forecast.py", "--month", args.month, "--min-prob", str(min_prob)]
        run(cmd_forecast, env=env, title="Predicción mensual (make_month_forecast)")

    # ---------------------------------------------------------------------
    # (C) APLICAR MODELO DE RETORNO AL FORECAST (opcional)
    # ---------------------------------------------------------------------
    if args.use_return:
        cmd_add_returns = [
            py, "scripts/12_run_forecast_add_returns_example.py",
            "--H", str(infer_h),
            "--features_csv", args.features_csv,
            "--out", args.forecast_with_returns_out
        ]
        run(cmd_add_returns, env=env, title=f"Añadir pred_return_{infer_h}d y EV al forecast")

        if args.rank_topn and args.rank_topn > 0:
            cmd_rank = [
                py, "scripts/23_rank_signals.py",
                "--in_csv", args.forecast_with_returns_out,
                "--top_n", str(args.rank_topn),
                "--out", args.rank_out
            ]
            run(cmd_rank, env=env, title=f"Ranking TOP-{args.rank_topn} por expected value")

    # ---------------------------------------------------------------------
    # (D) VALIDAR EL MES
    # ---------------------------------------------------------------------
    if not args.predict_only:
        cmd_validate = [py, "scripts/10_validate_month_forecast.py", "--month", args.month]
        run(cmd_validate, env=env, title="Validación mensual (validate_month_forecast)")

    # ---------------------------------------------------------------------
    # (D.1) APLICAR LIMITE DE SIMULTANEIDAD (opcional, sobre join_auto)
    # ---------------------------------------------------------------------
    limited_csv = None
    if args.apply_open_limits:
        validation_dir = f"reports/forecast/{args.month}/validation"
        src_csv = str(Path(validation_dir) / "validation_join_auto.csv")
        limited_csv = str(Path(validation_dir) / "validation_join_auto_limited.csv")

        cmd_limit = [
            py, "scripts/27_filter_open_limits.py",
            "--in",  src_csv,
            "--out", limited_csv,
            "--decision-log", args.decision_log,
        ]
        if args.max_open and args.max_open > 0:
            cmd_limit += ["--max-open", str(args.max_open)]
        if args.per_trade_cash and args.per_trade_cash > 0:
            cmd_limit += ["--per-trade-cash", str(args.per_trade_cash)]
        if args.budget and args.budget > 0:
            cmd_limit += ["--budget", str(args.budget)]

        run(cmd_limit, env=env, title="Aplicar tope de simultaneidad al join_auto")

    # ---------------------------------------------------------------------
    # (E) NUEVO: CARGAR POLÍTICA wf_box Y RECOMPUTAR PnL SOBRE LA VALIDACIÓN
    # ---------------------------------------------------------------------
    if args.use_wf_policy:
        # 1) Exportar la política normalizada a JSON
        policy_json_out = args.policy_json_out or f"reports/forecast/{args.month}/policy_wfbox.json"
        cmd_load_policy = [
            py, "scripts/25_load_wf_policy.py",
            "--month", args.month,
            "--wf-policy", args.wf_policy_file,
            "--out-json", policy_json_out
        ]
        run(cmd_load_policy, env=env, title="Exportar política wf_box a JSON")

        # 2) Recalcular PnL/TP/SL/H en la validación del sistema principal
        validation_dir = args.validation_dir or f"reports/forecast/{args.month}/validation"
        # si ya filtramos por simultaneidad, usar el CSV limitado
        default_in = str(Path(validation_dir) / "validation_join_auto.csv")
        if args.apply_open_limits and limited_csv:
            default_in = limited_csv
        csv_in = args.policy_csv_in or default_in

        csv_out = args.policy_csv_out or str(Path(validation_dir) / "validation_trades_policy.csv")
        kpi_out = args.policy_kpi_json_out or str(Path(validation_dir) / "kpi_policy.json")

        cmd_recompute = [
            py, "scripts/26_policy_recompute_pnl.py",
            "--month", args.month,
            "--policy-json", policy_json_out,
            "--validation-dir", validation_dir,
            "--csv-in", csv_in,
            "--csv-out", csv_out,
            "--kpi-json-out", kpi_out
        ]

        if args.predict_only:
            print("⚠ Advertencia: --predict-only está activo. Se intentará aplicar la política sobre archivos existentes en validación.")
        run(cmd_recompute, env=env, title="Aplicar política wf_box a la validación (recompute PnL)")

    print("\n✅ Flujo completado.")

if __name__ == "__main__":
    main()
