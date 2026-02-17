import os, json, pandas as pd, yaml
from pathlib import Path
from src.config import load_cfg
from src.io.loader import load_daily_map, load_hourly_map
from src.features.indicators import ensure_atr_14
from src.models.adapters import LSTMSim
from src.signals.generate import generate_daily_signals
from src.calibrate.threshold import scan_tau_pnl

if __name__ == "__main__":
    # 📌 1. Cargar configuración
    cfg = load_cfg("config/base.yaml")
    sH, eH = cfg.session.split("-")
    tag = f"{sH.replace(':','')}_{eH.replace(':','')}"

    # 📌 2. Cargar datos diarios y horarios
    d1_map = load_daily_map(os.path.join(cfg.data_dir, "raw", "1d"), cfg.tickers)
    for t in d1_map:
        d1_map[t] = ensure_atr_14(d1_map[t])
    h1_map = load_hourly_map(os.path.join(cfg.data_dir, "raw", "1h"), cfg.tickers, session_tag=tag)

    # 📌 3. Cargar modelos
    rf = svm = None
    try:
        import joblib
        if os.path.exists(cfg.models["rf_path"]):
            rf = joblib.load(cfg.models["rf_path"])
        if os.path.exists(cfg.models["svm_path"]):
            svm = joblib.load(cfg.models["svm_path"])
    except Exception as e:
        print("⚠️ No RF/SVM:", e)
    lstm = LSTMSim()

    # 📌 4. Generar señales dentro del rango de calibración
    cal_start = pd.Timestamp(cfg.calibration["start"])
    cal_end = pd.Timestamp(cfg.calibration["end"])
    dates_cal = [d for d in d1_map[cfg.tickers[0]].index if (cal_start <= d < cal_end)]
    sig = generate_daily_signals(d1_map, rf, svm, lstm, 0.0, 0.0, cfg.tickers, dates_cal, (0.5, 0.3, 0.2))

    # 📌 5. Escanear τ y PnL
    grid = cfg.calibration["tau_grid"]
    exec_cfg = dict(
        tp_atr_mult=cfg.exec.tp_atr_mult,
        sl_atr_mult=cfg.exec.sl_atr_mult,
        commission_pct=cfg.exec.commission_pct,
        slippage_pct=cfg.exec.slippage_pct,
        max_holding_days=cfg.exec.max_holding_days,
        trail_atr_mult=cfg.exec.trail_atr_mult,
        trail_activation_atr=cfg.exec.trail_activation_atr,
        break_even_atr=cfg.exec.break_even_atr,
    )
    tau_buy, pnl_buy, scan_buy = scan_tau_pnl(sig, "BUY", h1_map, d1_map, grid, exec_cfg)
    tau_sell, pnl_sell, scan_sell = scan_tau_pnl(sig, "SELL", h1_map, d1_map, grid, exec_cfg)

    # 📌 6. Guardar resultados
    os.makedirs("models", exist_ok=True)
    with open("models/thresholds.json", "w", encoding="utf-8") as f:
        json.dump({"buy": tau_buy, "sell": tau_sell}, f, indent=2)

    scan_buy.to_csv(os.path.join(cfg.reports_dir, "tau_scan_buy.csv"), index=False)
    scan_sell.to_csv(os.path.join(cfg.reports_dir, "tau_scan_sell.csv"), index=False)
    print(f"✅ τ* BUY={tau_buy}  SELL={tau_sell}")

    # 📌 7. Guardar τ* directamente en config/base.yaml
    cfg_path = Path("config/base.yaml")
    with cfg_path.open("r", encoding="utf-8") as f:
        base = yaml.safe_load(f) or {}
    base.setdefault("calibration", {})["tau_star"] = {"BUY": float(tau_buy), "SELL": float(tau_sell)}
    with cfg_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(base, f, sort_keys=False, allow_unicode=True)
    print("📝 τ* guardado en config/base.yaml")
