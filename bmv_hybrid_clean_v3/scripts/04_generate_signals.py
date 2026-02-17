import os, pandas as pd
from src.config import load_cfg
from src.io.loader import load_daily_map
from src.features.indicators import ensure_atr_14
from src.models.adapters import LSTMSim
from src.signals.generate import generate_daily_signals

if __name__ == "__main__":
    cfg = load_cfg("config/base.yaml")
    d1_map = load_daily_map(os.path.join(cfg.data_dir,"raw","1d"), cfg.tickers)
    for t in d1_map: d1_map[t] = ensure_atr_14(d1_map[t])

    rf = svm = None
    try:
        import joblib
        if os.path.exists(cfg.models["rf_path"]): rf = joblib.load(cfg.models["rf_path"])
        if os.path.exists(cfg.models["svm_path"]): svm = joblib.load(cfg.models["svm_path"])
    except Exception as e:
        print("⚠️ No RF/SVM:", e)

    lstm = LSTMSim()
    cal_start = pd.Timestamp(cfg.calibration["start"]); cal_end = pd.Timestamp(cfg.calibration["end"])
    dates_cal = [d for d in d1_map[cfg.tickers[0]].index if (cal_start <= d < cal_end)]

    sig = generate_daily_signals(d1_map, rf, svm, lstm, 0.0, 0.0, cfg.tickers, dates_cal, (0.5,0.3,0.2))
    os.makedirs(cfg.reports_dir, exist_ok=True)
    sig.to_csv(os.path.join(cfg.reports_dir,"signals_cal_raw.csv"), index=False)
    print("✅ Señales 2024 generadas en reports/signals_cal_raw.csv")
