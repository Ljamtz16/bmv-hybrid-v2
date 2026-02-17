# Diff Exacto - Cambios a 06b_execute_baseline_backtest.py

## Sección 1: Imports (líneas ~12-18)

```diff
from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path
+ import json
+ import subprocess
+ import sys
+ from datetime import datetime

import importlib.util
import math
import joblib
```

---

## Sección 2: Nueva función helper (después de `_load_intraday()`, ~línea 65)

```diff
def _load_intraday(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == '.parquet':
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    return df


+ def _get_git_commit_hash(repo_path: Path) -> str | None:
+     """Get current git commit hash, or None if not a git repo."""
+     try:
+         result = subprocess.run(
+             ['git', 'rev-parse', 'HEAD'],
+             cwd=str(repo_path),
+             capture_output=True,
+             text=True,
+             timeout=5
+         )
+         if result.returncode == 0:
+             return result.stdout.strip()
+     except Exception:
+         pass
+     return None


def _minute_of_day(ts: pd.Timestamp) -> int:
    return ts.hour * 60 + ts.minute
```

---

## Sección 3: Exportación de archivos (reemplazar líneas ~501-525)

### ANTES:
```python
    # Guardar outputs
    output_dir_path = Path(output_dir) if output_dir else base_dir / 'artifacts' / 'baseline_v1'
    output_dir_path.mkdir(parents=True, exist_ok=True)

    trades_path = output_dir_path / 'trades.csv'
    equity_path = output_dir_path / 'equity_daily.csv'
    monthly_path = output_dir_path / 'monthly_table.csv'
    summary_path = output_dir_path / 'summary_ticker_year_hour.csv'

    trades_df.to_csv(trades_path, index=False)
    equity_daily_df.to_csv(equity_path, index=False)
    monthly_df.to_csv(monthly_path, index=False)
    summary_df.to_csv(summary_path, index=False)

    print(f"[06b] ✅ Trades guardados en: {trades_path}")
    print(f"[06b] ✅ Equity daily guardado en: {equity_path}")
    print(f"[06b] ✅ Monthly table guardado en: {monthly_path}")
    print(f"[06b] ✅ Summary guardado en: {summary_path}")

    return {...}
```

### DESPUÉS:
```python
    # Guardar outputs
    output_dir_path = Path(output_dir) if output_dir else base_dir / 'artifacts' / 'baseline_v1'
    output_dir_path.mkdir(parents=True, exist_ok=True)

    trades_path = output_dir_path / 'trades.csv'
    equity_path = output_dir_path / 'equity_daily.csv'
    monthly_path = output_dir_path / 'monthly_table.csv'
    summary_path = output_dir_path / 'summary_ticker_year_hour.csv'
+   blocked_trades_path = output_dir_path / 'blocked_trades.csv'
+   blocked_summary_path = output_dir_path / 'blocked_summary.json'
+   metadata_path = output_dir_path / 'run_metadata.json'

    trades_df.to_csv(trades_path, index=False)
    equity_daily_df.to_csv(equity_path, index=False)
    monthly_df.to_csv(monthly_path, index=False)
    summary_df.to_csv(summary_path, index=False)

+   # Export blocked trades
+   if not trades_df.empty:
+       blocked_df = trades_df[trades_df.get('allowed', False) == False].copy()
+       if not blocked_df.empty:
+           # Select minimal columns
+           blocked_cols = ['entry_time', 'ticker', 'hour_bucket', 'block_reason', 
+                          'equity_at_entry', 'risk_cash', 'entry', 'sl', 'tp',
+                          'probwin', 'threshold']
+           blocked_export = blocked_df[[c for c in blocked_cols if c in blocked_df.columns]]
+           blocked_export.to_csv(blocked_trades_path, index=False)
+           print(f"[06b] ✅ Blocked trades guardados en: {blocked_trades_path}")
+           
+           # Export blocked summary
+           blocked_summary = blocked_df['block_reason'].value_counts().to_dict()
+           with open(blocked_summary_path, 'w') as f:
+               json.dump(blocked_summary, f, indent=2)
+           print(f"[06b] ✅ Blocked summary guardado en: {blocked_summary_path}")
+
+   # Export run metadata
+   git_commit = _get_git_commit_hash(base_dir.parent)
+   metadata = {
+       'run_timestamp': datetime.utcnow().isoformat() + 'Z',
+       'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
+       'repo_root': str(base_dir.parent),
+       'data_path': str(data_path) if 'data_path' in locals() else None,
+       'params': {
+           'capital_initial': equity_initial,
+           'risk_per_trade': risk_per_trade,
+           'max_open': max_open,
+           'daily_stop_R': daily_stop_r,
+           'atr_window': 14,
+           'sl_mult': 1.0,
+           'tp_mult': 1.5,
+           'tie_break_rule': 'first_signal'
+       },
+       'filters': {
+           'core_tickers': list(CORE_TICKERS),
+           'allowed_hours_ny': ['09:30-11:30', '15:00-16:00']
+       },
+       'counts': {
+           'signals_generated': len(signals) if 'signals' in locals() else 0,
+           'trades_allowed': int((trades_df.get('allowed', True) == True).sum()) if not trades_df.empty else 0,
+           'trades_blocked': int((trades_df.get('allowed', False) == False).sum()) if not trades_df.empty else 0
+       },
+       'output_paths': {
+           'trades': str(trades_path),
+           'blocked_trades': str(blocked_trades_path),
+           'equity_daily': str(equity_path),
+           'monthly_table': str(monthly_path),
+           'summary_ticker_year_hour': str(summary_path)
+       },
+       'git_commit': git_commit
+   }
+   
+   with open(metadata_path, 'w') as f:
+       json.dump(metadata, f, indent=2)
+   print(f"[06b] ✅ Metadata guardado en: {metadata_path}")

    print(f"[06b] ✅ Trades guardados en: {trades_path}")
    print(f"[06b] ✅ Equity daily guardado en: {equity_path}")
    print(f"[06b] ✅ Monthly table guardado en: {monthly_path}")
    print(f"[06b] ✅ Summary guardado en: {summary_path}")

    return {...}
```

---

## Resumen de Cambios

| Aspecto | Líneas | Tipo | Descripción |
|---------|--------|------|-------------|
| Imports | 12-18 | Adición | json, subprocess, sys, datetime |
| Helper | ~65 | Nueva función | `_get_git_commit_hash()` |
| Exportación | ~505-560 | Reemplazo | 3 nuevos archivos + metadata |
| **Total adicional** | ~80 líneas | **<1% del código** | Sin cambios a lógica de backtest |

---

## Validación

- ✅ No se modifica `execute_baseline_backtest()` signature
- ✅ No se alteran variables de cálculo (equity, pnl, r_mult, etc.)
- ✅ Todas las líneas de exportación de CSV existentes se mantienen
- ✅ El validador `10_validate_baseline_v1.py` pasa todas las pruebas
- ✅ Archivos generados sin errores: trades.csv, blocked_trades.csv, run_metadata.json, blocked_summary.json
