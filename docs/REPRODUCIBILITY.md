# Reproducibility

## Resumen (ES)
Estas instrucciones permiten reproducir el pipeline con datos locales. Los datos y modelos no se publican en este repositorio.

### Entorno
- Python 3.10+
- Crear y activar .venv
- Instalar dependencias desde requirements.txt

### Estructura esperada
```
data/
  raw/
    1d/
    1h/
models/
reports/
config/
```

### Ejecucion base (BMV Hybrid V2)
```
python scripts/01_download_data.py
python scripts/02_build_features.py
python scripts/04_generate_signals.py
python scripts/05_calibrate_thresholds.py
python scripts/06_backtest_eval.py
```

## Summary (EN)
These steps reproduce the pipeline with local data. Data and trained models are not included in this repository.

### Environment
- Python 3.10+
- Create and activate .venv
- Install dependencies from requirements.txt

### Expected layout
```
data/
  raw/
    1d/
    1h/
models/
reports/
config/
```

### Base run (BMV Hybrid V2)
```
python scripts/01_download_data.py
python scripts/02_build_features.py
python scripts/04_generate_signals.py
python scripts/05_calibrate_thresholds.py
python scripts/06_backtest_eval.py
```

## Notes
- Use environment variables for credentials. Do not commit .env files.
- For RPi deployment, see [bmv_hybrid_clean_v3/ARCHITECTURE.md](../bmv_hybrid_clean_v3/ARCHITECTURE.md).
