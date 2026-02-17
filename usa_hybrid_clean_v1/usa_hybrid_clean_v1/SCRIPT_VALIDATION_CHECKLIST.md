# CHECKLIST: Cómo Escribir Scripts de Validación Consistentes

## ✅ Antes de Crear un Script de Validación

Usa este checklist para asegurar que tu script usa la definición oficial de "operable":

### 1. Copiar las Constantes Globales
```python
CONF_THRESHOLD = 4
RISK_THRESHOLD = "MEDIUM"  # No operar si HIGH/CRITICAL
WHITELIST_TICKERS = ["CVX", "XOM", "WMT", "MSFT", "SPY"]
```

**Nunca cambies estos valores en scripts individuales**

### 2. Copiar la Función de Riesgo
```python
FOMC_DATES = pd.to_datetime([
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-11-05", "2025-12-17"
])

def calculate_macro_risk_level(date: pd.Timestamp) -> str:
    """Calcular nivel de riesgo macro."""
    fomc_proximity = ((FOMC_DATES - date).days).min()
    if abs(fomc_proximity) <= 2:
        return "HIGH"
    return "MEDIUM"
```

### 3. Aplicar los 3 Filtros (EN ORDEN)
```python
df["macro_risk"] = df["date"].apply(calculate_macro_risk_level)

# Filtro 1: Confianza
conf_ok = df["confidence_score"] >= CONF_THRESHOLD

# Filtro 2: Riesgo
risk_ok = df["macro_risk"].isin(["LOW", "MEDIUM"])

# Filtro 3: Whitelist
ticker_ok = df["ticker"].isin(WHITELIST_TICKERS)

# Combinar (EN ESTE ORDEN)
operable = df[conf_ok & risk_ok & ticker_ok]
```

**Importante**: Siempre aplica en este orden:
1. Confianza primero (reduce más)
2. Riesgo segundo
3. Whitelist tercero

### 4. Verificar el Conteo
```python
# Debería ser 3,881 operables
print(f"Operables: {len(operable):,}")
# Si ves diferente → revisa que tienes los 3 filtros
```

---

## ❌ Errores Comunes

### Error 1: Usar solo Conf
```python
# ❌ INCORRECTO
operable = df[df["confidence_score"] >= 4]
# Resultado: ~10,000 (sin filtrar Risk ni Whitelist)
```

### Error 2: Usar Conf + Risk pero NO Whitelist
```python
# ❌ INCORRECTO
operable = df[(df["confidence_score"] >= 4) & (df["risk_level"] != "HIGH")]
# Resultado: ~10,000 (falta Whitelist)
```

### Error 3: Usar columna de Risk incorrecta
```python
# ❌ INCORRECTO
operable = df[(df["confidence_score"] >= 4) & (df["risk"] <= "MEDIUM")]
# ¿Qué columna es? ¿"risk", "risk_level", "macro_risk"?
# Siempre usar la que calcula: calculate_macro_risk_level()
```

### Error 4: Usar != "HIGH" en lugar de .isin(["LOW", "MEDIUM"])
```python
# ❌ CASI CORRECTO (pero menos claro)
risk_ok = df["macro_risk"] != "HIGH"

# ✅ MEJOR (más explícito)
risk_ok = df["macro_risk"].isin(["LOW", "MEDIUM"])
```

---

## 🔍 Cómo Verificar si tu Script es Correcto

**Paso 1**: Ejecuta tu script
```bash
python mi_script_validacion.py
```

**Paso 2**: Busca el conteo de operables
- ¿Ves **3,881** operables?
  - ✅ CORRECTO (tienes los 3 filtros)
  
- ¿Ves **10,000+**?
  - ❌ INCORRECTO (faltan Risk o Whitelist)

- ¿Ves **<3,000**?
  - ❌ INCORRECTO (aplicaste filtros más estrictos)

**Paso 3**: Compara con `validate_operability_consistency.py`
```bash
python validate_operability_consistency.py
```

Si tu script muestra el mismo conteo de operables:
✅ **CONSISTENTE**

Si muestra diferente:
❌ **INCONSISTENTE** (revisa los filtros)

---

## 📋 Plantilla de Script Correcto

Copia y adapta esta plantilla:

```python
#!/usr/bin/env python
"""
Descripción de tu script
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ============================================================================
# CONSTANTES GLOBALES (SINCRONIZADAS)
# ============================================================================

CONF_THRESHOLD = 4
RISK_THRESHOLD = "MEDIUM"
WHITELIST_TICKERS = ["CVX", "XOM", "WMT", "MSFT", "SPY"]

FOMC_DATES = pd.to_datetime([
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-11-05", "2025-12-17"
])

def calculate_macro_risk_level(date: pd.Timestamp) -> str:
    """Calcular nivel de riesgo macro."""
    fomc_proximity = ((FOMC_DATES - date).days).min()
    if abs(fomc_proximity) <= 2:
        return "HIGH"
    return "MEDIUM"

# ============================================================================
# CARGAR Y FILTRAR
# ============================================================================

def main():
    # Cargar datos
    df = pd.read_csv("outputs/analysis/all_signals_with_confidence.csv")
    df["date"] = pd.to_datetime(df["date"])
    df["macro_risk"] = df["date"].apply(calculate_macro_risk_level)
    
    # Aplicar 3 filtros
    conf_ok = df["confidence_score"] >= CONF_THRESHOLD
    risk_ok = df["macro_risk"].isin(["LOW", "MEDIUM"])
    ticker_ok = df["ticker"].isin(WHITELIST_TICKERS)
    
    operable = df[conf_ok & risk_ok & ticker_ok]
    
    print(f"Operables: {len(operable):,}")
    # Debe ser 3,881
    
    # ... rest of your script ...

if __name__ == "__main__":
    main()
```

---

## 📊 Auditoría Automática

Cada vez que crees un script nuevo, ejecuta:
```bash
python validate_operability_consistency.py
```

Compara el resultado de tu script con el número de referencia: **3,881**

---

## 🔗 Referencias

- [OPERABILITY_DEFINITION.md](OPERABILITY_DEFINITION.md) - Definición oficial
- [production_orchestrator.py](production_orchestrator.py) - Script de referencia (Línea 202-220)
- [validate_operability_consistency.py](validate_operability_consistency.py) - Validador

