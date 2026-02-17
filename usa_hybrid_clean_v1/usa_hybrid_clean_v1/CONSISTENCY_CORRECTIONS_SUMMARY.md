# Correcciones de Consistencia: Definición de "Operable"

## Problema Identificado

Diferentes scripts usaban definiciones **inconsistentes** de qué es "operable":

- `production_orchestrator.py`: 3 filtros (Conf + Risk + Whitelist)
- `enhanced_metrics_reporter.py`: 2-3 filtros (columna de risk inconsistente)
- `backtest_confidence_rules.py`: 2 filtros (faltaban Risk + Whitelist)

**Resultado**: "Aparentes contradicciones" entre análisis que en realidad tenían filtros distintos

---

## Soluciones Implementadas

### 1. ✅ Archivo: OPERABILITY_DEFINITION.md

**Propósito**: Definición única y oficial

**Contenido**:
- Definición oficial de OPERABLE (3 filtros)
- Implementación correcta (referencia)
- Implementaciones incorrectas (cómo no hacerlo)
- Checklist de verificación

**Ubicación**: [OPERABILITY_DEFINITION.md](OPERABILITY_DEFINITION.md)

### 2. ✅ Script: validate_operability_consistency.py

**Propósito**: Verificar que todos los scripts usan la misma definición

**Funcionalidad**:
- Carga datos
- Aplica 3 filtros paso a paso
- Muestra conteo en cada paso
- Exporta auditoría CSV
- Proporciona "tabla rápida de referencia"

**Uso**:
```bash
python validate_operability_consistency.py
```

**Salida**: Muestra que el número oficial de operables es **3,881**

**Archivo exportado**: `operability_consistency_check.csv`

### 3. ✅ Script: enhanced_metrics_reporter.py

**Cambios**:
- Línea ~115-120: Cambió de `risk_level` a `macro_risk`
- Aplicación explícita de 3 filtros: `conf_ok & risk_ok & ticker_ok`

**Antes**:
```python
operable = df[
    (df["confidence_score"] >= 4) &
    (df["risk_level"] != "HIGH") &  # ← Columna inconsistente
    (df["ticker"].isin(WHITELIST_TICKERS))
]
```

**Después**:
```python
df["macro_risk"] = df["date"].apply(calculate_risk_level)

risk_ok = df["macro_risk"].isin(["LOW", "MEDIUM"])
conf_ok = df["confidence_score"] >= 4
ticker_ok = df["ticker"].isin(WHITELIST_TICKERS)

operable = df[risk_ok & conf_ok & ticker_ok].copy()
```

### 4. ✅ Script: backtest_confidence_rules.py

**Cambios**:
- Línea ~1-20: Agregadas constantes globales
- Línea ~40: Agregada función `calculate_macro_risk_level()`
- Línea ~160: Reemplazada definición de `operable` con 4 filtros

**Antes**:
```python
df_backtest["operable"] = (df_backtest["confidence_score"] >= confidence_threshold) & \
                          (df_backtest["trading_signal"].isin(["BUY", "SELL"]))
# ❌ Faltaban Risk y Whitelist
```

**Después**:
```python
df_backtest["macro_risk"] = df_backtest["date"].apply(calculate_macro_risk_level)

risk_ok = df_backtest["macro_risk"].isin(["LOW", "MEDIUM"])
conf_ok = df_backtest["confidence_score"] >= confidence_threshold
ticker_ok = df_backtest["ticker"].isin(WHITELIST_TICKERS)
trading_ok = df_backtest["trading_signal"].isin(["BUY", "SELL"])

df_backtest["operable"] = risk_ok & conf_ok & ticker_ok & trading_ok
```

### 5. ✅ Archivo: SCRIPT_VALIDATION_CHECKLIST.md

**Propósito**: Guía para escribir scripts consistentes en el futuro

**Contenido**:
- Checklist pre-script (qué copiar siempre)
- Errores comunes (qué NO hacer)
- Cómo verificar si un script es correcto
- Plantilla de script correcto

**Ubicación**: [SCRIPT_VALIDATION_CHECKLIST.md](SCRIPT_VALIDATION_CHECKLIST.md)

---

## Verificación

### Número de Referencia Oficial

**Operables con 3 filtros (Conf>=4 + Risk<=MEDIUM + Whitelist)**: **3,881**

### Si ves este número en tu script:
✅ **CORRECTO** - Tienes los 3 filtros

### Si ves diferente:
❌ **INCORRECTO** - Falta aplicar algún filtro

---

## Cambios Resumidos por Archivo

| Archivo | Cambios | Estado |
|---------|---------|--------|
| **production_orchestrator.py** | Sin cambios (referencia) | ✅ |
| **enhanced_metrics_reporter.py** | risk_level → macro_risk | ✅ Corregido |
| **backtest_confidence_rules.py** | +Risk +Whitelist | ✅ Corregido |
| **OPERABILITY_DEFINITION.md** | Nuevo archivo (referencia) | ✅ Creado |
| **validate_operability_consistency.py** | Nuevo script (validador) | ✅ Creado |
| **SCRIPT_VALIDATION_CHECKLIST.md** | Nuevo archivo (guía) | ✅ Creado |

---

## Impacto

### Antes de las Correcciones
- Conteos inconsistentes entre scripts
- Confusión sobre qué es "operable"
- "Aparentes contradicciones" (falsos)
- Difícil depurar si hay discrepancias

### Después de las Correcciones
- ✅ Definición única y oficial
- ✅ Todos los scripts usan mismos filtros
- ✅ Conteos consistentes (3,881)
- ✅ Fácil validar: ejecutar `validate_operability_consistency.py`
- ✅ Guía clara para scripts futuros

---

## Próximos Pasos

1. **Usar OPERABILITY_DEFINITION.md** como referencia
2. **Ejecutar validate_operability_consistency.py** regularmente
3. **Copiar plantilla** de SCRIPT_VALIDATION_CHECKLIST.md para nuevos scripts
4. **Documentar constantes** en la cabecera de cada script

---

## Última Actualización

**Fecha**: 2026-01-13
**Versión**: 1.0
**Estado**: Completado ✅

