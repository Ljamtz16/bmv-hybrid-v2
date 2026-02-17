# GapReport — Auditoría técnica Intradía

Fecha: 2026-02-10

## A) Mapa del pipeline actual (datos → señales → ejecución → backtest → métricas → artefactos)

1) **Datos intradía (15m)**
   - Fuente usada: consolidated_15m.parquet (no CSV en el pipeline).
   - Normalización TZ y columnas en: [intraday_v2/01_build_intraday_windows.py](intraday_v2/01_build_intraday_windows.py#L1-L200), [intraday_v2/06_execute_intraday_backtest.py](intraday_v2/06_execute_intraday_backtest.py#L1-L120).

2) **Barras diarias (OHLC)**
   - Se derivan desde 15m: [intraday_v2/00_build_daily_bars.py](intraday_v2/00_build_daily_bars.py#L1-L200).
   - Artefacto: artifacts/daily_bars.parquet.

3) **Régimen diario**
   - ATR/EMA/flags + prev features: [intraday_v2/02_build_regime_table.py](intraday_v2/02_build_regime_table.py#L1-L260).
   - Artefacto: artifacts/regime_table.parquet.

4) **Ventanas intradía (OPEN/CLOSE)**
   - Agregación por ventanas horarias: [intraday_v2/01_build_intraday_windows.py](intraday_v2/01_build_intraday_windows.py#L60-L190).
   - Artefacto: artifacts/intraday_windows.parquet.

5) **Dataset ML (labeling TP/SL)**
   - Labeling sobre ventanas + ATR prev: [intraday_v2/03_build_intraday_dataset.py](intraday_v2/03_build_intraday_dataset.py#L1-L230).
   - Artefacto: artifacts/intraday_ml_dataset.parquet.

6) **Entrenamiento ProbWin (Logistic Regression)**
   - Split temporal simple (train/val fijo): [intraday_v2/04_train_intraday_model.py](intraday_v2/04_train_intraday_model.py#L1-L240).
   - Artefactos: models/intraday_probwin_model.pkl, models/intraday_feature_columns.json, evidence/train_intraday_report.json.

7) **Plan intradía (gates + probabilidad)**
   - Gates por régimen + umbral de modelo (global): [intraday_v2/05_generate_intraday_plan.py](intraday_v2/05_generate_intraday_plan.py#L1-L260).
   - Artefactos: artifacts/intraday_plan.csv, artifacts/intraday_plan_clean.csv.

8) **Backtest**
   - Simulación TP/SL/timeout + daily stop: [intraday_v2/06_execute_intraday_backtest.py](intraday_v2/06_execute_intraday_backtest.py#L1-L260).
   - Artefactos: artifacts/intraday_trades.csv, artifacts/intraday_equity_curve.csv, artifacts/intraday_metrics.json.

9) **Métricas agregadas**
   - PF/WR/MaxDD + buckets de probabilidad: [intraday_v2/07_compute_intraday_metrics.py](intraday_v2/07_compute_intraday_metrics.py#L1-L220).
   - Artefacto: artifacts/intraday_weekly.csv.

10) **Sweep de thresholds**
   - Barrido de umbrales + backtest: [intraday_v2/08_sweep_thresholds.py](intraday_v2/08_sweep_thresholds.py#L1-L200).
   - Artefactos: artifacts/sweep/*.

## B) Checklist vs pipeline objetivo (Baseline Intradía v1 + ProbWin)

- [ ] **Fuente de datos = consolidated_15m.csv**
  - Actual: usa consolidated_15m.parquet. No hay conversión CSV→Parquet documentada.
  - Evidencia: [intraday_v2/00_build_daily_bars.py](intraday_v2/00_build_daily_bars.py#L1-L40), [intraday_v2/01_build_intraday_windows.py](intraday_v2/01_build_intraday_windows.py#L1-L40).

- [ ] **Baseline breakout (close rompe high últimas 4 velas) + entrada open siguiente vela**
  - Actual: no hay lógica de breakout ni entrada en siguiente open; se usa agregación por ventanas y entry en w_open.
  - Evidencia: [intraday_v2/01_build_intraday_windows.py](intraday_v2/01_build_intraday_windows.py#L100-L180), [intraday_v2/05_generate_intraday_plan.py](intraday_v2/05_generate_intraday_plan.py#L150-L230).

- [ ] **SL/TP = 1×ATR14 y 1.5×ATR14 + EOD exit**
  - Actual: tp_mult=0.8, sl_mult=0.6, time_stop_bars=16; no EOD explícito.
  - Evidencia: [intraday_v2/03_build_intraday_dataset.py](intraday_v2/03_build_intraday_dataset.py#L40-L200), [intraday_v2/05_generate_intraday_plan.py](intraday_v2/05_generate_intraday_plan.py#L30-L220), [intraday_v2/06_execute_intraday_backtest.py](intraday_v2/06_execute_intraday_backtest.py#L120-L220).

- [ ] **Filtros: core tickers y hours NY 09:30–11:30 + 15:00–16:00**
  - Actual: ventanas OPEN 09:30–10:30 y CLOSE 14:00–15:00; no core list; no hour gate.
  - Evidencia: [intraday_v2/01_build_intraday_windows.py](intraday_v2/01_build_intraday_windows.py#L98-L150).

- [ ] **Risk mgmt: equity = 2000, 0.75% riesgo, max_open=2, daily stop -2R**
  - Actual: PnL por share, sin sizing por equity, sin max_open, daily stop por SL count y r_limit=-1.0.
  - Evidencia: [intraday_v2/06_execute_intraday_backtest.py](intraday_v2/06_execute_intraday_backtest.py#L1-L200).

- [ ] **ProbWin v1 features (ret1, ret4, vol4, vol_z, atr_ratio, body_pct, hour_bucket, ticker one-hot)**
  - Actual: features de ventana + régimen (ema/atr/flags) y one-hot de ventana; no ret1/ret4/vol_z/hour_bucket/ticker one-hot.
  - Evidencia: [intraday_v2/03_build_intraday_dataset.py](intraday_v2/03_build_intraday_dataset.py#L90-L170), [intraday_v2/04_train_intraday_model.py](intraday_v2/04_train_intraday_model.py#L40-L120).

- [ ] **Walk-forward mensual OOS**
  - Actual: split fijo train_end_date/val_start_date (no walk-forward mensual).
  - Evidencia: [intraday_v2/04_train_intraday_model.py](intraday_v2/04_train_intraday_model.py#L20-L110).

- [ ] **Threshold default 0.55 + integración selectiva (NVDA/AMD y horas borderline)**
  - Actual: threshold global (default 0.70) y gate modelo aplicado a todos tras régimen.
  - Evidencia: [intraday_v2/05_generate_intraday_plan.py](intraday_v2/05_generate_intraday_plan.py#L20-L140).

- [ ] **Salidas: tabla mensual, equity curve diaria, resumen por ticker/año/hora, PDF maestro**
  - Actual: equity por trade, weekly summary, metrics JSON; no tabla mensual ni PDF.
  - Evidencia: [intraday_v2/06_execute_intraday_backtest.py](intraday_v2/06_execute_intraday_backtest.py#L220-L260), [intraday_v2/07_compute_intraday_metrics.py](intraday_v2/07_compute_intraday_metrics.py#L120-L220).

- [ ] **Auditoría por trade con campos completos (probwin, allowed/blocked, block_reason, etc.)**
  - Actual: trades.csv no incluye probwin ni block_reason ni allowed/blocked.
  - Evidencia: [intraday_v2/06_execute_intraday_backtest.py](intraday_v2/06_execute_intraday_backtest.py#L60-L190).

## C) Prioridad: faltantes vs ya implementado (con evidencia)

### Ya implementado (parcial o equivalente)
1) **ETL diario y régimen con anti-leakage**
   - Prev features (shift) para evitar fuga: [intraday_v2/02_build_regime_table.py](intraday_v2/02_build_regime_table.py#L120-L210).
2) **Labeling TP/SL con TP/SL conservador**
   - Evaluación TP/SL y timeout: [intraday_v2/03_build_intraday_dataset.py](intraday_v2/03_build_intraday_dataset.py#L120-L210).
3) **Backtest con TP/SL + daily stop (parcial)**
   - Daily stop por SL count y R limit: [intraday_v2/06_execute_intraday_backtest.py](intraday_v2/06_execute_intraday_backtest.py#L20-L140).
4) **Métricas básicas (PF, WR, DD)**
   - Cálculo de PF/WR/DD: [intraday_v2/07_compute_intraday_metrics.py](intraday_v2/07_compute_intraday_metrics.py#L30-L140).

### Faltantes (priorizados)
1) **Baseline breakout real (4 velas) + entrada en open siguiente vela**
   - No existe en repo; requiere nueva lógica de señal en 15m.
2) **Hour gate correcto + core tickers**
   - Ventanas actuales no cumplen horarios objetivo.
3) **Risk mgmt con sizing por equity + max_open=2**
   - Backtest no calcula tamaño de posición ni controla concurrencia.
4) **ProbWin features + walk-forward mensual**
   - Features y entrenamiento difieren del objetivo.
5) **Integración selectiva ProbWin (solo NVDA/AMD y horas borderline)**
   - Actualmente se aplica global con threshold fijo.
6) **Auditoría completa por trade**
   - Falta logging de allowed/blocked y block_reason.
7) **Outputs del objetivo (monthly table, daily equity, PDF)**
   - No están implementados.

## D) Riesgos detectados

1) **Look-ahead en ventanas**
   - `w_*` agrega toda la ventana y se usa como señal/entrada, lo que incorpora datos futuros respecto a la entrada. Riesgo alto de leakage.
   - Evidencia: [intraday_v2/01_build_intraday_windows.py](intraday_v2/01_build_intraday_windows.py#L100-L180), [intraday_v2/05_generate_intraday_plan.py](intraday_v2/05_generate_intraday_plan.py#L150-L230).

2) **Timezone: parseo de entry_time como UTC**
   - `entry_time` se guarda sin TZ y luego se parsea con `utc=True` en backtest; riesgo de shift si el CSV está en hora NY.
   - Evidencia: [intraday_v2/05_generate_intraday_plan.py](intraday_v2/05_generate_intraday_plan.py#L170-L220), [intraday_v2/06_execute_intraday_backtest.py](intraday_v2/06_execute_intraday_backtest.py#L30-L80).

3) **Sampling/selection bias por gates de régimen**
   - Filtra días “operables” y luego aplica modelo; no corresponde al baseline objetivo.
   - Evidencia: [intraday_v2/05_generate_intraday_plan.py](intraday_v2/05_generate_intraday_plan.py#L120-L170).

4) **No EOD exit real**
   - Time-stop por número de velas, no cierre de sesión. Puede variar por huecos/feriados.
   - Evidencia: [intraday_v2/03_build_intraday_dataset.py](intraday_v2/03_build_intraday_dataset.py#L120-L210), [intraday_v2/06_execute_intraday_backtest.py](intraday_v2/06_execute_intraday_backtest.py#L120-L210).

5) **ProbWin fuera de especificación**
   - Features y entrenamiento no son los definidos. Afecta comparabilidad con objetivo.
   - Evidencia: [intraday_v2/04_train_intraday_model.py](intraday_v2/04_train_intraday_model.py#L40-L140).

## E) Recomendaciones exactas (cambios mínimos) para reproducibilidad 100%

1) **Crear script de baseline intradía (señal 4-velas)**
   - Nuevo módulo (p. ej., 01b_build_baseline_signals.py) que genere señales en 15m usando solo barras previas y calcule entry_time = siguiente vela.
2) **Reemplazar ventanas por hour gate explícito**
   - Usar timestamps 15m en NY, filtrar 09:30–11:30 y 15:00–16:00; bloquear 12:00–14:00.
3) **Implementar TP/SL objetivo y EOD exit**
   - En backtest: si no toca TP/SL, cerrar en última vela del día (NY) y registrar exit_reason=EOD.
4) **Sizing por equity y max_open=2**
   - En backtest: mantener equity, calcular size = equity * 0.0075 / (|entry-sl|), y limitar trades concurrentes a 2.
5) **ProbWin v1 con features correctas + walk-forward mensual**
   - Construir features exactas en dataset, entrenar por mes (train < M, test = M), almacenar probas por trade.
6) **Integración selectiva ProbWin**
   - Aplicar ProbWin solo a NVDA/AMD y horas borderline; core + 09:30–10:30 sin filtro.
7) **Auditoría completa**
   - Añadir a trades.csv: probwin, allowed, block_reason, hour_bucket, atr14, sl, tp, exit_reason.
8) **Outputs objetivo**
   - Generar equity curve diaria, tabla mensual, resumen por ticker/año/hora y PDF maestro.

## Cambios mínimos propuestos (lista concreta)

1) Nuevo script `01b_build_baseline_signals.py` con señal breakout 4 velas y `entry_time` en siguiente vela.
2) Modificar `05_generate_intraday_plan.py` para usar señales baseline + filtros objetivo (core tickers + hour gate), sin gates de régimen.
3) Modificar `06_execute_intraday_backtest.py` para sizing por equity, max_open=2, daily stop -2R y EOD exit.
4) Nuevo script `03b_build_probwin_features.py` para features ProbWin v1 y labels TP/SL/EOD.
5) Modificar `04_train_intraday_model.py` a walk-forward mensual y threshold default 0.55.
6) Modificar `07_compute_intraday_metrics.py` para tabla mensual y resúmenes por ticker/año/hora.
7) Nuevo script `09_build_master_pdf.py` para PDF maestro desde artefactos.

## Riesgos detectados (resumen)

- Look-ahead en ventanas OPEN/CLOSE.
- Parseo de timezone potencialmente incorrecto en `entry_time`.
- Selección de días por régimen fuera del baseline.
- Time-stop vs EOD.

## Plan de implementación en 5 pasos

1) Implementar baseline signals + hour gate (sin ML) y validar PF/WR.
2) Actualizar backtest con sizing, max_open y daily stop -2R.
3) Construir ProbWin v1 features y walk-forward mensual.
4) Integrar ProbWin selectivo con threshold 0.55.
5) Generar outputs finales y PDF maestro con logs auditables.
