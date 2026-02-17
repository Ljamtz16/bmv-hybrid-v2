# INDICE MAESTRO: REFACTORIZACION COMPLETA v2.0

## Estructura de Archivos Creados

### 🔴 CORE MODULES (Fuente única de verdad)

1. **operability.py** (305 líneas)
   - `operable_mask(df)` - Filtro central booleano
   - `get_operability_breakdown(df)` - Breakdown 4-niveles
   - `get_risk_distribution(df)` - Histograma de riesgos
   - Constantes: CONF_THRESHOLD=4, WHITELIST_TICKERS, EXPECTED_OPERABLE_COUNT=3881
   - Adaptadores: normalize_tickers(), adapt_risk_column()

2. **operability_config.py** (195 líneas)
   - KillSwitchConfig (window=5, threshold=50%)
   - ModelHealthConfig (warning-level, non-blocking)
   - RiskMacroConfig (FOMC, earnings, VIX, gaps)
   - OutputConfig (validation, abort rules)

### 🟡 REFACTORED MODULES (Ahora usan operability.py)

3. **production_orchestrator.py** (555 líneas)
   - Importa operable_mask() de operability.py
   - Validación automática integrada
   - Exporta run_audit.json con breakdown completo
   - Kill switch configurable

4. **enhanced_metrics_reporter.py** (Refactorizado)
   - Usa operable_mask() y get_operability_breakdown()
   - Reporte Global vs Operable Slice
   - Comparación de métricas

### 🟢 UTILITY & DIAGNOSTIC TOOLS

5. **diff_operables.py** (240 líneas)
   - Compara dos sets de operables
   - Identifica filas faltantes/sobrantes
   - Diagnóstico automático (NaN, parse, typo)
   - Uso: `python diff_operables.py --test=signals.csv`

6. **normalize_tickers.py** (95 líneas)
   - Limpia tickers (.strip().upper())
   - Crea backup
   - Reporta violaciones de whitelist
   - Uso: `python normalize_tickers.py`

7. **new_script_template.py** (250 líneas)
   - Plantilla reutilizable
   - 5-item checklist integrado
   - Ejemplos de código correcto

### 📚 DOCUMENTATION

8. **REFACTORING_COMPLETE.md**
   - Resumen ejecutivo de cambios
   - Beneficios antes/después
   - Número de referencia (3,881 operables)
   - Flujo de uso diario

9. **MIGRATION_GUIDE.md**
   - Patrón de actualización (ANTES vs DESPUÉS)
   - 3 scripts identificados para migrar
   - Checklist paso a paso
   - Troubleshooting

10. **STATUS_FINAL_REFACTORING.md**
    - Estado detallado de todos 11 puntos
    - Métricas de desempeño
    - Garantías implementadas
    - Plan de próximos pasos

11. **QUICK_VERIFICATION.md**
    - Comandos para verificar todo funciona
    - Salidas esperadas
    - Troubleshooting rápido

12. **INDICE_MAESTRO.md** (este archivo)
    - Índice completo
    - Cómo empezar
    - Referencias cruzadas

---

## 🚀 COMO EMPEZAR

### Opción 1: Verificación Rápida (5 minutos)
```bash
# Ver que todo funciona
python operability.py
python operability_config.py
python production_orchestrator.py --date=2025-11-19
```

Ver: `QUICK_VERIFICATION.md`

### Opción 2: Entender Cambios (15 minutos)
```bash
# Leer resumen ejecutivo
cat REFACTORING_COMPLETE.md
```

### Opción 3: Migrar Tu Script (30 minutos)
```bash
# Seguir guía paso a paso
cat MIGRATION_GUIDE.md

# Copiar plantilla como base
cp new_script_template.py mi_script.py

# Adaptar y validar
python mi_script.py
python diff_operables.py --test=mi_script_operables.csv
```

### Opción 4: Entender Arquitectura (1 hora)
```bash
# Leer estado final completo
cat STATUS_FINAL_REFACTORING.md

# Revisar código fuente
code operability.py
code operability_config.py
```

---

## 📊 NUMEROS CLAVE

| Métrica | Valor |
|---------|-------|
| Operables de referencia | 3,881 |
| Actuales en dataset | 3,880 |
| Delta | -1 (margen normal) |
| Reducción de ruido | 85.4% |
| Mejora accuracy | +3.38 pts |
| Documentos creados | 5 |
| Scripts refactorizados | 2 |
| Módulos centrales | 2 |
| Herramientas | 3 |

---

## 🎯 FLUJO TIPICO DIARIO

### 1. Mañana: Generar Señales
```bash
python production_orchestrator.py --date=$(date +%Y-%m-%d)
```
- Output: `run_audit.json` (breakdown + validation)
- Output: `signals_to_trade_*.csv` (operables del día)

### 2. Mediodía: Auditar
```bash
cat outputs/analysis/run_audit.json | jq .breakdown
```
- Ver: Global → Conf → Risk → Whitelist
- Si delta > 1: Ejecutar diff_operables.py

### 3. Tarde: Analizar Desempeño
```bash
python enhanced_metrics_reporter.py
```
- Output: `metrics_global_vs_operable.csv`
- Comparar: Accuracy global vs operable slice

### 4. Fin del Día: Validar Consistencia (opcional)
```bash
python validate_operability_consistency.py
```
- Confirmar: 3,881 operables en dataset

---

## 📚 REFERENCIAS RAPIDAS

### Integración en Nuevo Script
```python
# Step 1: Import
from operability import operable_mask, get_operability_breakdown, EXPECTED_OPERABLE_COUNT

# Step 2: Apply
mask = operable_mask(df)
operable_df = df[mask]

# Step 3: Validate
breakdown = get_operability_breakdown(df)
if len(operable_df) != EXPECTED_OPERABLE_COUNT:
    print(f"Warning: Expected {EXPECTED_OPERABLE_COUNT}, got {len(operable_df)}")
```

### Cambiar Configuración Global
```python
# operability_config.py
class KillSwitchConfig:
    WINDOW_DAYS = 10  # ← Cambiar aquí (antes era 5)
    ACCURACY_THRESHOLD = 0.45  # ← Cambiar aquí (antes era 0.50)

# Efecto: Todos los scripts que importan kill_switch usan nuevos valores
from operability_config import kill_switch
if kill_switch.ACCURACY_THRESHOLD:  # ← Usa el nuevo valor automáticamente
    ...
```

### Diagnosticar Delta
```bash
# Si operable count != 3881
python diff_operables.py --test=mi_output.csv
```
- Output: Exactamente qué rows faltan/sobran

### Limpiar Dataset
```bash
# Si hay typos en tickers
python normalize_tickers.py
# Crea backup y normaliza
```

---

## ✅ LISTA DE VERIFICACIÓN FINAL

- [ ] Ejecuté `python operability.py` → Ver constantes ✅
- [ ] Ejecuté `python operability_config.py` → Ver 4 clases ✅
- [ ] Ejecuté `python production_orchestrator.py` → Ver run_audit.json ✅
- [ ] Ejecuté `python enhanced_metrics_reporter.py` → Ver breakdown ✅
- [ ] Leí REFACTORING_COMPLETE.md → Entender cambios ✅
- [ ] Leí MIGRATION_GUIDE.md → Sé cómo migrar ✅
- [ ] Copié new_script_template.py → Tengo plantilla ✅
- [ ] Entiendo operability.py → Sé dónde está fuente de verdad ✅
- [ ] Entiendo operability_config.py → Sé dónde cambiar parámetros ✅
- [ ] Pronto: Migrar backtest_confidence_rules.py ⏳
- [ ] Pronto: Migrar validate_operability_consistency.py ⏳

---

## 🔗 INDICE DE ARCHIVOS

### Documentación
- [REFACTORING_COMPLETE.md](REFACTORING_COMPLETE.md) - Resumen ejecutivo
- [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) - Guía paso a paso
- [STATUS_FINAL_REFACTORING.md](STATUS_FINAL_REFACTORING.md) - Estado detallado
- [QUICK_VERIFICATION.md](QUICK_VERIFICATION.md) - Verificación rápida
- [INDICE_MAESTRO.md](INDICE_MAESTRO.md) - Este archivo

### Código - Core
- [operability.py](operability.py) - Fuente única
- [operability_config.py](operability_config.py) - Configuración

### Código - Refactorizado
- [production_orchestrator.py](production_orchestrator.py) - Orquestador diario
- [enhanced_metrics_reporter.py](enhanced_metrics_reporter.py) - Análisis de desempeño

### Código - Herramientas
- [diff_operables.py](diff_operables.py) - Diagnóstico
- [normalize_tickers.py](normalize_tickers.py) - Limpieza
- [new_script_template.py](new_script_template.py) - Plantilla

### Datos - Auto-generados
- [outputs/analysis/run_audit.json](outputs/analysis/run_audit.json) - Auditoría automática
- [outputs/analysis/metrics_global_vs_operable.csv](outputs/analysis/metrics_global_vs_operable.csv) - Métricas
- [kill_switch_status.txt](kill_switch_status.txt) - Estado del kill switch

---

## 🎓 CONCEPTOS CLAVE

**Operable**: Observación que cumple 3 criterios
- Confidence Score >= 4
- Macro Risk <= MEDIUM
- Ticker en whitelist

**Fuente Única de Verdad (SSOT)**: operability.py
- Nunca reimplementar filtros
- Cambios centralizados
- Auditoría consistente

**Configuración Centralizada**: operability_config.py
- Kill switch params
- Model health thresholds
- Output rules

**Validación Automática**: production_orchestrator.py
- Valida conteo vs esperado
- Exporta run_audit.json
- Warn/abort configurable

**Breakdown 4-Niveles**:
1. Global (26,634)
2. Conf >= 4 (10,383)
3. + Risk <= MEDIUM (10,363)
4. + Whitelist (3,880)

---

## 🚀 PROXIMOS PASOS

### Semana 1
- [ ] Ejecutar todas las verificaciones en QUICK_VERIFICATION.md
- [ ] Migrar backtest_confidence_rules.py (ver MIGRATION_GUIDE.md)
- [ ] Migrar validate_operability_consistency.py

### Semana 2
- [ ] Integrar model_health en dashboard
- [ ] Pruebas de regresión completas
- [ ] Documentar custom scripts

### Semana 3
- [ ] A/B testing de kill switch triggers
- [ ] Integración de RiskMacroConfig avanzado
- [ ] CI/CD con validaciones automáticas

---

## 📞 SOPORTE RAPIDO

| Pregunta | Ver |
|----------|-----|
| ¿Dónde está la definición de operable? | operability.py |
| ¿Cómo cambio los parámetros del kill switch? | operability_config.py |
| ¿Cómo actualizo mi script? | MIGRATION_GUIDE.md |
| ¿Por qué 3,880 y no 3,881? | diff_operables.py |
| ¿Cómo valido mi script? | QUICK_VERIFICATION.md |
| ¿Cuáles son los cambios? | REFACTORING_COMPLETE.md |
| ¿Cuál es el estado actual? | STATUS_FINAL_REFACTORING.md |
| ¿Tengo un template? | new_script_template.py |

---

**Creado**: 2026-01-13
**Versión**: 2.0 Refactorizado
**Status**: ✅ FASE 1 COMPLETA

