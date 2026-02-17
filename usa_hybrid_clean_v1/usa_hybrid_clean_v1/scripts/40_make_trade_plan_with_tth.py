"""
Script: 40_make_trade_plan_with_tth.py
Genera trade_plan ordenado por eficiencia temporal (E[PnL]/ETTH_proxy) usando señales calibradas.
Funciona sin modelo TTH todavía; usa proxy basado en ATR%.
"""
import numpy as np
import pandas as pd
from pathlib import Path
import os
from hashlib import md5
from zoneinfo import ZoneInfo
from pandas.tseries.offsets import BusinessDay
import yaml
import json
from datetime import datetime

SIGNALS_IN  = Path("data/daily/signals_with_gates.parquet")  # salida de 11_infer_and_gate.py
PLAN_OUT    = Path("val/trade_plan.csv")
AUDIT_OUT   = Path("val/trade_plan_audit.parquet")

# Parámetros (mover a policies.yaml si se requiere más adelante)
MIN_PROB = {"low_vol": 0.60, "med_vol": 0.62, "high_vol": 0.65}
RISK_CFG = {"max_open": 8, "max_per_ticker": 2, "cooldown_days": 2}

# Sizing configuration
ACCOUNT_CASH = 1000.0  # Total available capital
PER_TRADE = 250.0      # Target cash per position
FEE_PCT = 0.0005       # 5 bps round-trip cost estimate

# Sector caps
SECTOR_CAP = 0.50      # Max 50% exposure per sector
SECTOR_MAP = {
    'NVDA': 'Semiconductors', 'AMD': 'Semiconductors', 'INTC': 'Semiconductors',
    'AAPL': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology', 'META': 'Technology',
    'JPM': 'Financials', 'MS': 'Financials', 'BAC': 'Financials', 'WFC': 'Financials',
    'XOM': 'Energy', 'CVX': 'Energy', 'COP': 'Energy',
    'WMT': 'Consumer', 'HD': 'Consumer', 'MCD': 'Consumer'
}

# Model version for traceability
MODEL_VERSION = "Baseline-Calibrated-Q4-2025"

# Columnas del plan (también usadas para escribir header-only si no hay filas)
PLAN_COLS = [
    "ticker", "sector", "regime", "prob_win_cal", "entry_price",
    "tp_price", "sl_price", "qty", "position_cash", "total_exposure",
    "exp_pnl", "exp_pnl_net", "exp_pnl_cash", "etth_days", "epnl_time",
    "signal_timestamp", "valid_until", "model_version",
    "asof_date", "model_hash", "calibration_version", "thresholds_applied",
    "data_freshness_date", "entry_source", "risk_level"
]

def enable_utf8_output():
    """Fuerza stdout/stderr a UTF-8 para evitar UnicodeEncodeError en Windows."""
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def write_header_only_plan(path: Path):
    """Escribe un CSV sólo con encabezados (sin filas) para evitar EmptyDataError."""
    import io
    path.parent.mkdir(parents=True, exist_ok=True)
    # Usar pandas para garantizar formato consistente
    pd.DataFrame(columns=PLAN_COLS).to_csv(path, index=False)


def load_calendar_risk(today: pd.Timestamp) -> tuple[str, list[str]]:
    """Determina el nivel de riesgo del día leyendo data/calendar.
    Retorna (risk_level, reasons).
    """
    cal_dir = Path("data/calendar")
    y = today.year
    holidays_path = cal_dir / f"nyse_holidays_{y}.json"
    events_path = cal_dir / f"events_{y}.csv"
    is_weekend = today.weekday() >= 5
    reasons: list[str] = []

    # Holidays
    is_holiday = False
    if holidays_path.exists():
        try:
            h = json.loads(holidays_path.read_text(encoding="utf-8"))
            hols = h.get("holidays", [])
            hol_map = {}
            for item in hols:
                if isinstance(item, str):
                    hol_map[item] = "Holiday"
                elif isinstance(item, dict):
                    dt = item.get("date")
                    nm = item.get("name") or "Holiday"
                    if dt:
                        hol_map[str(dt)] = str(nm)
            is_holiday = today.strftime("%Y-%m-%d") in hol_map
            if is_holiday:
                reasons.append(f"Holiday: {hol_map[today.strftime('%Y-%m-%d')]}")
        except Exception:
            pass

    # Events
    events: list[dict] = []
    if events_path.exists():
        try:
            df_ev = pd.read_csv(events_path)
            if "date" in df_ev.columns:
                events = df_ev[df_ev["date"] == today.strftime("%Y-%m-%d")].to_dict(orient="records")
        except Exception:
            events = []

    # Risk level
    has_high = any(str(e.get("importance", "")).lower() == "high" for e in events)
    has_med = any(str(e.get("importance", "")).lower() == "medium" for e in events)
    if has_high:
        risk = "high"
    elif has_med:
        risk = "medium"
    else:
        risk = "low"

    # Weekend closes market but we care about impact; keep risk but add reason
    if is_weekend and not is_holiday:
        reasons.append("Weekend")

    # Add top reasons for display
    for e in events:
        desc = str(e.get("description", "Evento"))
        t = str(e.get("time_et", ""))
        tk = str(e.get("ticker", ""))
        imp = str(e.get("importance", "")).lower()
        if imp in {"high", "medium"}:
            reasons.append(((t + " ET - ") if t else "") + (f"[{tk}] " if tk else "") + desc)

    return risk, reasons[:5]

def expected_pnl(row: pd.Series) -> float:
    """Estimación simple de pnl esperado con TP/SL adaptativo si no presentes.
    gain = p * (tp%); loss = (1-p) * (loss%). Loss se penaliza.
    """
    p = float(row.get("prob_win_cal", np.nan))
    if not np.isfinite(p):
        return np.nan
    entry = row.get("close", row.get("entry_price", np.nan))
    # Si ya vienen precios de tp/sl usar esos
    tp_price = row.get("tp_price", np.nan)
    sl_price = row.get("sl_price", np.nan)
    if np.isfinite(tp_price) and np.isfinite(sl_price) and np.isfinite(entry):
        gain = tp_price/entry - 1.0
        loss = 1.0 - sl_price/entry
    else:
        # Adaptativo por régimen usando atr_pct si disponible
        atr_pct = row.get("atr_pct", row.get("atr_pct_w", np.nan))
        if not np.isfinite(atr_pct):
            # fallback atr_14d/close.shift(1) si existe prev_close
            atr = row.get("atr_14d", np.nan)
            prev_close = row.get("prev_close", np.nan)
            if np.isfinite(atr) and np.isfinite(prev_close) and prev_close > 0:
                atr_pct = atr / prev_close
            else:
                atr_pct = 0.01  # fallback
        k_map = {"low_vol": 1.0, "med_vol": 1.3, "high_vol": 1.6}
        k = k_map.get(row.get("regime"), 1.2)
        gain = k * atr_pct
        loss = 0.7 * k * atr_pct
    return p * gain - (1 - p) * loss

def etth_proxy_days(row: pd.Series) -> float:
    """Proxy de tiempo hasta evento usando función inversa del ATR%.
    Cap a [0.1, 10] días para estabilidad.
    """
    atr_pct = row.get("atr_pct", row.get("atr_pct_w", np.nan))
    if not np.isfinite(atr_pct):
        atr = row.get("atr_14d", np.nan)
        prev_close = row.get("prev_close", np.nan)
        if np.isfinite(atr) and np.isfinite(prev_close) and prev_close > 0:
            atr_pct = atr / prev_close
        else:
            atr_pct = 0.01
    c1, c2 = 0.05, 15.0
    proxy = 1.0 / max(c1 + c2 * atr_pct, 1e-4)
    return float(np.clip(proxy, 0.1, 10.0))

def compute_tp_sl_prices(row: pd.Series) -> tuple:
    """Calcula TP/SL usando régimen y ATR%."""
    entry = row.get("entry_price", row.get("close", np.nan))
    if not np.isfinite(entry):
        return np.nan, np.nan
    
    atr_pct = row.get("atr_pct", row.get("atr_pct_w", np.nan))
    if not np.isfinite(atr_pct):
        atr = row.get("atr_14d", np.nan)
        prev_close = row.get("prev_close", np.nan)
        if np.isfinite(atr) and np.isfinite(prev_close) and prev_close > 0:
            atr_pct = atr / prev_close
        else:
            atr_pct = 0.01
    
    k_map = {"low_vol": 1.0, "med_vol": 1.3, "high_vol": 1.6}
    k = k_map.get(row.get("regime"), 1.2)
    
    tp_price = entry * (1 + k * atr_pct)
    sl_price = entry * (1 - 0.7 * k * atr_pct)
    
    return float(tp_price), float(sl_price)

def load_health_report():
    """Carga el último health report para ajustar gates dinámicamente."""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    health_path = Path(f"reports/health/daily_health_{today}.json")
    
    if not health_path.exists():
        return None
    
    try:
        import json
        with open(health_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] No se pudo leer health report: {e}")
        return None

def adjust_thresholds_by_health(min_prob_map, health_report):
    """Ajusta thresholds dinámicamente según coverage y ECE del health report."""
    if not health_report:
        return min_prob_map
    
    adjusted = dict(min_prob_map)
    coverage_pct = health_report.get('metrics', {}).get('coverage', {}).get('coverage_pct', 0)
    ece = health_report.get('metrics', {}).get('quality', {}).get('ece')
    
    # Coverage muy alta → gates más restrictivos
    if coverage_pct > 35:
        adjustment = 0.01
        print(f"[HEALTH] Coverage {coverage_pct:.1f}% > 35% → subiendo thresholds +{adjustment}")
        for k in adjusted:
            adjusted[k] = min(adjusted[k] + adjustment, 0.75)
    
    # Coverage muy baja → gates más permisivos
    elif coverage_pct < 15:
        adjustment = -0.01
        print(f"[HEALTH] Coverage {coverage_pct:.1f}% < 15% → bajando thresholds {adjustment}")
        for k in adjusted:
            adjusted[k] = max(adjusted[k] + adjustment, 0.50)
    
    # ECE alto → recomendar recalibración pero mantener gates
    if ece and ece > 0.07:
        print(f"[HEALTH] ⚠️ ECE {ece:.4f} > 0.07 → Recalibración recomendada")
    
    return adjusted

def main():
    enable_utf8_output()
    if not SIGNALS_IN.exists():
        print(f"[WARN] No existe {SIGNALS_IN}")
        # Aun así escribir header-only para que validaciones no fallen por CSV vacío
        write_header_only_plan(PLAN_OUT)
        return
    df = pd.read_parquet(SIGNALS_IN).copy()
    # Crear entrada_price estándar si no existe
    if 'entry_price' not in df.columns:
        df['entry_price'] = df.get('close', np.nan)

    # Alias robusto para probabilidad calibrada
    if 'prob_win_cal' not in df.columns:
        for alt in ['prob_win', 'prob', 'yhat', 'y_hat']:
            if alt in df.columns:
                df['prob_win_cal'] = df[alt]
                print(f"[INFO] Usando alias para prob_win_cal -> {alt}")
                break
    # Cargar política si existe para thresholds por régimen
    policy_path = Path('config/policies.yaml')
    min_prob_map = dict(MIN_PROB)
    if policy_path.exists():
        try:
            with open(policy_path, 'r', encoding='utf-8') as f:
                pol = yaml.safe_load(f)
            thr = pol.get('thresholds', {}).get('prob_threshold', {})
            if isinstance(thr, dict) and thr:
                min_prob_map.update(thr)
                print(f"[INFO] Thresholds base de política: {min_prob_map}")
        except Exception as e:
            print(f"[WARN] No se pudo leer política: {e}")
    
    # Ajustar thresholds según health report
    health_report = load_health_report()
    min_prob_map = adjust_thresholds_by_health(min_prob_map, health_report)
    if health_report:
        print(f"[INFO] Thresholds ajustados por health: {min_prob_map}")

    # Ajustes por riesgo de calendario (semáforo)
    ny = ZoneInfo("America/New_York")
    today_ny = pd.Timestamp.now(tz=ny).normalize()
    risk_level, risk_reasons = load_calendar_risk(today_ny)
    per_trade_used = PER_TRADE
    max_open_used = RISK_CFG['max_open']
    risk_note = ""
    if risk_level == "high":
        per_trade_used = max(50.0, PER_TRADE * 0.5)
        max_open_used = max(1, int(round(RISK_CFG['max_open'] * 0.5)))
        for k in min_prob_map:
            min_prob_map[k] = min(min_prob_map[k] + 0.01, 0.8)
        risk_note = "risk=high: per_trade x0.5, max_open x0.5, thresholds +0.01"
    elif risk_level == "medium":
        per_trade_used = max(50.0, PER_TRADE * 0.8)
        max_open_used = max(1, min(RISK_CFG['max_open'], RISK_CFG['max_open'] - 2))
        for k in min_prob_map:
            min_prob_map[k] = min(min_prob_map[k] + 0.005, 0.8)
        risk_note = "risk=medium: per_trade x0.8, max_open -2, thresholds +0.005"
    else:
        risk_note = "risk=low: sin ajustes"
    print(f"[RISK] Calendario hoy: {risk_level.upper()} | {', '.join(risk_reasons) if risk_reasons else 'sin eventos relevantes'}")
    print(f"[RISK] Ajustes aplicados -> {risk_note}")

    required = {"ticker", "regime", "prob_win_cal"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {missing}")

    # Gate defensivo por régimen
    df = df[df.apply(lambda r: r["prob_win_cal"] >= min_prob_map.get(r["regime"], 0.62), axis=1)].copy()
    if df.empty:
        print("No hay señales post-gate.")
        write_header_only_plan(PLAN_OUT)
        return

    # Métricas para ranking
    df['exp_pnl'] = df.apply(expected_pnl, axis=1)
    df['etth_days'] = df.apply(etth_proxy_days, axis=1)
    df['epnl_time'] = df['exp_pnl'] / df['etth_days']

    # Sort inicial por eficiencia
    df = df.sort_values('epnl_time', ascending=False)

    # Dedupe inteligente: mejor señal por ticker (mayor epnl_time)
    print(f"[INFO] Antes de dedupe: {len(df)} señales")
    df = df.sort_values(['ticker', 'epnl_time'], ascending=[True, False])
    df = df.groupby('ticker', as_index=False).head(1)
    print(f"[INFO] Después de dedupe: {len(df)} señales únicas por ticker")
    
    # Re-sort tras dedupe
    df = df.sort_values('epnl_time', ascending=False)

    # Aplicar sector caps y risk guardrails
    df['sector'] = df['ticker'].map(SECTOR_MAP).fillna('Other')
    
    plan_rows = []
    open_by_ticker = {}
    exposure_by_sector = {}
    total_exposure = 0.0

    for _, r in df.iterrows():
        if len(plan_rows) >= max_open_used:
            break
        
        t = r['ticker']
        s = r['sector']
        
        # Ticker limit
        if open_by_ticker.get(t, 0) >= RISK_CFG['max_per_ticker']:
            continue
        
        # Calculate position size
        pos_cash = min(per_trade_used, ACCOUNT_CASH / max(1, max_open_used))
        qty = int(np.floor(pos_cash / r['entry_price']))
        if qty < 1:
            continue
        
        trade_exposure = qty * r['entry_price']
        
        # Sector cap check
        sector_exp = exposure_by_sector.get(s, 0.0)
        if sector_exp + trade_exposure > SECTOR_CAP * ACCOUNT_CASH:
            print(f"[SKIP] {t} ({s}): sector cap reached ({sector_exp:.0f} + {trade_exposure:.0f} > {SECTOR_CAP*ACCOUNT_CASH:.0f})")
            continue
        
        # Accept trade
        plan_rows.append(r)
        open_by_ticker[t] = open_by_ticker.get(t, 0) + 1
        exposure_by_sector[s] = sector_exp + trade_exposure
        total_exposure += trade_exposure

    plan = pd.DataFrame(plan_rows)
    
    if len(plan) == 0:
        print("[WARN] No hay trades tras aplicar caps y guardrails")
        write_header_only_plan(PLAN_OUT)
        return

    # Position sizing and executable quantities
    plan["position_cash"] = plan.apply(
        lambda r: min(per_trade_used, ACCOUNT_CASH / max(1, len(plan))), axis=1
    )
    plan["qty"] = np.floor(plan["position_cash"] / plan["entry_price"]).astype(int)
    plan = plan[plan["qty"] > 0].copy()
    
    # TP/SL prices
    tp_sl = plan.apply(compute_tp_sl_prices, axis=1, result_type='expand')
    plan["tp_price"] = tp_sl[0]
    plan["sl_price"] = tp_sl[1]
    
    # PnL calculations
    plan["exp_pnl_net"] = plan["exp_pnl"] - FEE_PCT
    plan["exp_pnl_cash"] = plan["position_cash"] * plan["exp_pnl_net"]
    plan["exp_pnl_cash_total"] = (plan["qty"] * plan["entry_price"]) * plan["exp_pnl_net"]
    plan["total_exposure"] = plan["qty"] * plan["entry_price"]
    
    # Metadata y trazabilidad (determinística por día)
    ny = ZoneInfo("America/New_York")
    today_ny = pd.Timestamp.now(tz=ny).normalize()
    asof_date = (today_ny - BusinessDay(1)).date()

    # Sellos determinísticos para idempotencia diaria
    plan["signal_timestamp"] = pd.Timestamp(asof_date)
    plan["valid_until"] = pd.Timestamp(asof_date) + pd.Timedelta(days=1)
    plan["model_version"] = MODEL_VERSION

    # Hash del modelo (meta-learner) y thresholds aplicados
    model_hash = "unknown"
    meta_path = Path("models/direction/meta.joblib")
    if meta_path.exists():
        try:
            model_hash = md5(meta_path.read_bytes()).hexdigest()[:10]
        except Exception:
            pass
    
    # Data freshness date (max date del CSV autoridad)
    csv_path = Path("data/us/ohlcv_us_daily.csv")
    data_freshness_date = str(asof_date)  # default
    if csv_path.exists():
        try:
            csv_df = pd.read_csv(csv_path)
            max_csv = pd.to_datetime(csv_df["date"], utc=True, errors="coerce").dt.tz_convert("America/New_York").dt.date.max()
            data_freshness_date = str(max_csv)
        except Exception:
            pass
    
    # Entry de autoridad: cruzar con último close CSV por ticker
    if csv_path.exists():
        try:
            csv_df = pd.read_csv(csv_path)
            csv_df["date"] = pd.to_datetime(csv_df["date"], utc=True)
            last_close = csv_df.sort_values("date").groupby("ticker").tail(1).set_index("ticker")["close"]
            plan["csv_last_close"] = plan["ticker"].map(last_close)
            plan["entry_diff_pct"] = (plan["entry_price"] - plan["csv_last_close"]) / plan["csv_last_close"]
            # Si difiere >0.5%, sustituir y anotar
            override_mask = plan["entry_diff_pct"].abs() > 0.005
            plan["entry_source"] = "signal"
            if override_mask.any():
                print(f"[INFO] {override_mask.sum()} entries ajustados desde CSV (>0.5% diff)")
                plan.loc[override_mask, "entry_price"] = plan.loc[override_mask, "csv_last_close"]
                plan.loc[override_mask, "entry_source"] = "csv_last_close"
                # Recalcular TP/SL para los ajustados
                for idx in plan[override_mask].index:
                    r = plan.loc[idx]
                    tp_new, sl_new = compute_tp_sl_prices(r)
                    plan.loc[idx, "tp_price"] = tp_new
                    plan.loc[idx, "sl_price"] = sl_new
        except Exception as e:
            plan["entry_source"] = "signal"
            print(f"[WARN] No se pudo aplicar entry de autoridad: {e}")
    else:
        plan["entry_source"] = "signal"
    
    plan["asof_date"] = str(asof_date)
    plan["model_hash"] = model_hash
    plan["calibration_version"] = MODEL_VERSION
    plan["thresholds_applied"] = str(min_prob_map)
    plan["risk_level"] = risk_level
    plan["data_freshness_date"] = data_freshness_date
    
    # Sector summary
    sector_summary = plan.groupby("sector")["total_exposure"].sum()

    # Auditoría completa
    AUDIT_OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(AUDIT_OUT, index=False)
    PLAN_OUT.parent.mkdir(parents=True, exist_ok=True)
    plan[PLAN_COLS].to_csv(PLAN_OUT, index=False)

    # Summary report
    print(f"\n{'='*60}")
    print(f"✅ Plan listo: {PLAN_OUT} ({len(plan)} señales)")
    print(f"{'='*60}")
    print(f"Capital disponible: ${ACCOUNT_CASH:.2f}")
    print(f"Exposición total: ${plan['total_exposure'].sum():.2f} ({plan['total_exposure'].sum()/ACCOUNT_CASH*100:.1f}%)")
    print(f"E[PnL] neto agregado (cash): ${plan['exp_pnl_cash'].sum():.2f}")
    print(f"E[PnL] neto agregado (%): {plan['exp_pnl_net'].sum():.2%}")
    print(f"Avg P(win): {plan['prob_win_cal'].mean():.3f}")
    print(f"Avg ETTH: {plan['etth_days'].mean():.2f} días")
    print(f"Riesgo calendario: {risk_level}")
    print(f"\nExposición por sector:")
    for sector, exp in sector_summary.items():
        pct = exp / plan['total_exposure'].sum() * 100
        print(f"  {sector}: ${exp:.2f} ({pct:.1f}%)")
    print(f"\n[INFO] Auditoría completa: {AUDIT_OUT}")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()
