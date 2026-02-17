# Packaging Institucional - Baseline Intradía v1

## Objetivo
Generar auditoría y reproducibilidad para cada corrida del backtest sin alterar la lógica del engine.

---

## Cambios Aplicados a `06b_execute_baseline_backtest.py`

### 1. Imports Adicionales
```python
import json
import subprocess
import sys
from datetime import datetime
```

### 2. Nueva Función Helper
```python
def _get_git_commit_hash(repo_path: Path) -> str | None:
    """Get current git commit hash, or None if not a git repo."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None
```

### 3. Nueva Sección de Exportación (al final de `execute_baseline_backtest()`)

**A) Exportar trades bloqueadas** (`blocked_trades.csv`):
- Filtra todas las filas con `allowed=False`
- Exporta columnas: entry_time, ticker, hour_bucket, block_reason, equity_at_entry, risk_cash, entry, sl, tp, probwin, threshold
- Ubicación: `artifacts/baseline_v1/blocked_trades.csv`

**B) Resumen de bloqueos** (`blocked_summary.json`):
- Conteo por `block_reason` usando value_counts()
- Ejemplo: `{"MAX_OPEN": 1636, "DAILY_STOP": 1390}`
- Ubicación: `artifacts/baseline_v1/blocked_summary.json`

**C) Metadatos de ejecución** (`run_metadata.json`):
```json
{
  "run_timestamp": "ISO timestamp",
  "python_version": "3.12.6",
  "repo_root": "path to workspace",
  "data_path": "path to consolidated_15m.parquet",
  "params": {
    "capital_initial": 2000.0,
    "risk_per_trade": 0.0075,
    "max_open": 2,
    "daily_stop_R": -2.0,
    "atr_window": 14,
    "sl_mult": 1.0,
    "tp_mult": 1.5,
    "tie_break_rule": "first_signal"
  },
  "filters": {
    "core_tickers": ["SPY", "QQQ", "GS", "JPM", "CAT"],
    "allowed_hours_ny": ["09:30-11:30", "15:00-16:00"]
  },
  "counts": {
    "signals_generated": 40075,
    "trades_allowed": 3126,
    "trades_blocked": 3026
  },
  "output_paths": {
    "trades": "path/trades.csv",
    "blocked_trades": "path/blocked_trades.csv",
    "equity_daily": "path/equity_daily.csv",
    "monthly_table": "path/monthly_table.csv",
    "summary_ticker_year_hour": "path/summary_ticker_year_hour.csv"
  },
  "git_commit": "hash or null"
}
```

---

## Integridad Mantenida

✅ **Validador pasa todas las 5 pruebas**:
- Cero leakage: Señales usan solo datos ≤ bar de entrada
- TZ consistente: date_ny y hour_bucket correctos
- EOD real: exit_time = última vela NY cuando no hay TP/SL
- Risk real: shares calculado correctamente
- max_open real: Máximo 2 posiciones simultáneas

✅ **Motor de backtest sin cambios**:
- La lógica de entradas, exits, sizing y gating se mantiene idéntica
- Solo se añadieron exportaciones al final

---

## Archivos Generados

En cada ejecución de `06b_execute_baseline_backtest.py`, se crean:

```
artifacts/baseline_v1/
├── trades.csv                    (3,126 trades permitidas + headers)
├── blocked_trades.csv            (3,026 trades bloqueadas)
├── blocked_summary.json          (conteo por reason)
├── run_metadata.json             (metadatos completos)
├── equity_daily.csv              (curva de equity por día)
├── monthly_table.csv             (resumen mensual)
└── summary_ticker_year_hour.csv  (resumen por ticker/año/hora)
```

---

## Ejemplo de Contenido

### blocked_trades.csv (primeras 3 filas)
```
entry_time,ticker,hour_bucket,block_reason,equity_at_entry,risk_cash,entry,sl,tp,probwin,threshold
2024-02-06 09:45:00-05:00,SPY,09:45,DAILY_STOP,2014.788437,15.110913,494.17,NaN,NaN,NaN,NaN
2024-02-06 11:30:00-05:00,GS,11:30,DAILY_STOP,1999.873437,14.999051,385.24,NaN,NaN,NaN,NaN
2024-02-06 11:30:00-05:00,SPY,11:30,DAILY_STOP,1999.873437,14.999051,493.315,NaN,NaN,NaN,NaN
```

### blocked_summary.json
```json
{
  "MAX_OPEN": 1636,
  "DAILY_STOP": 1390
}
```

### run_metadata.json (extracto)
```json
{
  "run_timestamp": "2026-02-11T06:18:57.821294Z",
  "python_version": "3.12.6",
  "repo_root": "C:\\...\\Intradia",
  "data_path": "C:\\...\\consolidated_15m.parquet",
  "params": { ... },
  "counts": {
    "signals_generated": 6152,
    "trades_allowed": 3126,
    "trades_blocked": 3026
  },
  "git_commit": null
}
```

---

## Validación Final

```bash
$ python intraday_v2/10_validate_baseline_v1.py
[10] ℹ️ 13 trades bloqueados por MAX_OPEN (límite=2)
[10] ✅ Todas las pruebas pasaron
```

**Estado: ✅ IMPLEMENTADO Y VALIDADO**
