# COMANDOS RAPIDOS - COPY & PASTE

## 🚀 VERIFICACION RAPIDA (5 MINUTOS)

### 1️⃣ Verificar módulos cargan
```bash
.venv\Scripts\python.exe operability.py
.venv\Scripts\python.exe operability_config.py
```

**Expected**: Constantes y configs impresas

### 2️⃣ Ejecutar orquestador diario
```bash
.venv\Scripts\python.exe production_orchestrator.py --date=2025-11-19
```

**Expected**: Breakdown 26,634 → 10,383 → 10,363 → 3,880

### 3️⃣ Ejecutar análisis de desempeño
```bash
.venv\Scripts\python.exe enhanced_metrics_reporter.py
```

**Expected**: Global 48.81%, Operable 52.19%, Mejora +3.38 pts

### 4️⃣ Validar consistencia (opcional)
```bash
.venv\Scripts\python.exe validate_operability_consistency.py
```

**Expected**: 3,881 operables, Status: ✅

---

## 📊 DIAGNOSTICO (Si hay problemas)

### ¿Delta mismatch?
```bash
# Generar tu salida
.venv\Scripts\python.exe mi_script.py > salida_mia.csv

# Diagnosticar diferencia
.venv\Scripts\python.exe diff_operables.py --test=salida_mia.csv
```

### ¿Tickers sucios?
```bash
# Normalizar
.venv\Scripts\python.exe normalize_tickers.py
# Crea: my_data_BACKUP.csv (original)
# Crea: my_data_normalized.csv (limpio)
```

---

## 📚 LEER DOCUMENTACION

### Quick Start (5 min)
```bash
cat REFACTORING_COMPLETE.md
```

### Entender cambios (15 min)
```bash
cat STATUS_FINAL_REFACTORING.md
```

### Migrar script (30 min)
```bash
cat MIGRATION_GUIDE.md
```

### Ver todo (1 hora)
```bash
cat INDICE_MAESTRO.md
```

---

## 💻 CREAR NUEVO SCRIPT

### Paso 1: Copiar template
```bash
copy new_script_template.py mi_analisis.py
```

### Paso 2: Editar (mantener imports)
```python
from operability import operable_mask, get_operability_breakdown, EXPECTED_OPERABLE_COUNT
```

### Paso 3: Ejecutar
```bash
.venv\Scripts\python.exe mi_analisis.py
```

### Paso 4: Validar
```bash
.venv\Scripts\python.exe diff_operables.py --test=mi_analisis_operables.csv
```

---

## 🔧 CAMBIAR CONFIGURACION

### Cambiar kill switch
```python
# operability_config.py
class KillSwitchConfig:
    WINDOW_DAYS = 10  # antes: 5
    ACCURACY_THRESHOLD = 0.45  # antes: 0.50
```
Ejecutar production_orchestrator.py → usa nuevos valores automáticamente

### Cambiar thresholds de riesgo
```python
# operability_config.py
class RiskMacroConfig:
    FOMC_PROXIMITY_DAYS = 3  # antes: 2
    DEFAULT_RISK = "LOW"     # antes: "MEDIUM"
```

### Ver configuración actual
```bash
.venv\Scripts\python.exe operability_config.py
```

---

## 📊 DATOS TIPICOS

### Breakdown esperado
```
Global:     26,634 (100%)
Conf >= 4:  10,383 (38.98%)
+Risk<=MED: 10,363 (38.91%)
+Whitelist:  3,880 (14.57%)
Expected:    3,881
```

### Delta normal
```
3,880 - 3,881 = -1 ✅ NORMAL
```

### Performance
```
Global accuracy:    48.81%
Operable accuracy:  52.19%
Improvement:        +3.38 pts
Noise reduction:    85.4%
```

---

## 🔍 VERIFICAR AUDIT

### Ver último audit
```bash
type outputs\analysis\run_audit.json
```

### Ver breakdown en audit
```bash
# Powershell
(Get-Content outputs\analysis\run_audit.json | ConvertFrom-Json).breakdown
```

### Ver validation status
```bash
# Powershell
(Get-Content outputs\analysis\run_audit.json | ConvertFrom-Json).validation
```

### Ver kill switch state
```bash
# Powershell
(Get-Content outputs\analysis\run_audit.json | ConvertFrom-Json).kill_switch
```

---

## 📝 ESCRIBIR SCRIPT DESDE CERO

### Estructura mínima
```python
#!/usr/bin/env python
"""Mi análisis"""

from operability import operable_mask, get_operability_breakdown, EXPECTED_OPERABLE_COUNT
import pandas as pd

def main():
    # 1. Load data
    df = pd.read_csv("mi_data.csv")
    
    # 2. Calculate macro_risk if needed
    df["macro_risk"] = calculate_risk_level(df["date"])  # or "MEDIUM" for all
    
    # 3. Apply operability mask
    mask = operable_mask(df)
    operable_df = df[mask]
    
    # 4. Print breakdown
    breakdown = get_operability_breakdown(df)
    print(f"Global: {breakdown['global']:,}")
    print(f"Operable: {breakdown['operable']:,}")
    
    # 5. Validate
    if len(operable_df) != EXPECTED_OPERABLE_COUNT:
        print(f"Warning: Expected {EXPECTED_OPERABLE_COUNT}, got {len(operable_df)}")
    
    # 6. Your logic
    # ... do something with operable_df
    
    # 7. Export
    operable_df.to_csv("mi_output.csv", index=False)

if __name__ == "__main__":
    main()
```

---

## ✅ CHECKLIST DE NUEVO SCRIPT

- [ ] Importé `operable_mask` y `get_operability_breakdown`
- [ ] Importé `EXPECTED_OPERABLE_COUNT`
- [ ] Calculé `macro_risk` antes de usar operable_mask()
- [ ] Apliqué `mask = operable_mask(df)`
- [ ] Imprimí breakdown
- [ ] Validé conteo vs EXPECTED_OPERABLE_COUNT
- [ ] Exporté CSV
- [ ] Ejecuté `diff_operables.py` para validar
- [ ] Resultado: delta <= 1 ✅

---

## 🐛 TROUBLESHOOTING RAPIDO

| Error | Solución |
|-------|----------|
| ModuleNotFoundError: operability | Verificar que operability.py está en mismo directorio |
| KeyError: 'macro_risk' | Agregar: `df["macro_risk"] = "MEDIUM"` o calcular antes |
| 'NoneType' object has no attribute 'values' | Verificar que df no está vacío |
| JSON serialization error | Ya está corregido en production_orchestrator.py |
| Operable count mismatch | Ejecutar: `python diff_operables.py --test=yourfile.csv` |
| Tickers inconsistentes | Ejecutar: `python normalize_tickers.py` |

---

## 🎯 COMANDOS DIARIOS

### Mañana
```bash
# Generar señales y audit
.venv\Scripts\python.exe production_orchestrator.py --date=$(Get-Date -Format 'yyyy-MM-dd')
```

### Mediodía
```bash
# Revisar audit
type outputs\analysis\run_audit.json
```

### Tarde
```bash
# Analizar desempeño
.venv\Scripts\python.exe enhanced_metrics_reporter.py
```

### Fin de día
```bash
# Validar consistencia (opcional)
.venv\Scripts\python.exe validate_operability_consistency.py
```

---

## 📞 SOPORTE RAPIDO

| Pregunta | Archivo | Comando |
|----------|---------|---------|
| ¿Dónde editar parametros? | operability_config.py | `code operability_config.py` |
| ¿Ver parámetros actuales? | - | `.venv\Scripts\python.exe operability_config.py` |
| ¿Dónde está la definición? | operability.py | `code operability.py` |
| ¿Cómo actualizar mi script? | MIGRATION_GUIDE.md | `cat MIGRATION_GUIDE.md` |
| ¿Cómo creo nuevo script? | new_script_template.py | `copy new_script_template.py` |
| ¿Cómo diagnostico delta? | diff_operables.py | `.venv\Scripts\python.exe diff_operables.py` |
| ¿Cómo limpio tickers? | normalize_tickers.py | `.venv\Scripts\python.exe normalize_tickers.py` |

---

## 💡 PRO TIPS

1. **Siempre mostrar breakdown**
   ```python
   breakdown = get_operability_breakdown(df)
   print(f"Operables: {breakdown['operable']:,}")  # Ver qué se usa
   ```

2. **Guardar audit después de cambios**
   ```bash
   # Los datos se guardan en run_audit.json automáticamente
   # Revisar después de cada cambio en config
   ```

3. **Usar template como base**
   ```bash
   copy new_script_template.py mi_nuevo_analisis.py
   # Ya tiene todo lo necesario
   ```

4. **Validar antes de producción**
   ```bash
   .venv\Scripts\python.exe diff_operables.py --test=mi_output.csv
   # Verifica delta automáticamente
   ```

5. **Monitorear kill switch**
   ```bash
   # Revisar run_audit.json diariamente
   # "kill_switch": {"triggered": false, "reason": "..."}
   ```

---

**Última actualización**: 2026-01-13
**Versión**: 2.0 Refactorizado

