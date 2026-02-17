# GapReport_Current — Auditoría técnica Intradía

Fecha: 2026-02-10

## Árbol (carpetas relevantes)
```
Intradia/
  data/us/intraday_15m/
  intraday_v2/
    00_build_daily_bars.py
    01_build_intraday_windows.py
    01b_build_baseline_signals.py
    02_build_regime_table.py
    03_build_intraday_dataset.py
    04_train_intraday_model.py
    04b_train_probwin_v1.py
    05_generate_intraday_plan.py
    06_execute_intraday_backtest.py
    06b_execute_baseline_backtest.py
    07_compute_intraday_metrics.py
    08_sweep_thresholds.py
    10_validate_baseline_v1.py
    artifacts/
    models/
```

## A) Mapa del pipeline actual (datos → señales → plan → backtest → métricas → artefactos)

### Pipeline intraday_v2 “ventanas + régimen + modelo” (legacy)
1) Datos 15m → ventanas OPEN/CLOSE
   - [intraday_v2/01_build_intraday_windows.py](intraday_v2/01_build_intraday_windows.py#L1-L200)
   - Artefacto: intraday_v2/artifacts/intraday_windows.parquet
2) Régimen diario (ATR/EMA/flags)
   - [intraday_v2/02_build_regime_table.py](intraday_v2/02_build_regime_table.py)
   - Artefacto: intraday_v2/artifacts/regime_table.parquet
3) Dataset ML (ventanas)
   - [intraday_v2/03_build_intraday_dataset.py](intraday_v2/03_build_intraday_dataset.py)
   - Artefacto: intraday_v2/artifacts/intraday_ml_dataset.parquet
4) Entrenamiento modelo intradía (split temporal fijo)
   - [intraday_v2/04_train_intraday_model.py](intraday_v2/04_train_intraday_model.py#L1-L200)
   - Artefactos: intraday_v2/models/intraday_probwin_model.pkl, intraday_v2/models/intraday_feature_columns.json
5) Plan intradía (gates régimen + probabilidad)
   - [intraday_v2/05_generate_intraday_plan.py](intraday_v2/05_generate_intraday_plan.py#L1-L240)
   - Artefactos: intraday_v2/artifacts/intraday_plan.csv, intraday_v2/artifacts/intraday_plan_clean.csv
6) Backtest del plan
   - [intraday_v2/06_execute_intraday_backtest.py](intraday_v2/06_execute_intraday_backtest.py#L1-L240)
   - Artefactos: intraday_v2/artifacts/intraday_trades.csv, intraday_v2/artifacts/intraday_equity_curve.csv, intraday_v2/artifacts/intraday_metrics.json

### Pipeline Baseline v1 + ProbWin (nuevo)
1) Datos 15m → señales baseline (breakout 4 velas)
   - [intraday_v2/01b_build_baseline_signals.py](intraday_v2/01b_build_baseline_signals.py#L1-L140)
   - Artefactos: intraday_v2/artifacts/baseline_v1/baseline_signals.parquet|csv
2) Backtest baseline v1 con sizing + max_open + daily stop
   - [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L1-L520)
   - Artefactos: intraday_v2/artifacts/baseline_v1/trades.csv, equity_daily.csv, monthly_table.csv, summary_ticker_year_hour.csv
3) ProbWin v1 (walk-forward mensual OOS)
   - [intraday_v2/04b_train_probwin_v1.py](intraday_v2/04b_train_probwin_v1.py#L1-L260)
   - Artefactos: intraday_v2/models/probwin_v1.joblib, intraday_v2/artifacts/probwin_v1/oos_predictions.csv, oos_metrics_by_month.csv, coeffs.csv

## B) Checklist vs Objetivo (✅/⚠️/❌)

| Requisito | Estado | Evidencia |
|---|---|---|
| Datos consolidated_15m.parquet/CSV | ✅ | [intraday_v2/01b_build_baseline_signals.py](intraday_v2/01b_build_baseline_signals.py#L1-L60), [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L30-L120) |
| Señal breakout 4 velas + entry open siguiente | ✅ | [intraday_v2/01b_build_baseline_signals.py](intraday_v2/01b_build_baseline_signals.py#L63-L110) |
| ATR14 en entry (sin futuro) | ✅ | [intraday_v2/01b_build_baseline_signals.py](intraday_v2/01b_build_baseline_signals.py#L63-L100) |
| SL=1×ATR, TP=1.5×ATR | ✅ | [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L70-L125) |
| EOD exit real | ⚠️ | Lógica EOD existe, pero validación falló en ejecución local (357 casos). Lógica: [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L90-L120) |
| Tie-break conservador SL primero | ✅ | [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L95-L112) |
| Filtros core tickers | ✅ | [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L210-L220) |
| Hour gate NY 09:30–11:30 y 15:00–16:00 | ✅ | [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L46-L70) |
| Risk: equity=2000, 0.75%, shares=floor(...) | ✅ | [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L135-L370) |
| max_open=2 | ✅ | [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L280-L292) |
| daily stop -2R | ✅ | [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L276-L286) |
| ProbWin v1 features correctas | ✅ | [intraday_v2/04b_train_probwin_v1.py](intraday_v2/04b_train_probwin_v1.py#L45-L160) |
| Walk-forward mensual OOS | ✅ | [intraday_v2/04b_train_probwin_v1.py](intraday_v2/04b_train_probwin_v1.py#L170-L230) |
| Threshold default 0.55 | ✅ | [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L140-L152) |
| ProbWin selectivo (core open no, NVDA/AMD sí, horas borderline sí) | ✅ | [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L290-L330) |
| trades.csv con campos completos | ✅ | [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L360-L398) |
| equity_daily.csv + monthly_table.csv + summary_ticker_year_hour.csv | ✅ | [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L400-L480) |
| PDF maestro | ❌ | No hay generador PDF en repo |
| blocked_trades.csv | ❌ | No existe salida dedicada |
| Logs reproducibles (seed/version/timestamp) | ⚠️ | Parcial: `model_version` existe en trades, pero no hay log de corrida |

## C) Top 10 gaps priorizados (con evidencia y cambio mínimo)

1) **EOD real falla en validación**
   - Importa: afecta comparabilidad con Baseline v1.
   - Evidencia: lógica EOD en [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L90-L120) pero validación local falló.
   - Cambio mínimo: normalizar TZ de `entry_time`/`exit_time` y asegurar última vela NY por `date_ny` en backtest.

2) **blocked_trades.csv no existe**
   - Importa: auditoría requerida por el objetivo.
   - Evidencia: `block_reason` se guarda en trades, pero no se exporta separado [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L360-L398).
   - Cambio mínimo: exportar `trades_df[allowed==False]` a artifacts/baseline_v1/blocked_trades.csv.

3) **PDF maestro no implementado**
   - Importa: entregable recomendado.
   - Evidencia: no hay script PDF en intraday_v2.
   - Cambio mínimo: nuevo script `09_build_master_pdf.py` usando outputs baseline_v1.

4) **Logs reproducibles incompletos**
   - Importa: auditoría y trazabilidad.
   - Evidencia: no hay archivo de “run metadata”.
   - Cambio mínimo: escribir `artifacts/baseline_v1/run_metadata.json` con timestamp, seed, versiones y paths.

5) **Pipeline legacy con ventanas sigue activo**
   - Importa: riesgo de confusión y leakage si se mezcla.
   - Evidencia: `w_open/w_close` en [intraday_v2/01_build_intraday_windows.py](intraday_v2/01_build_intraday_windows.py#L70-L150) y [intraday_v2/05_generate_intraday_plan.py](intraday_v2/05_generate_intraday_plan.py#L90-L200).
   - Cambio mínimo: documentar que Baseline v1 usa scripts 01b/06b/04b, no 01/05/06.

6) **ProbWin v1: parseo de TZ en training**
   - Importa: consistencia de `entry_time`.
   - Evidencia: `pd.to_datetime` sin `utc=True` en [intraday_v2/04b_train_probwin_v1.py](intraday_v2/04b_train_probwin_v1.py#L108-L130).
   - Cambio mínimo: normalizar UTC antes de tz_convert.

7) **Validation script no integrado a pipeline**
   - Importa: QA automatizada.
   - Evidencia: [intraday_v2/10_validate_baseline_v1.py](intraday_v2/10_validate_baseline_v1.py).
   - Cambio mínimo: llamar validador al final de 06b opcionalmente.

8) **`daily_stop` basado en R acumulado no registra bloqueos en archivo separado**
   - Importa: auditoría.
   - Evidencia: bloqueos en memoria [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L276-L330).
   - Cambio mínimo: exportar bloqueos con `block_reason=DAILY_STOP`.

9) **No hay tabla resumen por hora/año para baseline legacy**
   - Importa: solo baseline v1 tiene summary; legacy no.
   - Evidencia: summary en [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L440-L470).
   - Cambio mínimo: opcional.

10) **`equity_daily` no incluye equity_start**
   - Importa: auditoría de retornos mensuales.
   - Evidencia: [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L400-L430).
   - Cambio mínimo: agregar columna `equity_start`.

## D) Riesgos técnicos detectados (con evidencia)

- **Leakage en pipeline legacy por ventanas agregadas**: `w_open/w_close` usan toda la ventana → posible look-ahead. Evidencia: [intraday_v2/01_build_intraday_windows.py](intraday_v2/01_build_intraday_windows.py#L70-L150) y [intraday_v2/05_generate_intraday_plan.py](intraday_v2/05_generate_intraday_plan.py#L90-L200).
- **Timezone inconsistente en legacy**: `plan['entry_time']` parsea con `utc=True` en backtest aunque la fuente puede ser NY. Evidencia: [intraday_v2/06_execute_intraday_backtest.py](intraday_v2/06_execute_intraday_backtest.py#L50-L70).
- **EOD real en Baseline v1 aún no validado**: lógica existe, validación falló localmente. Evidencia: [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L90-L120).
- **Selection bias legacy por régimen + prob global**: gates combinados en plan. Evidencia: [intraday_v2/05_generate_intraday_plan.py](intraday_v2/05_generate_intraday_plan.py#L130-L180).

## E) Siguiente paso recomendado (1) — Baseline engine sin ventanas

### Qué archivos crear/modificar
- Ya existe baseline engine: [intraday_v2/01b_build_baseline_signals.py](intraday_v2/01b_build_baseline_signals.py#L1-L140) y [intraday_v2/06b_execute_baseline_backtest.py](intraday_v2/06b_execute_baseline_backtest.py#L1-L520).
- Pendiente mínimo:
  1) Fix EOD real (validación fallida).
  2) Exportar blocked_trades.csv.
  3) Agregar run_metadata.json.

### Artefactos esperados en artifacts/baseline_v1/
- baseline_signals.parquet / baseline_signals.csv
- trades.csv
- equity_daily.csv
- monthly_table.csv
- summary_ticker_year_hour.csv
- (nuevo) blocked_trades.csv
- (nuevo) run_metadata.json

### Cómo validar
- Ejecutar validador 5 pruebas: [intraday_v2/10_validate_baseline_v1.py](intraday_v2/10_validate_baseline_v1.py)
- Confirmar que EOD real pase sin errores.

---

## Anexo — Estado actual “Baseline v1 + ProbWin selectivo”

✅ Implementado (código): señales 4 velas, ATR14, SL/TP, hour gate, sizing, max_open, daily stop, gating ProbWin selectivo, outputs principales.
⚠️ Pendiente: EOD real validado + blocked_trades.csv + PDF + logs reproducibles.
