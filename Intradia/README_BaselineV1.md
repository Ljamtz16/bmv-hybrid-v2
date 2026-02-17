# Baseline Intradía v1 — Cómo correr

Fecha: 2026-02-10

## Requisitos
- Datos 15m en:
  - data/us/intraday_15m/consolidated_15m.parquet (preferido)
  - o data/us/intraday_15m/consolidated_15m.csv

## Scripts
- Generar señales baseline (opcional):
  - intraday_v2/01b_build_baseline_signals.py
- Ejecutar backtest baseline v1:
  - intraday_v2/06b_execute_baseline_backtest.py
- Entrenar ProbWin v1 (walk-forward mensual OOS):
  - intraday_v2/04b_train_probwin_v1.py

## Ejecución (Windows)
1) Señales (opcional):
   - Ejecuta el script 01b. Genera:
     - intraday_v2/artifacts/baseline_v1/baseline_signals.parquet
     - intraday_v2/artifacts/baseline_v1/baseline_signals.csv

2) Backtest baseline v1:
   - Ejecuta el script 06b. Genera:
     - intraday_v2/artifacts/baseline_v1/trades.csv
     - intraday_v2/artifacts/baseline_v1/equity_daily.csv
     - intraday_v2/artifacts/baseline_v1/monthly_table.csv
     - intraday_v2/artifacts/baseline_v1/summary_ticker_year_hour.csv

3) ProbWin v1 (entrenamiento y outputs):
   - Ejecuta el script 04b. Genera:
     - intraday_v2/models/probwin_v1.joblib
     - intraday_v2/artifacts/probwin_v1/oos_predictions.csv
     - intraday_v2/artifacts/probwin_v1/oos_metrics_by_month.csv
     - intraday_v2/artifacts/probwin_v1/coeffs.csv

## Parámetros clave (Baseline v1)
- Señal: close[t] > max(high[t-4:t-1])
- Entry: open[t+1]
- SL/TP: 1×ATR14 / 1.5×ATR14
- EOD exit si no toca TP/SL
- Filtros: core tickers [SPY, QQQ, GS, JPM, CAT] + horas 09:30–11:30 y 15:00–16:00 NY
- Risk: equity inicial 2000, 0.75% riesgo, max_open=2, daily_stop=-2R

## ProbWin v1 (gate defensivo)
- Features en entry: ret1, ret4, vol4, vol_z20, atr_ratio, body_pct, hour_bucket, ticker one-hot.
- Walk-forward mensual OOS: train = meses < M, test = mes M.
- Threshold default: 0.55.
- Gating selectivo en backtest baseline:
  - No aplica a core tickers en 09:30–10:30.
  - Aplica a NVDA/AMD siempre.
  - Aplica a horas borderline 10:30–11:30 y 15:00–16:00.
- trades.csv incluye: probwin, allowed, block_reason, threshold, model_version.

## Notas de reproducibilidad
- TZ convertida a America/New_York para sesión y hour_bucket.
- ATR14 usa solo barras previas al entry.
- Sin uso de ventanas agregadas (w_open/w_close).
