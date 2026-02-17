
# WF Box (aislado y controlado)

Este paquete corre un **walk‑forward** simple SIN depender de tu repo.
Tú controlas exactamente **qué datos** entran vía `manifest.yaml` y la carpeta `data/raw/`.

## Carpeta
```
wf_box/
  data/
    raw/        # coloca aquí CSVs OHLCV por ticker (una fila por día)
    frozen/     # snapshot reproducible que el pipeline usa
  scripts/
    freeze_data.py
    make_month_forecast.py
    kpi_validation_summary.py
    utils.py
  configs/
    model.yaml
  manifest.yaml
  README.md
```

## CSV esperado (por cada ticker)
- Nombre: `<TICKER>.csv` (ej. `WALMEX.MX.csv`)
- Columnas requeridas (utf-8):
  `Date,Open,High,Low,Close,Volume`
- `Date` en formato ISO `YYYY-MM-DD`

## Flujo
1) Edita `manifest.yaml` con tickers, rango de fechas y horizonte/target.
2) Congela datos (whitelist + recorte + hash):  
   `python scripts/freeze_data.py`
3) Pronóstico por mes (entrena con train_end y predice mes objetivo):  
   `python scripts/make_month_forecast.py --month 2025-01 --train-end 2024-12`
4) KPIs del mes (si hay `y_true` dentro del mes):  
   `python scripts/kpi_validation_summary.py --month 2025-01`

## Target
- `y`: **retorno acumulado a +5 días** (suma de log-retornos).
- Para meses ya cerrados tendrás `y_true`; para meses en curso, puede faltar.

## Modelo simple
- RandomForestRegressor con features básicos (log-ret, MAs, volatilidad).
- Semilla fija para reproducibilidad. Ajusta en `configs/model.yaml`.
