# BMV Hybrid V2 — Clean Zero (v3)
Sistema híbrido desde cero:
- Señal diaria (RF/SVM/LSTM) → prob BUY/SELL
- Ejecución intradía 1H con SL-first, trailing ATR, break-even y holding
- Calibración de umbral τ por PnL y fusión de probabilidades



# hasta el momento 17/08
¡perfecto! te dejo un **README.md** listo para pegar en la raíz del repo. Incluye los dos flujos (preparación/validación y operación mensual), ejemplos de comandos en PowerShell (y equivalentes bash), variables de entorno útiles, archivos de salida y una guía rápida de troubleshooting.

---

# BMV Hybrid — README

Automatiza la generación de señales, calibración de umbrales, backtests, barridos de parámetros, *paper trading*, pronóstico mensual y validación con datos reales.

## Requisitos

* Python 3.10+
* Entorno virtual activado (`.venv`)
* Dependencias instaladas:

  ```powershell
  .\.venv\Scripts\pip.exe install -r requirements.txt
  ```
* Estructura de datos esperada:

  ```
  data/
    raw/
      1d/    # OHLC diarios por ticker (CSV)
      1h/    # OHLC horarios por ticker (CSV)
  models/    # modelos/umbrales/gates
  reports/   # salidas
  config/
    base.yaml
    paper.yaml  # (se genera/actualiza con 09_prepare_paper_config.py)
  ```

## Variables útiles

* `CFG` para fijar la config a usar (opcional, muchos scripts lo respetan):

  ```powershell
  $env:CFG = "config/paper.yaml"
  ```

  ```bash
  export CFG="config/paper.yaml"
  ```

* `PYTHONPATH` (en PowerShell, dentro de la carpeta del repo):

  ```powershell
  $env:PYTHONPATH = (Get-Location).Path
  ```

---

## A) Preparación y validación (básico a avanzado)

Ejecuta esto cuando cambies datos/modelos o quieras recalibrar y validar.

1. **Descarga/actualiza datos**

```powershell
.\.venv\Scripts\python.exe scripts\01_download_data.py
```

```bash
./.venv/bin/python scripts/01_download_data.py
```

2. **Construye features/indicadores**

```powershell
.\.venv\Scripts\python.exe scripts\02_build_features.py
```

3. *(Opcional)* **Genera señales globales**

```powershell
.\.venv\Scripts\python.exe scripts\04_generate_signals.py
```

4. **Calibra umbrales (τ\*) global / por ticker**
   Guarda `models/thresholds_by_ticker.json`.

```powershell
.\.venv\Scripts\python.exe scripts\05_calibrate_thresholds.py
```

5. *(Opcional)* **Construye BUY gate dinámico**

```powershell
.\.venv\Scripts\python.exe scripts\06_dynamic_buy_gate_eval.py
```

6. **Backtest rápido del mes de la config**

```powershell
.\.venv\Scripts\python.exe scripts\06_backtest_eval.py
```

7. **Barrido de parámetros por mes(es)**

```powershell
.\.venv\Scripts\python.exe scripts\07_param_sweep_eval.py --months 2024-11
# Ejemplo multi-mes:
.\.venv\Scripts\python.exe scripts\07_param_sweep_eval.py --months 2024-10,2024-11
```

8. **Validación multi-mes (agrega, top-N, campeón)**

```powershell
.\.venv\Scripts\python.exe scripts\08_multi_month_validation.py --months "2024-05:2025-01"
```

9. *(Opcional)* **Revalidar top configs**

```powershell
.\.venv\Scripts\python.exe scripts\07b_validate_top_configs.py
```

10. **Congelar campeón a `config/paper.yaml`**

```powershell
.\.venv\Scripts\python.exe scripts\09_prepare_paper_config.py
```

11. *(Opcional)* **Comparar corridas por mes**

```powershell
.\.venv\Scripts\python.exe scripts\11_compare_runs.py --months "2024-05,2025-01,2025-03"
```

---

## B) Operación mensual (forecast, paper trading, validación)

### Opción 1 — Manual (paso a paso)

1. **Pronóstico del mes objetivo**

```powershell
.\.venv\Scripts\python.exe scripts\09_make_month_forecast.py --month 2025-03
```

2. **Paper trading del intervalo**

```powershell
# usar config/paper.yaml
$env:CFG = "config/paper.yaml"
.\.venv\Scripts\python.exe scripts\paper_run_daily.py --start 2025-01-01 --end 2025-02-01 --dump
```

3. **Resumen de paper (equity metrics + atribución)**

```powershell
.\.venv\Scripts\python.exe scripts\paper_post_summary.py
```

4. **Validación del pronóstico (cuando ya hay datos reales del mes)**

```powershell
.\.venv\Scripts\python.exe scripts\10_validate_month_forecast.py --month 2025-03
```

5. *(Opcional)* **Comparar resultados por mes**

```powershell
.\.venv\Scripts\python.exe scripts\11_compare_runs.py --months "2025-01:2025-03"
```

### Opción 2 — Automática (un botón)

**Pronostica y valida** en un solo comando:

```powershell
.\.venv\Scripts\python.exe scripts\12_forecast_and_validate.py --month 2025-04
```

* Genera `reports/forecast/2025-04/...` y luego valida con los datos reales que tenga el repo.

---

## Validación intrabar de pronóstico vs histórico (TP/SL)

Cuando quieras **auditar si primero tocó TP o SL** con barras 1h reales:

1. Valida el mes (genera `validation_trades_auto.csv` enriquecido con `entry_date/price/tp/sl`):

```powershell
.\.venv\Scripts\python.exe scripts\10_validate_month_forecast.py --month 2025-05
```

2. Compara contra OHLC 1h:

```powershell
.\.venv\Scripts\python.exe scripts\13_compare_forecast_real.py --month 2025-05 --hist_dir "data/raw/1h" --tie_mode worst
```

Salida:

* `reports/forecast/<YYYY-MM>/validation/forecast_vs_real.csv`
* `.../forecast_vs_real_metrics.json` (match rate TP/SL/TIME, winrate real vs predicho, accuracy de signos, etc.)

> **Nota:** Si tus `validation_trades_*.csv` no traen `entry_date/tp/sl`, el script 10 ya los reconstituye usando ATR diario + multiplicadores del `cfg.exec`.

---

## Dónde cambiar meses y rangos

* **Barrido** (`07_param_sweep_eval.py`):

  ```powershell
  --months "YYYY-MM"              # un mes
  --months "YYYY-MM,YYYY-MM"      # lista
  --months "YYYY-MM:YYYY-MM"      # rango inclusive:exclusive por mes
  ```

* **Validación multi-mes** (`08_multi_month_validation.py`):

  ```powershell
  --months "2024-05:2025-01"
  ```

* **Forecast** (`09_make_month_forecast.py`) y **Validación** (`10_validate_month_forecast.py`):

  ```powershell
  --month 2025-03
  ```

* **Paper** (`paper_run_daily.py`):

  ```powershell
  --start YYYY-MM-DD --end YYYY-MM-DD
  ```

---

## Archivos de salida clave

* `reports/param_sweep/param_sweep_summary.csv` — ranking de combinaciones.
* `reports/param_sweep/topN_validation.csv` — top-N por mes.
* `reports/param_sweep/validation_aggregate.csv` — agregado global multi-mes.
* `reports/forecast/<YYYY-MM>/forecast_*.csv` — señales previstas del mes.
* `reports/forecast/<YYYY-MM>/validation/validation_trades_*.csv` — trades de validación.
* `reports/forecast/<YYYY-MM>/validation/forecast_vs_real.csv` — comparación TP/SL intrabar.
* `reports/paper_trading/paper_daily_equity.csv|json` — equity del paper.
* `reports/paper_trading/paper_trades_by_ticker.csv` — atribución por ticker.

---

## Scripts incluidos

* `01_download_data.py` — descarga/actualiza datos.
* `02_build_features.py` — features/indicadores.
* `04_generate_signals.py` — señales (opcional).
* `05_calibrate_thresholds.py` (+ auxiliares) — τ\* global/por ticker.
* `06_dynamic_buy_gate_eval.py` — BUY gate dinámico.
* `06_backtest_eval.py` — backtest de un mes.
* `07_param_sweep_eval.py` — barrido de tp/sl/trailing/gate/meses (con *lookback* opcional).
* `07b_validate_top_configs.py` — revalida top configs.
* `08_multi_month_validation.py` — multi-mes + topN + agregado.
* `09_prepare_paper_config.py` — genera `config/paper.yaml`.
* `09_make_month_forecast.py` — pronóstico del mes.
* `10_validate_month_forecast.py` — **(parcheado)** valida forecast; enriquece `entry_date/price/tp/sl`.
* `11_compare_runs.py` — compara corridas por mes.
* `12_forecast_and_validate.py` — *one-click* pronóstico + validación.
* `13_compare_forecast_real.py` — comparación intrabar TP/SL con 1h real.

---

## Troubleshooting rápido

* **“No encontré forecast…”**
  Asegúrate de correr `09_make_month_forecast.py` antes de `10_validate_month_forecast.py`.

* **`validation_trades_*.csv` sin `entry_date/tp/sl`**
  Ya se completa automáticamente en `10_validate_month_forecast.py`. Vuelve a ejecutar.

* **Sin datos 1h/1d del mes**
  Corre `01_download_data.py` y confirma archivos en `data/raw/1d` y `data/raw/1h`.

* **Resultados muy disparejos por mes**
  Usa `07_param_sweep_eval.py` + `08_multi_month_validation.py` y congela con `09_prepare_paper_config.py`.

---

## Ejemplos rápidos (PowerShell)

* Pronosticar y validar Mayo 2025 en un paso:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe scripts\12_forecast_and_validate.py --month 2025-05
```

* Validar forecast vs 1h real (TP/SL intrabar):

```powershell
.\.venv\Scripts\python.exe scripts\13_compare_forecast_real.py --month 2025-05 --hist_dir "data/raw/1h" --tie_mode worst
```

* Paper trading de enero:

```powershell
$env:CFG = "config/paper.yaml"
.\.venv\Scripts\python.exe scripts\paper_run_daily.py --start 2025-01-01 --end 2025-02-01 --dump
.\.venv\Scripts\python.exe scripts\paper_post_summary.py
```
