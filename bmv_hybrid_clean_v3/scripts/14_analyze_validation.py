"""
14_analyze_validation.py (robusto, sin matplotlib)
Se adapta a los CSV con columnas:
['ticker','side','entry_date','exit_date','tp','sl','reason_pred','pnl_pred',
 'outcome_real','entry_price','exit_price_real','pnl_sign_real','match_reason','bars_used']

Qué deriva:
- y_true: TP/SL desde outcome_real; para TIME/TIME_FALLBACK usa pnl_sign_real (>0)
- y_score: si existe (y_score/score/prob/proba/...), normaliza a [0,1]
- ticker: 'ticker' o 'symbol'
- reason: 'reason_pred' > 'reason' > 'pattern' > 'rule'
- entry_hour: desde 'entry_hour' o parseando 'entry_date'/'entry_dt'/'timestamp'
- sign_accuracy: si hay 'pnl_sign_real' (proporción de pnl_sign_real > 0)

Genera:
- analysis.md + CSVs (per_ticker, per_hour, per_reason, calibration_bins, thresholds_sweep)

Uso:
  python scripts/14_analyze_validation.py --months 2025-03 2025-04 2025-05
"""

import argparse
import os
import io
import sys
import numpy as np
import pandas as pd

_SKLEARN_OK = True
try:
    from sklearn.metrics import brier_score_loss, matthews_corrcoef
    from sklearn.calibration import calibration_curve
except Exception:
    _SKLEARN_OK = False


# -----------------------
# Utilidades
# -----------------------
def _to_markdown_table(df: pd.DataFrame, max_rows: int = None) -> str:
    if df is None or df.empty:
        return "_(sin datos)_"
    if max_rows is not None:
        df = df.head(max_rows)
    buf = io.StringIO()
    df.to_markdown(buf, index=True)
    return buf.getvalue()


def _safe_mean(series: pd.Series):
    try:
        return float(series.mean())
    except Exception:
        return float("nan")


def _norm01(x: pd.Series) -> pd.Series:
    s = pd.to_numeric(x, errors="coerce")
    if s.min() >= 0 and s.max() <= 1:
        return s.clip(0, 1)
    if s.max() <= 100 and s.min() >= 0:
        return (s / 100.0).clip(0, 1)
    mn, mx = s.min(), s.max()
    if np.isfinite(mn) and np.isfinite(mx) and mx > mn:
        return ((s - mn) / (mx - mn)).clip(0, 1)
    return s.clip(0, 1)


# -----------------------
# Detección de columnas
# -----------------------
def derive_y_true(df: pd.DataFrame, log: list) -> pd.Series | None:
    # 1) outcome_real con TP/SL y TIME/TIME_FALLBACK (usa pnl_sign_real)
    if "outcome_real" in df.columns:
        s = df["outcome_real"].astype(str).str.upper().str.strip()
        if s.notna().any():
            y = s.map({
                "TP": 1, "HIT_TP": 1, "TP_FIRST": 1,
                "SL": 0, "HIT_SL": 0, "SL_FIRST": 0
            })
            if "pnl_sign_real" in df.columns:
                pnl_pos = (pd.to_numeric(df["pnl_sign_real"], errors="coerce") > 0).astype(float)
                mask_time = s.isin(["TIME", "TIME_FALLBACK"])
                y = y.where(~mask_time, pnl_pos)
            if y.notna().any():
                log.append("y_true <- outcome_real (TP/SL) y TIME/TIME_FALLBACK con pnl_sign_real")
                return y.fillna(0).astype(float)

    # 2) fallback puro con pnl_sign_real
    if "pnl_sign_real" in df.columns:
        try:
            y = (pd.to_numeric(df["pnl_sign_real"], errors="coerce") > 0).astype(float)
            log.append("y_true <- (pnl_sign_real > 0) (fallback)")
            return y
        except Exception:
            pass

    # 3) otros nombres genéricos
    for c in ["y_true", "real_win", "label", "target"]:
        if c in df.columns:
            s = pd.to_numeric(df[c], errors="coerce")
            if s.notna().any():
                log.append(f"y_true <- '{c}' (num)")
                return s.fillna(0).astype(float)

    # 4) outcome/result genéricos
    for c in ["outcome", "result"]:
        if c in df.columns:
            s = df[c].astype(str).str.upper().str.strip()
            y = s.map({"TP":1, "HIT_TP":1, "TP_FIRST":1, "SL":0, "HIT_SL":0, "SL_FIRST":0})
            if y.notna().any():
                log.append(f"y_true <- mapeo TP/SL desde '{c}'")
                return y.fillna(0).astype(float)

    return None


def derive_y_score(df: pd.DataFrame, log: list) -> pd.Series | None:
    for c in ["y_score","score","prob","proba","proba_win","confidence","conf","pred_prob"]:
        if c in df.columns:
            s = _norm01(df[c])
            if s.notna().any():
                log.append(f"y_score <- '{c}' (normalizado a [0,1] si aplica)")
                return s
    return None


def derive_ticker(df: pd.DataFrame, log: list) -> str | None:
    for c in ["ticker", "symbol"]:
        if c in df.columns:
            log.append(f"ticker <- '{c}'")
            return c
    return None


def derive_reason(df: pd.DataFrame, log: list) -> str | None:
    for c in ["reason_pred", "reason", "pattern", "rule"]:
        if c in df.columns:
            log.append(f"reason <- '{c}'")
            return c
    return None


def derive_entry_hour(df: pd.DataFrame, log: list) -> pd.Series | None:
    if "entry_hour" in df.columns:
        try:
            return df["entry_hour"].astype(str)
        except Exception:
            pass
    for c in ["entry_date", "entry_time", "entry_dt", "entry_datetime", "timestamp"]:
        if c in df.columns:
            ts = pd.to_datetime(df[c], errors="coerce")
            if ts.notna().any():
                log.append(f"entry_hour derivada de '{c}'")
                return ts.dt.strftime("%H:%M")
    return None


# -----------------------
# Núcleo de análisis
# -----------------------
def analizar_mes(month: str) -> None:
    csv_path = f"reports/forecast/{month}/validation/forecast_vs_real.csv"
    out_dir  = f"reports/forecast/{month}/validation"
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n📂 Analizando {month}: {csv_path}")
    if not os.path.exists(csv_path):
        print("❌ No existe el archivo CSV. Se omite este mes.")
        return

    df = pd.read_csv(csv_path)
    mapping_log = []

    # Derivar columnas clave
    y_true = derive_y_true(df, mapping_log)
    if y_true is None:
        print("❌ No pude derivar 'y_true' a partir de las columnas disponibles.")
        print("   Columnas del CSV:", list(df.columns))
        return
    df["_y_true"] = y_true.astype(float)

    y_score = derive_y_score(df, mapping_log)
    ticker_col = derive_ticker(df, mapping_log)
    reason_col = derive_reason(df, mapping_log)
    entry_hour_series = derive_entry_hour(df, mapping_log)
    if entry_hour_series is not None:
        df["_entry_hour"] = entry_hour_series.astype(str)

    # sign_accuracy (si viene pnl_sign_real)
    sign_accuracy = float("nan")
    if "pnl_sign_real" in df.columns:
        try:
            sign_accuracy = (pd.to_numeric(df["pnl_sign_real"], errors="coerce") > 0).mean()
        except Exception:
            pass

    # Log del mapeo
    print("ℹ️ Mapeo aplicado:")
    for line in mapping_log:
        print("   -", line)

    # -------------------------
    # Métricas globales
    # -------------------------
    total_trades   = len(df)
    winrate_real   = _safe_mean(df["_y_true"])
    expectancy     = _safe_mean(pd.to_numeric(df["pnl_pred"], errors="coerce")) if "pnl_pred" in df.columns else float("nan")
    expectancy_real = _safe_mean(pd.to_numeric(df["pnl_real_pct"], errors="coerce")) if "pnl_real_pct" in df.columns else float("nan")

    # -------------------------
    # Por ticker / hora / reason
    # -------------------------
    def _agg_with_exp_real(groupby_obj):
        if "pnl_real_pct" in df.columns:
            return groupby_obj.agg(
                count=("_y_true","count"),
                winrate=("_y_true","mean"),
                exp_real=("pnl_real_pct","mean"),
            )
        else:
            return groupby_obj.agg(
                count=("_y_true","count"),
                winrate=("_y_true","mean"),
            )

    g_ticker = None
    if ticker_col:
        g_ticker = _agg_with_exp_real(df.groupby(ticker_col)).sort_values("winrate", ascending=False)

    g_hour = None
    if "_entry_hour" in df.columns:
        g_hour = _agg_with_exp_real(df.groupby("_entry_hour")).sort_index()

    g_reason = None
    if reason_col:
        g_reason = _agg_with_exp_real(df.groupby(reason_col)).sort_values("winrate", ascending=False)

    # -------------------------
    # Calibración y umbrales
    # -------------------------
    calibration_info = None
    thresholds_info  = None
    best_thr_section = []  # texto a insertar luego en el markdown

    if y_score is not None and _SKLEARN_OK:
        y_true_np  = df["_y_true"].values.astype(float)
        y_score_np = _norm01(y_score).values

        prob_true, prob_pred = calibration_curve(y_true_np, y_score_np, n_bins=10, strategy="uniform")
        try:
            brier = float(brier_score_loss(y_true_np, y_score_np))
        except Exception:
            brier = float("nan")

        yhat_05 = (y_score_np >= 0.5).astype(int)
        try:
            mcc_05 = float(matthews_corrcoef(y_true_np.astype(int), yhat_05))
        except Exception:
            mcc_05 = float("nan")

        calibration_df = pd.DataFrame({"bin_pred_prob": prob_pred, "bin_true_rate": prob_true})
        calibration_info = {"brier": brier, "mcc_thr_0_5": mcc_05, "table": calibration_df}

        rows = []
        for thr in np.linspace(0.40, 0.70, 7):
            mask = y_score_np >= thr
            sel  = int(mask.sum())
            wr   = float(y_true_np[mask].mean()) if sel > 0 else float("nan")
            cov  = (sel / len(y_true_np)) if len(y_true_np) > 0 else float("nan")
            rows.append({"threshold": round(float(thr), 3),
                         "selected_trades": sel,
                         "coverage": cov,
                         "winrate_selected": wr})
        thresholds_info = pd.DataFrame(rows)

        # Sugerencia de umbral (cobertura mínima 30%)
        if thresholds_info is not None and not thresholds_info.empty:
            thr_candidates = thresholds_info.dropna().copy()
            thr_candidates = thr_candidates[thr_candidates["coverage"] >= 0.30]
            if not thr_candidates.empty:
                best_row = thr_candidates.sort_values("winrate_selected", ascending=False).iloc[0]
                best_thr = float(best_row["threshold"])
                best_thr_section.append("## Sugerencia de umbral\n")
                best_thr_section.append(
                    f"- **Umbral recomendado (cobertura ≥30%)**: `{best_thr:.2f}` "
                    f"con winrate≈{best_row['winrate_selected']:.2%} "
                    f"y cobertura≈{best_row['coverage']:.0%}\n"
                )
                best_thr_section.append("_Ajusta según tu tolerancia a menor cobertura vs mayor winrate._\n")
                best_thr_section.append("\n---\n")

    elif y_score is not None and not _SKLEARN_OK:
        print("⚠️ sklearn no disponible: se omite curva de calibración y barrido de umbrales.")
    else:
        print("ℹ️ No se encontró columna de score/probabilidad; se omite calibración y umbrales.")

    # -------------------------
    # Exportar CSVs auxiliares
    # -------------------------
    if g_ticker is not None and not g_ticker.empty:
        g_ticker.to_csv(os.path.join(out_dir, "per_ticker.csv"))
    if g_hour is not None and not g_hour.empty:
        g_hour.to_csv(os.path.join(out_dir, "per_hour.csv"))
    if g_reason is not None and not g_reason.empty:
        g_reason.to_csv(os.path.join(out_dir, "per_reason.csv"))
    if calibration_info is not None:
        calibration_info["table"].to_csv(os.path.join(out_dir, "calibration_bins.csv"), index=False)
    if thresholds_info is not None and not thresholds_info.empty:
        thresholds_info.to_csv(os.path.join(out_dir, "thresholds_sweep.csv"), index=False)

    # -------------------------
    # Generar reporte Markdown
    # -------------------------
    md_lines = []
    md_lines.append(f"# Análisis de validación — {month}\n")
    md_lines.append("## Resumen global\n")
    md_lines.append(f"- **Trades**: {total_trades}")
    md_lines.append(f"- **Winrate real (TP/SL/TIME)**: {winrate_real:.2%}")
    if not np.isnan(sign_accuracy):
        md_lines.append(f"- **Sign accuracy (pnl_sign_real>0)**: {sign_accuracy:.2%}")
    md_lines.append(
        f"- **Expectancy (pnl_pred medio)**: {expectancy:.4f}"
        if not np.isnan(expectancy) else "- **Expectancy (pnl_pred medio)**: _no disponible_"
    )
    md_lines.append(
        f"- **Expectancy real (pnl_real_pct medio)**: {expectancy_real:.4f}"
        if not np.isnan(expectancy_real) else "- **Expectancy real**: _no disponible_"
    )

    md_lines.append("\n### Mapeo de columnas aplicado\n")
    md_lines.extend([f"- {line}" for line in mapping_log])

    md_lines.append("\n---\n")

    if g_ticker is not None:
        md_lines.append("## Desempeño por *ticker* (Top 15 por winrate)\n")
        md_lines.append(_to_markdown_table(g_ticker.head(15)))
        md_lines.append("")
        md_lines.append("_CSV_: `per_ticker.csv`")
        md_lines.append("\n---\n")

    if g_hour is not None:
        md_lines.append("## Desempeño por *hora* de entrada\n")
        md_lines.append(_to_markdown_table(g_hour))
        md_lines.append("")
        md_lines.append("_CSV_: `per_hour.csv`")
        md_lines.append("\n---\n")

    if g_reason is not None:
        md_lines.append("## Desempeño por *reason* (Top 20 por winrate)\n")
        md_lines.append(_to_markdown_table(g_reason.head(20)))
        md_lines.append("")
        md_lines.append("_CSV_: `per_reason.csv`")
        md_lines.append("\n---\n")

    if calibration_info is not None:
        md_lines.append("## Calibración (sin gráficos)\n")
        md_lines.append(f"- **Brier score**: {calibration_info['brier']:.4f}")
        md_lines.append(f"- **MCC** con umbral 0.5: {calibration_info['mcc_thr_0_5']:.3f}")
        md_lines.append("\n**Bins de calibración (prob. predicha vs prob. real):**\n")
        md_lines.append(_to_markdown_table(calibration_info["table"]))
        md_lines.append("")
        md_lines.append("_CSV_: `calibration_bins.csv`")
        md_lines.append("\n---\n")

    if thresholds_info is not None:
        md_lines.append("## Barrido de umbrales de `y_score`\n")
        md_lines.append(_to_markdown_table(
            thresholds_info.assign(
                coverage=lambda d: (d["coverage"]*100).round(2).astype(str) + "%"
            )[["threshold", "selected_trades", "coverage", "winrate_selected"]],
        ))
        md_lines.append("")
        md_lines.append("_CSV_: `thresholds_sweep.csv`")
        md_lines.append("\n---\n")

    # Sugerencia de umbral (si se calculó)
    md_lines.extend(best_thr_section)

    # Recomendaciones
    md_lines.append("## Recomendaciones iniciales\n")
    md_lines.append("- Enfocarse en **tickers** y **horas** con mejor winrate; excluir los de bajo rendimiento.")
    md_lines.append("- Afinar reglas con peor desempeño en **reason_pred** (desactivar o rebajar peso).")
    md_lines.append("- Si añades `y_score`, calibra y ajusta umbral con el barrido (y revisa el umbral recomendado).")
    md_lines.append("- Verificar consistencia entre `outcome_real` (TP/SL/TIME) y la validación TP/SL intradía.")

    report_path = os.path.join(out_dir, "analysis.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"✅ Reporte generado: {report_path}")
    if g_ticker is not None and not g_ticker.empty:
        print("   - per_ticker.csv")
    if g_hour is not None and not g_hour.empty:
        print("   - per_hour.csv")
    if g_reason is not None and not g_reason.empty:
        print("   - per_reason.csv")
    if calibration_info is not None:
        print("   - calibration_bins.csv")
    if thresholds_info is not None and not thresholds_info.empty:
        print("   - thresholds_sweep.csv")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", nargs="+", required=True,
                        help="Lista de meses a analizar (YYYY-MM)")
    args = parser.parse_args()

    for month in args.months:
        try:
            analizar_mes(month)
        except Exception as e:
            print(f"❌ Error analizando {month}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
