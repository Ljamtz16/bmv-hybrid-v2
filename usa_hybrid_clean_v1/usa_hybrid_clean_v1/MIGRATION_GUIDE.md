# Guía de Migración: Actualizar Scripts Existentes

## Patrón de Actualización

### ANTES (Re-implementación de filtros)

```python
# enhanced_metrics_reporter.py (ANTES)
import pandas as pd

# ❌ Re-implementando filtro aquí
CONF_THRESHOLD = 4
WHITELIST = ["CVX", "XOM", "WMT", "MSFT", "SPY"]
ALLOWED_RISKS = ["LOW", "MEDIUM"]

def get_operables(df):
    mask = (df["confidence_score"] >= CONF_THRESHOLD) & \
           (df["macro_risk"].isin(ALLOWED_RISKS)) & \
           (df["ticker"].isin(WHITELIST))
    return df[mask]

# En main()
operables = get_operables(df)
print(f"Total: {len(df)}, Operables: {len(operables)}")
```

### DESPUÉS (Importar de operability.py)

```python
# enhanced_metrics_reporter.py (DESPUÉS)
import pandas as pd
from operability import operable_mask, get_operability_breakdown

def get_operables(df):
    # ✅ Usar función central
    return df[operable_mask(df)]

# En main()
breakdown = get_operability_breakdown(df)
print(f"Global: {breakdown['global']:,}")
print(f"  └─ Conf>=4: {breakdown['conf_only']:,}")
print(f"      └─ +Risk: {breakdown['conf_risk']:,}")
print(f"          └─ +Whitelist: {breakdown['operable']:,}")

operables = get_operables(df)
print(f"✅ Operables validados: {len(operables):,}")
```

---

## Scripts a Migrar

### 1. enhanced_metrics_reporter.py

**Cambios requeridos**:

```diff
+ from operability import operable_mask, get_operability_breakdown, EXPECTED_OPERABLE_COUNT
- CONF_THRESHOLD = 4  # ← Quitar (ahora en operability.py)
- WHITELIST = [...]    # ← Quitar

  def filter_signals(df):
-     mask = (df["confidence_score"] >= CONF_THRESHOLD) & ...  # ← Quitar
+     mask = operable_mask(df)  # ← Usar función central
      return df[mask]

  def main():
+     breakdown = get_operability_breakdown(df)  # ← Agregar breakdown
+     print(f"  Global: {breakdown['global']:,}")
      
      signals = filter_signals(df)
      print(f"  Operables: {len(signals):,}")
```

---

### 2. backtest_confidence_rules.py

**Cambios requeridos**:

```diff
+ from operability import operable_mask, get_operability_breakdown, WHITELIST_TICKERS
- CONF_THRESHOLD = 4  # ← Quitar
- WHITELIST = [...]    # ← Quitar

  def validate_backtest(results_df):
      # ← Aplicar operable_mask en lugar de manual filter
+     mask = operable_mask(results_df)
      operable_results = results_df[mask]
      
      return {
+         "breakdown": get_operability_breakdown(results_df),
          "operable_count": len(operable_results),
          "accuracy": operable_results["predicted_direction"].mean()
      }
```

---

### 3. validate_operability_consistency.py

**Cambios requeridos**:

```diff
+ from operability import get_operability_breakdown, EXPECTED_OPERABLE_COUNT
  
  def validate():
      df = load_features_csv()
      
-     # Manual counting aquí
+     breakdown = get_operability_breakdown(df)  # ← Usar función
      
-     operable_count = len(df[(df["confidence_score"] >= 4) & ...])
-     
      delta = breakdown["operable"] - EXPECTED_OPERABLE_COUNT
      
      if delta == 0:
          print("✅ CONSISTENT")
      elif abs(delta) <= 1:
          print("⚠️  Margin of error (OK)")
      else:
          print(f"❌ MISMATCH: {delta}")
```

---

## Checklist de Migración

Para cada script:

- [ ] Añadir imports de `operability.py`
  ```python
  from operability import operable_mask, get_operability_breakdown, EXPECTED_OPERABLE_COUNT, WHITELIST_TICKERS
  ```

- [ ] Quitar constantes hardcoded
  ```python
  # ❌ Eliminar:
  CONF_THRESHOLD = 4
  WHITELIST = [...]
  ALLOWED_RISKS = [...]
  ```

- [ ] Reemplazar lógica manual
  ```python
  # ❌ Antes:
  mask = (df["confidence_score"] >= 4) & (df["macro_risk"].isin(["LOW", "MEDIUM"])) & ...
  
  # ✅ Después:
  mask = operable_mask(df)
  ```

- [ ] Añadir breakdown
  ```python
  breakdown = get_operability_breakdown(df)
  print(f"Global: {breakdown['global']:,}")
  print(f"  Operables: {breakdown['operable']:,}")
  ```

- [ ] Validar conteo (opcional pero recomendado)
  ```python
  if len(operable_df) != EXPECTED_OPERABLE_COUNT:
      print(f"⚠️  Expected {EXPECTED_OPERABLE_COUNT}, got {len(operable_df)}")
  ```

---

## Validación Post-Migración

Después de actualizar un script:

```bash
# 1. Que el script corra sin errores
python mi_script.py

# 2. Que genere salida consistente
# (output CSV con operables)

# 3. Diagnóstico con diff_operables.py
python diff_operables.py --test=mi_script_output.csv
# Debe mostrar delta <= 1

# 4. Ejecutar validate_operability_consistency.py
python validate_operability_consistency.py
# Debe reportar ✅ o ⚠️ (no ❌)
```

---

## Orden de Migración Recomendado

1. **validate_operability_consistency.py** (más simple, ya casi usa bien los conteos)
2. **enhanced_metrics_reporter.py** (análisis, sin dependencias de otros)
3. **backtest_confidence_rules.py** (backtesting, mayor impacto)
4. **Tus scripts nuevos** (copiar template directamente)

---

## Troubleshooting

### Error: "ModuleNotFoundError: No module named 'operability'"

**Solución**: Asegurar que `operability.py` está en el mismo directorio que el script.

```bash
ls -la operability.py  # Debe existir
```

### Error: "KeyError: 'macro_risk'"

**Solución**: Algunos CSV tienen `risk_level` en lugar de `macro_risk`. Usar adapter:

```python
from operability import adapt_risk_column

df = adapt_risk_column(df)  # Convierte risk_level → macro_risk
mask = operable_mask(df)
```

### Conteo inconsistente tras migración

**Diagnóstico**:

```bash
# Generar referencia de script viejo
python script_viejo.py → output_viejo.csv

# Generar referencia de script nuevo
python script_nuevo.py → output_nuevo.csv

# Comparar
python diff_operables.py --test=output_nuevo.csv
```

Si delta es alto, revisar:
1. ¿Cambió el filtro por accidente?
2. ¿El CSV tiene columnas faltantes?
3. ¿Hay NaN en confidence_score o macro_risk?

---

## Resumen

| Antes | Después |
|-------|---------|
| 200+ líneas de lógica de filtrado en c/script | 1 línea: `operable_mask(df)` |
| Constantes duplicadas en 5 lugares | 1 fuente: `operability_config.py` |
| Difícil cambiar umbrales | `operability_config.KillSwitchConfig.WINDOW_DAYS = X` |
| Sin auditoría | `run_audit.json` automático |
| Problemas con nombres de columnas | Adapter automático |
| Inconsistencias silenciosas | Validación integrada |

---

**Versión**: 1.0
**Fecha**: 2026-01-13
**Status**: Ready for Implementation

