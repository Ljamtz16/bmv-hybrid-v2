#!/usr/bin/env python
"""
MEJORA 5 + 6: Producción-Ready Orchestrator (v2 - Refactorizado)
================================================================
Integración completa con operability.py:
  1. macro_event_alerts.py como GATE (¿es seguro operar hoy?)
  2. Generar señales (si es seguro)
  3. Calcular métricas rolling
  4. Kill switch: si 5d Conf>=4 pero accuracy<50% → PAUSE
  5. Validación automática de operables
  6. Auditoría en run_audit.json

FLUJO DIARIO:
  python production_orchestrator.py --date=2025-01-13

OUTPUT:
  - signals_to_trade.csv (solo lo operable)
  - metrics_rolling.csv (5d/10d)
  - kill_switch_status.txt (estado del sistema)
  - run_audit.json (auditoría)
  - PNG visualizations
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import json
import warnings

warnings.filterwarnings("ignore")

# ============================================================================
# SINGLE SOURCE OF TRUTH: Importar de operability.py
# ============================================================================

from operability import (
    operable_mask,
    get_operability_breakdown,
    prepare_operability_columns,
    CONF_THRESHOLD,
    WHITELIST_TICKERS,
    ALLOWED_RISKS,
    EXPECTED_OPERABLE_COUNT
)
from operability_config import kill_switch, model_health, output, data_source, gate_config, delta_tolerance

REPO_ROOT = Path(__file__).resolve().parent

# ⚠️ USAR CSV_AUTHORITY de operability_config (Single Source of Truth)
CSV_PATH = data_source.CSV_AUTHORITY

OUTPUTS_DIR = REPO_ROOT / "outputs" / "analysis"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (14, 8)

# Umbrales (ahora desde operability_config)
ACCURACY_THRESHOLD = kill_switch.ACCURACY_CRITICAL  # 45% = PAUSE
ROLLING_WINDOW = 5  # días
KILL_SWITCH_WINDOW = kill_switch.WINDOW_DAYS


def load_data(csv_path: Path):
    """
    Cargar y preparar datos usando PREPROCESAMIENTO ESTÁNDAR.
    
    Retorna DataFrame y métricas de filas para auditoría.
    """
    df = pd.read_csv(csv_path)
    rows_loaded = len(df)

    # Fecha y validaciones iniciales
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    invalid_date_count = int(df["date"].isna().sum())

    # Filas con campos críticos faltantes (y_H3, y_hat, close, date)
    missing_core_mask = df[["y_H3", "y_hat", "close", "date"]].isna().any(axis=1)
    missing_core_fields = int(missing_core_mask.sum())
    df = df.dropna(subset=["y_H3", "y_hat", "close", "date"])
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    
    # ⚠️ PREPROCESAMIENTO ESTÁNDAR (normaliza confidence, calcula macro_risk)
    df = prepare_operability_columns(df, warn_on_fallback=True)
    rows_after_prepare = len(df)
    
    # Precio predicho
    df["price_pred"] = df["close"] * (1 + df["y_hat"])
    df["price_real"] = df["close"].shift(-3)
    price_real_nan_after_shift = int(df["price_real"].isna().sum())
    df = df.dropna(subset=["price_real"])
    rows_after_any_filter = len(df)
    
    df["direction_correct"] = (np.sign(df["y_hat"]) == np.sign(df["y_H3"])).astype(int)
    df["abs_price_error_pct"] = abs(((df["price_real"] - df["price_pred"]) / df["price_pred"]) * 100)
    
    row_counts = {
        "rows_loaded": int(rows_loaded),
        "rows_after_prepare": int(rows_after_prepare),
        "rows_after_dedup": int(rows_after_prepare),  # no dedup aplicado
        "rows_after_any_filter": int(rows_after_any_filter),
    }
    drop_reason_counts = {
        "invalid_date": invalid_date_count,
        "missing_core_fields": missing_core_fields,
        "price_real_nan_after_shift": price_real_nan_after_shift,
    }
    return df, row_counts, drop_reason_counts



def calculate_rolling_metrics(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """Calcular métricas rolling."""
    
    df_sorted = df.sort_values(["ticker", "date"])
    
    # Por ticker
    df_sorted["accuracy_rolling"] = df_sorted.groupby("ticker")["direction_correct"].transform(
        lambda x: x.rolling(window, min_periods=1).mean()
    )
    
    df_sorted["mae_rolling"] = df_sorted.groupby("ticker")["abs_price_error_pct"].transform(
        lambda x: x.rolling(window, min_periods=1).mean()
    )
    
    # Global (por fecha)
    df_sorted["accuracy_rolling_global"] = df_sorted.groupby("date")["direction_correct"].transform(
        lambda x: x.rolling(window, min_periods=1).mean()
    )
    
    df_sorted["mae_rolling_global"] = df_sorted.groupby("date")["abs_price_error_pct"].transform(
        lambda x: x.rolling(window, min_periods=1).mean()
    )
    
    return df_sorted


def detect_kill_switch(df: pd.DataFrame, window: int = 5, 
                       accuracy_threshold: float = 0.50) -> dict:
    """
    Kill switch CORRECTO: 
    - Cuenta DÍAS (no filas)
    - Usa ventana móvil de últimos N días operativos
    - Solo considera señales con Conf>=4 y Risk permitido
    
    Returns:
        {
            "triggered": bool,
            "days_triggered": int,
            "reason": str,
            "pause_until": str
        }
    """
    
    d = df.copy()
    
    # Filtro operable: Conf>=4 solamente
    d = d[d["confidence_score"] >= CONF_THRESHOLD]
    
    # Si no hay datos operables, NO dispara kill switch
    if d.empty:
        return {
            "triggered": False,
            "reason": f"No operable signals found (Conf>={CONF_THRESHOLD})",
            "pause_until": None,
            "days_triggered": 0,
            "window_days": window,
        }
    
    # Calcular accuracy por DÍA (cada día = 1)
    # Asumir que ya existe columna 'direction_correct' con 0/1
    d["direction_correct"] = d["direction_correct"].astype(int)
    
    daily_acc = (
        d.groupby("date")["direction_correct"]
        .mean()
        .sort_index()
    )
    
    # Tomar últimos N días operativos
    last_window = daily_acc.tail(window)
    
    # Si aún no hay suficientes días, no disparar
    if len(last_window) < window:
        return {
            "triggered": False,
            "reason": f"Insufficient operable days for kill switch window: {len(last_window)}/{window}",
            "pause_until": None,
            "days_triggered": 0,
            "window_days": window,
        }
    
    # Condición: TODOS los últimos N días operativos por debajo del umbral
    below = last_window < accuracy_threshold
    triggered = bool(below.all())
    
    # Contar días por debajo (solo racha final consecutiva)
    days_triggered = sum(1 for v in reversed(below.tolist()) if v)
    
    pause_until = None
    if triggered:
        pause_until = str((pd.to_datetime(datetime.now().date()) + timedelta(days=window)).date())
    
    reason = (
        f"Accuracy < {int(accuracy_threshold*100)}% for {window} consecutive OPERABLE days (Conf>={CONF_THRESHOLD})"
        if triggered else
        f"OK: last {window} operable days not all below {int(accuracy_threshold*100)}%"
    )
    
    # Guardar TODA la ventana (últimos N días) y la serie completa para auditoría
    daily_acc_window_dict = {str(k): round(float(v), 4) for k, v in last_window.items()}
    daily_acc_all_dict = {str(k): round(float(v), 4) for k, v in daily_acc.items()}
    
    return {
        "triggered": triggered,
        "reason": reason,
        "pause_until": pause_until,
        "days_triggered": days_triggered if triggered else 0,
        "window_days": window,
        "daily_acc_window": daily_acc_window_dict,  # Últimos N días (para decisión)
        "daily_acc_all": daily_acc_all_dict,  # Todo el histórico (para auditoría)
    }


def filter_operable_signals(df: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
    """
    GATE: Filtrar solo señales operables
    
    ⚠️ Asume que df YA tiene macro_risk calculado por prepare_operability_columns()
    
    Usa operable_mask() de operability.py (single source of truth).
    
    Condiciones:
      1. Confidence >= 4
      2. macro_risk IN ["LOW", "MEDIUM"]
      3. ticker IN whitelist
    """
    
    # ⚠️ Ya NO calcula macro_risk (se hace en load_data con prepare_operability_columns)
    
    # Aplicar máscara (desde operability.py)
    mask = operable_mask(df)
    operable = df[mask].copy()
    
    # Filtrar por fecha si es necesario
    operable = operable[operable["date"] == date]
    
    return operable


def generate_trading_signals(df: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
    """
    Generar señales de trading para la fecha.
    """
    
    df_today = df[df["date"] == date].copy()
    
    # Filtrar operables
    signals = filter_operable_signals(df_today, date)
    
    if len(signals) == 0:
        return pd.DataFrame()
    
    # Rank por confianza y MAE
    signals = signals.sort_values(
        ["confidence_score", "abs_price_error_pct"],
        ascending=[False, True]
    )
    
    # Columnas relevantes
    output_cols = [
        "date", "ticker", "close", "y_hat", "y_H3",
        "confidence_score", "abs_price_error_pct",
        "macro_risk", "direction_correct"
    ]
    
    signals = signals[[c for c in output_cols if c in signals.columns]]
    
    return signals


def read_previous_kill_switch_status() -> dict:
    """
    Leer el kill_switch_status anterior.
    Returns: {"triggered": bool} o {} si no existe
    """
    status_file = OUTPUTS_DIR / "kill_switch_status.txt"
    
    if not status_file.exists():
        return {}
    
    try:
        with open(status_file, "r") as f:
            content = f.read()
            # Buscar línea "Triggered: ..."
            for line in content.split("\n"):
                if "Triggered:" in line:
                    triggered = "True" in line
                    return {"triggered": triggered}
    except:
        pass
    
    return {}


def has_state_changed(current_triggered: bool, previous_status: dict) -> bool:
    """
    Detectar si el estado del kill switch cambió.
    Returns: True si hubo cambio (False→True o True→False)
    """
    if not previous_status:  # Primer run
        return True  # Primera vez, siempre "cambio"
    
    previous_triggered = previous_status.get("triggered", False)
    return current_triggered != previous_triggered


def plot_daily_overview(df: pd.DataFrame, signals: pd.DataFrame, 
                       kill_switch_status: dict, date: pd.Timestamp):
    """Gráfica diaria del sistema."""
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. Señales por confidence
    ax = axes[0, 0]
    if len(signals) > 0:
        conf_counts = signals["confidence_score"].value_counts().sort_index()
        ax.bar(conf_counts.index, conf_counts.values, color="#4ECDC4", alpha=0.8)
    ax.set_xlabel("Confidence Score")
    ax.set_ylabel("# Señales")
    ax.set_title(f"Señales Operables por Confianza ({date.date()})")
    ax.grid(True, alpha=0.3, axis="y")
    
    # 2. MAE por ticker (en signals)
    ax = axes[0, 1]
    if len(signals) > 0:
        ticker_mae = signals.groupby("ticker")["abs_price_error_pct"].mean().sort_values()
        ax.barh(ticker_mae.index, ticker_mae.values, color="#FFE66D", alpha=0.8)
    ax.set_xlabel("MAE (%)")
    ax.set_title("Error por Ticker (Operables)")
    ax.grid(True, alpha=0.3, axis="x")
    
    # 3. Accuracy rolling (últimos 10 días)
    ax = axes[1, 0]
    df_rolling = df.sort_values("date").tail(20)
    daily_acc = df_rolling.groupby("date")["direction_correct"].mean() * 100
    ax.plot(daily_acc.index, daily_acc.values, "o-", linewidth=2, markersize=8, color="steelblue")
    ax.axhline(50, color="red", linestyle="--", linewidth=2, alpha=0.5, label="50% threshold")
    ax.fill_between(daily_acc.index, daily_acc.values, 50, where=(daily_acc >= 50), 
                    alpha=0.3, color="green", label="Arriba threshold")
    ax.fill_between(daily_acc.index, daily_acc.values, 50, where=(daily_acc < 50), 
                    alpha=0.3, color="red", label="Debajo threshold")
    ax.set_ylabel("Accuracy (%)")
    ax.set_title("Accuracy Rolling (10d)")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # 4. Kill switch status
    ax = axes[1, 1]
    ax.axis("off")
    
    if kill_switch_status["triggered"]:
        status_text = f"""
╔═ ⚠️ KILL SWITCH ACTIVADO ⚠️
║
║ Razón: {kill_switch_status['reason']}
║
║ Pausar hasta: {kill_switch_status['pause_until']}
║
║ Días consecutivos: {kill_switch_status['days_triggered']}/{KILL_SWITCH_WINDOW}
║
╚════════════════════════════════════
        """
        color_box = "red"
    else:
        status_text = f"""
╔═ ✅ SISTEMA NORMAL
║
║ {kill_switch_status['reason']}
║
║ Siguientes {KILL_SWITCH_WINDOW} días monitoreados
║
╚════════════════════════════════════
        """
        color_box = "green"
    
    ax.text(0.05, 0.95, status_text, transform=ax.transAxes, fontsize=10,
           verticalalignment='top', fontfamily='monospace',
           bbox=dict(boxstyle='round', facecolor=color_box, alpha=0.2))
    
    plt.suptitle(f"Daily Overview - {date.date()}", 
                 fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    fname = f"15_daily_overview_{date.date()}.png"
    plt.savefig(OUTPUTS_DIR / fname, dpi=150, bbox_inches="tight")
    print(f"✓ Gráfica: {fname}")
    plt.close()


def main():
    """Flujo principal."""
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None, 
                       help="Fecha (YYYY-MM-DD). Default: hoy")
    args = parser.parse_args()
    
    if args.date:
        target_date = pd.to_datetime(args.date)
    else:
        target_date = pd.Timestamp(datetime.now().date())
    
    print(f"\n{'='*70}")
    print(f"PRODUCCIÓN ORCHESTRATOR - {target_date.date()}")
    print(f"{'='*70}")
    
    # 1. Cargar datos
    df, row_counts, drop_reason_counts = load_data(CSV_PATH)
    gap_overlay_active = gate_config.is_gap_overlay_active()
    
    # 2. Calcular métricas rolling
    df = calculate_rolling_metrics(df, window=ROLLING_WINDOW)
    
    # 3. Detectar kill switch
    kill_switch = detect_kill_switch(df, window=KILL_SWITCH_WINDOW)
    
    # 3b. Leer status anterior
    previous_status = read_previous_kill_switch_status()
    state_changed = has_state_changed(kill_switch['triggered'], previous_status)
    
    print(f"\n[KILL SWITCH STATUS]")
    print(f"  Triggered: {kill_switch['triggered']}")
    print(f"  Razón: {kill_switch['reason']}")
    if state_changed:
        print(f"  ⚠️ ESTADO CAMBIÓ: {previous_status.get('triggered', '?')} → {kill_switch['triggered']}")
    if kill_switch['triggered']:
        print(f"  ⚠️ SISTEMA EN PAUSA HASTA: {kill_switch['pause_until']}")
    
    # 4. Filtrar señales operables
    signals = filter_operable_signals(df, target_date)
    
    print(f"\n[SEÑALES DIARIAS - {target_date.date()}]")
    print(f"  Total en dataset: {len(df[df['date'] == target_date])}")
    print(f"  Operables (Conf>=4, Risk<=MEDIUM, Whitelist): {len(signals)}")
    
    if len(signals) > 0:
        print(f"\n[TOP SEÑALES]")
        top_signals = signals.nlargest(5, "confidence_score")[
            ["ticker", "confidence_score", "abs_price_error_pct", "macro_risk"]
        ]
        print(top_signals.to_string(index=False))
    
    # 5. Export
    signals.to_csv(OUTPUTS_DIR / f"signals_to_trade_{target_date.date()}.csv", index=False)
    print(f"\n✓ Exportado: signals_to_trade_{target_date.date()}.csv")
    
    # 6. Gráfica
    plot_daily_overview(df, signals, kill_switch, target_date)
    
    # 7. Kill switch status file
    # SOLO escribir a disco si hay cambio de estado (evitar ruido)
    if state_changed:
        with open(OUTPUTS_DIR / "kill_switch_status.txt", "w") as f:
            f.write(f"Kill Switch Status Report\n")
            f.write(f"Generated: {datetime.now()}\n")
            f.write(f"Target Date: {target_date.date()}\n")
            f.write(f"\n[STATUS]\n")
            f.write(f"Triggered: {kill_switch['triggered']}\n")
            f.write(f"Reason: {kill_switch['reason']}\n")
            if kill_switch['triggered']:
                f.write(f"Pause Until: {kill_switch['pause_until']}\n")
            f.write(f"\nDays Triggered: {kill_switch['days_triggered']}/{KILL_SWITCH_WINDOW}\n")
            
            # AUDITORÍA: Guardar ventana (últimos N días operativos)
            f.write(f"\n[DAILY ACCURACY WINDOW (últimos {KILL_SWITCH_WINDOW} días)]\n")
            for date_str, acc in kill_switch['daily_acc_window'].items():
                f.write(f"  {date_str}: {acc:.2%}\n")
            
            # CONTEXTO: Guardar histórico completo (para investigación si dispara)
            f.write(f"\n[HISTORICAL ACCURACY (todos los días con Conf>={CONF_THRESHOLD})]\n")
            for date_str, acc in sorted(kill_switch['daily_acc_all'].items())[-10:]:  # Últimos 10 días
                f.write(f"  {date_str}: {acc:.2%}\n")
        
        log_msg = f"✓ Kill switch: {previous_status.get('triggered', '?')} → {kill_switch['triggered']} [exportado]"
        print(log_msg)
    else:
        log_msg = f"✓ Kill switch: {kill_switch['triggered']} [sin cambio, no escribir a disco]"
        print(log_msg)
    
    # ====================================================================
    # VALIDACIÓN AUTOMÁTICA OBLIGATORIA
    # ====================================================================
    
    print(f"\n[VALIDACIÓN AUTOMÁTICA]")
    
    # Breakdown de operables (global)
    breakdown = get_operability_breakdown(df)
    global_operables_count = int(breakdown['operable'])
    daily_operables_count = int(len(signals))
    expected_global_operables_count = EXPECTED_OPERABLE_COUNT
    expected_daily_operables_count = None  # No hay referencia diaria

    print(f"  Filas cargadas: {row_counts['rows_loaded']:,} -> prep: {row_counts['rows_after_prepare']:,} -> post-filtros: {row_counts['rows_after_any_filter']:,}")
    print(f"  Global (todas las filas): {breakdown['global']:,}")
    print(f"  Conf>=4: {breakdown['conf_only']:,}")
    print(f"  +Risk: {breakdown['conf_risk']:,}")
    print(f"  +Whitelist (global operables): {global_operables_count:,}")
    print(f"  Operables del día {target_date.date()}: {daily_operables_count:,}")
    
    # Validar solo global vs expected_global usando tolerancias centralizadas
    delta_global = global_operables_count - expected_global_operables_count
    delta_global_pct = abs(delta_global) / expected_global_operables_count * 100 if expected_global_operables_count > 0 else 0
    tol_abs = delta_tolerance.DELTA_TOLERANCE_ABSOLUTE
    tol_pct = delta_tolerance.DELTA_TOLERANCE_PCT

    if delta_global == 0:
        print(f"  ✅ Operables global: {global_operables_count:,} (consistencia total vs esperado {expected_global_operables_count:,})")
        validation_ok = True
    elif abs(delta_global) <= tol_abs:
        print(f"  ⚠️  Operables global: {global_operables_count:,} (delta ±{tol_abs}, dentro de margen)")
        validation_ok = True
    elif delta_global_pct <= tol_pct:
        print(f"  ⚠️  Operables global: {global_operables_count:,} (delta {delta_global_pct:.2f}%, dentro de {tol_pct}%)")
        validation_ok = True
    else:
        print(f"  ❌ MISMATCH GLOBAL: {global_operables_count:,} vs {expected_global_operables_count:,} ({delta_global_pct:.2f}%)")
        validation_ok = False
        if output.ABORT_ON_MISMATCH:
            print(f"  🛑 ABORT_ON_MISMATCH=True - Abortando")
            import sys
            sys.exit(1)
    
    # ====================================================================
    # GUARDAR AUDITORÍA EN run_audit.json CON METADATA COMPLETA
    # ====================================================================
    
    if output.SAVE_RUN_AUDIT:
        # Calcular metadata del dataset
        import hashlib
        
        # Hash MD5
        with open(CSV_PATH, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()[:8]
        
        # Fallback flags + distribución por DÍA (no por fila)
        macro_risk_fallback_count = 0
        macro_risk_by_day = {}
        high_days_count_last_60 = 0
        
        if "macro_risk" in df.columns:
            # Detectar si hay fallbacks (todos MEDIUM sería sospechoso)
            risk_dist = df["macro_risk"].value_counts()
            if len(risk_dist) == 1 and "MEDIUM" in risk_dist:
                macro_risk_fallback_count = len(df)
            
            # Distribución por día único
            risk_by_day_series = df.groupby("date")["macro_risk"].first().value_counts()
            macro_risk_by_day = {
                "total_days": int(df["date"].nunique()),
                "distribution": risk_by_day_series.to_dict(),
                "high_days_pct": round(100 * risk_by_day_series.get("HIGH", 0) / df["date"].nunique(), 2)
            }
            # Contar días HIGH en los últimos 60 días
            cutoff = df["date"].max() - pd.Timedelta(days=60)
            recent_days = df[df["date"] >= cutoff].groupby("date")["macro_risk"].first()
            high_days_count_last_60 = int((recent_days == "HIGH").sum())

        # Gap overlay availability
        gap_available_rows = int(df["gap_pct_available"].sum()) if "gap_pct_available" in df.columns else 0
        gap_unavailable_rows = int(len(df) - gap_available_rows) if "gap_pct_available" in df.columns else int(len(df))
        gap_unavailable_pct = round(100 * gap_unavailable_rows / len(df), 2) if len(df) else 0.0

        # Separation report (si hay direction_correct)
        separation_report = {}
        if "direction_correct" in df.columns and "macro_risk" in df.columns:
            try:
                acc_medium = df[df["macro_risk"] == "MEDIUM"]["direction_correct"].mean()
                acc_high = df[df["macro_risk"] == "HIGH"]["direction_correct"].mean()
                separation = float(abs(acc_high - acc_medium))
                # Sample size by unique day
                high_days = int((df.groupby("date")["macro_risk"].first() == "HIGH").sum())
                separation_report = {
                    "acc_medium": round(float(acc_medium), 4) if pd.notna(acc_medium) else None,
                    "acc_high": round(float(acc_high), 4) if pd.notna(acc_high) else None,
                    "separation": round(separation, 4),
                    "high_days": high_days,
                    "min_high_days_required": gate_config.MIN_HIGH_DAYS_FOR_SEPARATION,
                    "sample_sufficient": bool(high_days >= gate_config.MIN_HIGH_DAYS_FOR_SEPARATION)
                }
            except Exception:
                separation_report = {"error": "unable to compute"}
        
        audit = {
            "timestamp": str(datetime.now()),
            "target_date": str(target_date.date()),
            
            # METADATA DEL DATASET
            "dataset_metadata": {
                "source": str(CSV_PATH.name),
                "full_path": str(CSV_PATH),
                "file_size_mb": round(CSV_PATH.stat().st_size / 1024 / 1024, 2),
                "hash_md5": file_hash,
                "total_rows": int(len(df)),
                "date_min": str(df["date"].min().date()),
                "date_max": str(df["date"].max().date()),
                "unique_dates": int(df["date"].nunique()),
                "unique_tickers": int(df["ticker"].nunique()),
                "row_counts": row_counts,
                "dropped_rows_reason_counts": drop_reason_counts,
            },
            
            # FALLBACK FLAGS
            "fallback_flags": {
                "macro_risk_fallback_count": int(macro_risk_fallback_count),
                "macro_risk_distribution_by_row": df["macro_risk"].value_counts().to_dict() if "macro_risk" in df.columns else {},
                "macro_risk_by_day": macro_risk_by_day,  # ✅ Por día único
                "high_days_count_last_60": int(high_days_count_last_60)
            },
            
            # GAP OVERLAY
            "gap_overlay": {
                "available_rows": gap_available_rows,
                "unavailable_rows": gap_unavailable_rows,
                "unavailable_pct": gap_unavailable_pct,
                "policy": {
                    "requested": gate_config.GAP_OVERLAY_ENABLED,
                    "active": gap_overlay_active,
                    "mode": gate_config.MODE,
                    "strict_mode": gate_config.STRICT_MODE,
                    "ohlcv_ready": gate_config.OHLCV_READY,
                    "hardfail_threshold_pct": gate_config.GAP_UNAVAILABLE_PCT_HARDFAIL,
                }
            },
            
            # BREAKDOWN POR FILTRO
            "breakdown": {
                "global": int(breakdown['global']),
                "conf_only": int(breakdown['conf_only']),
                "percentages": {k: float(v) for k, v in breakdown['percentages'].items()}
            },
            
            "validation": {
                "global_operables_count": global_operables_count,
                "daily_operables_count": daily_operables_count,
                "expected_global_operables_count": expected_global_operables_count,
                "expected_daily_operables_count": expected_daily_operables_count,
                "delta_global": int(delta_global),
                "delta_global_pct": round(float(delta_global_pct), 2),
                "status": "OK" if validation_ok else "MISMATCH",
                "separation_report": separation_report
            },
            "kill_switch": {
                "triggered": bool(kill_switch["triggered"]),
                "reason": kill_switch["reason"]
            },
            "output": {
                "signals_to_trade": f"signals_to_trade_{target_date.date()}.csv",
                "kill_switch_status": "kill_switch_status.txt",
                "plot": f"15_daily_overview_{target_date.date()}.png"
            },
            "config_snapshot": gate_config.snapshot()
        }
        
        with open(OUTPUTS_DIR / "run_audit.json", "w") as f:
            json.dump(audit, f, indent=2)
        
        print(f"\n✓ Auditoría: run_audit.json")
        
        # 🚨 HARD-FAIL SI HAY FALLBACK (después de guardar audit)
        if macro_risk_fallback_count > 0:
            print(f"\n{'='*70}")
            print(f"🛑 CRITICAL FAILURE: macro_risk fallback detected")
            print(f"   Fallback count: {macro_risk_fallback_count:,} rows")
            print(f"   System MUST calculate real macro_risk")
            print(f"   Aborting to prevent silent degradation...")
            print(f"{'='*70}")
            import sys
            sys.exit(2)  # Exit code 2 = configuration error
        
        # 🚨 HARD-FAIL/Soft-fail según MODE y overlay activo
        if gap_overlay_active and gap_unavailable_pct > gate_config.GAP_UNAVAILABLE_PCT_HARDFAIL:
            if gate_config.MODE.upper() == "PROD" or gate_config.STRICT_MODE:
                print(f"\n{'='*70}")
                print(f"🛑 GAP OVERLAY UNRELIABLE: {gap_unavailable_pct:.2f}% rows without gap")
                print(f"   available_rows={gap_available_rows:,} | unavailable_rows={gap_unavailable_rows:,}")
                print(f"   MODE=PROD / STRICT={gate_config.STRICT_MODE} → Aborting...")
                print(f"{'='*70}")
                import sys
                sys.exit(3)  # Exit code 3 = overlay data quality error
            else:
                print(f"\n{'='*70}")
                print(f"⚠️ GAP OVERLAY UNRELIABLE: {gap_unavailable_pct:.2f}% rows without gap")
                print(f"   available_rows={gap_available_rows:,} | unavailable_rows={gap_unavailable_rows:,}")
                print(f"   MODE=DEV / STRICT={gate_config.STRICT_MODE} → Continuing without abort")
                print(f"{'='*70}")
    
    print(f"\n{'='*70}")
    print(f"✅ ORCHESTRATOR COMPLETADO")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
