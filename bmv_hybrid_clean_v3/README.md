# BMV Hybrid V2 - Clean Zero (v3)

## Resumen (ES)
Sistema hibrido de trading cuantitativo con dos capas: senales diarias basadas en modelos ML y ejecucion intradia con control de riesgo. El pipeline incluye generacion de features, calibracion de umbrales por PnL y validacion mensual. El despliegue objetivo es desktop + Raspberry Pi para monitoreo continuo.

## Summary (EN)
Hybrid quantitative trading system with two layers: daily ML-based signals and intraday execution with risk controls. The pipeline covers feature engineering, PnL-based threshold calibration, and monthly validation. The target deployment is desktop + Raspberry Pi for continuous monitoring.

## Quick Start
1) Install dependencies:
```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```
2) Set local environment variables as needed (do not commit .env).
3) Run the core pipeline:
```
python scripts/01_download_data.py
python scripts/02_build_features.py
python scripts/04_generate_signals.py
python scripts/05_calibrate_thresholds.py
python scripts/06_backtest_eval.py
```

## Data Layout
```
data/
  raw/
    1d/
    1h/
models/
reports/
config/
```

## Key Scripts
- Data: scripts/01_download_data.py
- Features: scripts/02_build_features.py
- Signals: scripts/04_generate_signals.py
- Calibration: scripts/05_calibrate_thresholds.py
- Backtest: scripts/06_backtest_eval.py

## Operations and Deployment
- Architecture and RPi flow: [ARCHITECTURE.md](ARCHITECTURE.md)
- Operational index and setup: [INDEX.md](INDEX.md)

## Notes
- Data and trained models are excluded from version control.
- Use environment variables for credentials.
- This project is for research and paper-trading contexts.
