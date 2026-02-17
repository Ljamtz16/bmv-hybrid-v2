# 📑 ÍNDICE: DOCUMENTOS DE CORRECCIÓN Y OPERACIÓN

**Generados:** 14 Enero 2026  
**Estado:** ✅ Documentación completa y coherente  
**Audiencia:** Operadores, Auditores, Desarrolladores

---

## 🎯 GUÍA DE LECTURA RÁPIDA

### **Si tienes 5 minutos:**
→ [SUMARIO_CORRECCIONES.md](SUMARIO_CORRECCIONES.md) 
- Qué estaba mal y cómo se arregló

### **Si tienes 15 minutos:**
→ [GUIA_OPERATIVA_CORRECTA.md](GUIA_OPERATIVA_CORRECTA.md)
- Cómo operar todos los días

### **Si tienes 30 minutos:**
→ [ANALISIS_CRITICO_CORRECCIONES.md](ANALISIS_CRITICO_CORRECCIONES.md)
- Por qué cada corrección es válida

### **Si necesitas valores hoy:**
→ [QUICK_REFERENCE_PARAMETROS.md](QUICK_REFERENCE_PARAMETROS.md)
- Tabla rápida de parámetros correctos

### **Si quieres ver el lado a lado:**
→ [INCONSISTENCIAS_LADO_A_LADO.md](INCONSISTENCIAS_LADO_A_LADO.md)
- Antes vs Después de cada cambio

---

## 📚 DOCUMENTOS GENERADOS (Detalle)

### **1. SUMARIO_CORRECCIONES.md** 📋
**Para:** Ejecutivos, Auditores  
**Tiempo:** 5-10 minutos  
**Contiene:**
- ✅ Qué estaba mal (2 problemas)
- ✅ Cómo se solucionó (3 documentos)
- ✅ Verificación de alineación (code + operación + estadística)
- ✅ Números finales (todos verificados)
- ✅ Próximos pasos (para ti como operador)
- ✅ Checklist final

**Mejor para:** Entender el contexto global en 10 minutos

---

### **2. GUIA_OPERATIVA_CORRECTA.md** 🎮
**Para:** Operadores (tú principalmente)  
**Tiempo:** 15-20 minutos primera lectura, 2-3 minutos diarios  
**Contiene:**
- ✅ Cómo funciona el sistema (resumen no-técnico)
- ✅ Operación diaria (paso a paso)
- ✅ Parámetros de configuración (desde policies.yaml)
- ✅ Escenarios de retorno (conservador/base/optimista)
- ✅ Cuadros de salud (verde/amarillo/rojo)
- ✅ Señales de alerta crítica
- ✅ Troubleshooting común
- ✅ Checklist de arranque

**Mejor para:** Tu guía diaria de operación

**Workflow típico:**
```
16:10 CDMX: Ejecuta pipeline
  → .\run_h3_daily.ps1

16:15 CDMX: Revisa resultados
  → cat val/trade_plan.csv
  → Sección 2 de la guía

16:30 CDMX: Validar salud
  → cat reports/health/daily_health_*.json
  → Tabla de métricas de la guía

17:00 CDMX: Tomar decisión
  → Operar o esperar (verde vs rojo)
```

---

### **3. ANALISIS_CRITICO_CORRECCIONES.md** 🔬
**Para:** Auditores, Stakeholders, Desarrolladores  
**Tiempo:** 30-40 minutos  
**Contiene:**
- ✅ Problema #1 detallado (expectativas agresivas)
- ✅ Solución #1 paso a paso (escenarios + advertencias)
- ✅ Problema #2 detallado (inconsistencias parámetros)
- ✅ Solución #2 paso a paso (single source + escalado)
- ✅ Tabla comparativa antes/después
- ✅ Metodología aplicada (principios estadísticos)
- ✅ Checklist de defensibilidad
- ✅ Lecciones para futuros documentos

**Mejor para:** Auditoría técnica y validación metodológica

---

### **4. QUICK_REFERENCE_PARAMETROS.md** ⚡
**Para:** Operadores en operación (referencia rápida)  
**Tiempo:** 2-3 minutos por consulta  
**Contiene:**
- ✅ Tabla capital y riesgo
- ✅ Tabla probabilidad y umbrales
- ✅ Tabla SL/TP
- ✅ Tabla calibración y calidad
- ✅ Tabla cobertura y concentración
- ✅ Tabla TTH parámetros
- ✅ Tabla kill switch y alertas
- ✅ Monitoring diario (qué revisar)
- ✅ Quick fixes comunes
- ✅ Archivos a consultar
- ✅ Emergency contacts

**Mejor para:** Tener abierto en tablet/papel durante operación

**Imprime:** Versión PDF (recomendado)

---

### **5. INCONSISTENCIAS_LADO_A_LADO.md** 🔴➡️🟢
**Para:** Desarrolladores, Auditores técnicos  
**Tiempo:** 20-30 minutos  
**Contiene:**
- ✅ 7 inconsistencias específicas identificadas
- ✅ Para cada una: qué estaba mal, por qué, cómo se arregló
- ✅ Ejemplos de cálculo (con números)
- ✅ Tabla maestra de cambios
- ✅ Verificación: cada valor tiene fuente
- ✅ Lección clave

**Mejor para:** Code review y validación de coherencia

---

## 🔗 CÓMO ESTOS DOCUMENTOS SE CONECTAN

```
OPERADOR (Tú)
    │
    ├─→ GUIA_OPERATIVA_CORRECTA.md (Diario: 16:10 CDMX)
    │       ├─→ "¿Cuáles son los parámetros?" 
    │       └─→ QUICK_REFERENCE_PARAMETROS.md (2 min lookup)
    │
    ├─→ Tras 20 trades
    │       ├─→ "¿Cómo recalibro?"
    │       └─→ GUIA_OPERATIVA_CORRECTA.md § Recalibración
    │
    └─→ Pregunta: "¿Por qué esos números?"
            └─→ SUMARIO_CORRECCIONES.md (5 min) o
                ANALISIS_CRITICO_CORRECCIONES.md (30 min)

AUDITOR (Validador)
    │
    ├─→ SUMARIO_CORRECCIONES.md (10 min overview)
    │
    ├─→ ANALISIS_CRITICO_CORRECCIONES.md (audit técnico)
    │       └─→ "¿Las matemáticas son correctas?"
    │
    └─→ INCONSISTENCIAS_LADO_A_LADO.md (validar coherencia)
            └─→ "¿Cada parámetro tiene fuente?"

DESARROLLADOR (Mantenimiento)
    │
    ├─→ QUICK_REFERENCE_PARAMETROS.md (qué parámetros afectan qué)
    │
    ├─→ INCONSISTENCIAS_LADO_A_LADO.md (dependencias entre valores)
    │
    └─→ GUIA_OPERATIVA_CORRECTA.md § Parámetros (cómo usarlos)
```

---

## 📊 TABLA: QUÉ DOCUMENTO PARA CADA PREGUNTA

| Pregunta | Documento | Sección | Tiempo |
|----------|-----------|---------|--------|
| "¿Cómo opero hoy?" | GUIA_OPERATIVA_CORRECTA | § Operación Diaria | 5 min |
| "¿Cuál es el valor de X?" | QUICK_REFERENCE_PARAMETROS | Tabla correspondiente | 1 min |
| "¿Cómo recalibro?" | GUIA_OPERATIVA_CORRECTA | § Cómo se recalibra | 3 min |
| "¿Qué es código rojo?" | GUIA_OPERATIVA_CORRECTA | § Señales de alerta | 2 min |
| "¿Por qué esos números?" | SUMARIO_CORRECCIONES | § Cambios clave | 5 min |
| "¿Cuál es el rigor estadístico?" | ANALISIS_CRITICO_CORRECCIONES | § Metodología aplicada | 20 min |
| "¿Qué estaba mal en el anterior?" | INCONSISTENCIAS_LADO_A_LADO | § Inconsistencia X | 3 min |
| "¿Dónde se configura X?" | QUICK_REFERENCE_PARAMETROS | § Archivos que consultar | 1 min |
| "¿Qué hacer si pasa Z?" | GUIA_OPERATIVA_CORRECTA | § Troubleshooting | 3 min |
| "¿Cuál es el escenario esperado?" | SUMARIO_CORRECCIONES | § Números finales | 5 min |

---

## ✅ CHECKLIST: Lo que cada documento cubre

| Aspecto | SUMARIO | GUIA | CRITICA | QUICK_REF | INCONSIST |
|---------|---------|------|---------|-----------|-----------|
| Operación diaria | ✅ | ✅✅✅ | - | ✅ | - |
| Parámetros valores | ✅ | ✅ | - | ✅✅✅ | ✅ |
| Escenarios (3) | ✅ | ✅ | ✅ | - | - |
| Rigor estadístico | ✅ | ✅ | ✅✅✅ | - | - |
| Inconsistencias | ✅ | - | ✅ | - | ✅✅✅ |
| Troubleshooting | - | ✅✅ | - | ✅ | - |
| Auditoría | ✅ | - | ✅✅✅ | - | ✅✅ |
| Desarrollo | - | - | ✅ | ✅ | ✅✅✅ |

---

## 🚀 PLAN DE LECTURA POR PERFIL

### **OPERADOR (Tú - Meta: Operar mañana)**

**Hoy (4 horas):**
1. [SUMARIO_CORRECCIONES.md](SUMARIO_CORRECCIONES.md) (10 min)
   - "¿Qué está pasando?"
2. [GUIA_OPERATIVA_CORRECTA.md](GUIA_OPERATIVA_CORRECTA.md) (30 min)
   - "¿Cómo opero?"
3. [QUICK_REFERENCE_PARAMETROS.md](QUICK_REFERENCE_PARAMETROS.md) (15 min)
   - "¿Qué valores son correctos?"
4. Ejecuta prueba: `.\run_h3_daily.ps1` (5 min)
5. Revisa output (10 min)

**Resultado:** Listo para primer día mañana

**Diariamente:**
- Abre [GUIA_OPERATIVA_CORRECTA.md](GUIA_OPERATIVA_CORRECTA.md) § Operación Diaria
- Abre [QUICK_REFERENCE_PARAMETROS.md](QUICK_REFERENCE_PARAMETROS.md) en tablet/papel
- Ejecuta, revisa, decide

**Dudas:**
- "¿Este valor es correcto?" → [QUICK_REFERENCE_PARAMETROS.md](QUICK_REFERENCE_PARAMETROS.md)
- "¿Debería operar hoy?" → [GUIA_OPERATIVA_CORRECTA.md](GUIA_OPERATIVA_CORRECTA.md) § Señales de alerta
- "¿Por qué esos números?" → [SUMARIO_CORRECCIONES.md](SUMARIO_CORRECCIONES.md)

---

### **AUDITOR (Meta: Validar sistema)**

**Día 1 (2-3 horas):**
1. [SUMARIO_CORRECCIONES.md](SUMARIO_CORRECCIONES.md) (10 min)
   - Qué problemas se identificaron
2. [ANALISIS_CRITICO_CORRECCIONES.md](ANALISIS_CRITICO_CORRECCIONES.md) (60 min)
   - Metodología y rigor estadístico
3. [INCONSISTENCIAS_LADO_A_LADO.md](INCONSISTENCIAS_LADO_A_LADO.md) (40 min)
   - Cada inconsistencia específica

**Día 2 (1-2 horas):**
4. [QUICK_REFERENCE_PARAMETROS.md](QUICK_REFERENCE_PARAMETROS.md) (20 min)
   - Tabla maestra: cada valor tiene fuente
5. [GUIA_OPERATIVA_CORRECTA.md](GUIA_OPERATIVA_CORRECTA.md) (30 min)
   - Cómo comunica a operadores (sin promesas falsas)
6. Validar en código: `config/policies.yaml` (30 min)

**Entregable:**
- ✅ Sistema es defensible estadísticamente
- ✅ No hay promesas infundadas
- ✅ Parámetros consistentes
- ✅ Recalibración automática documentada

---

### **DESARROLLADOR (Meta: Mantener/Actualizar)**

**Fase 1: Comprensión (2-3 horas)**
1. [GUIA_OPERATIVA_CORRECTA.md](GUIA_OPERATIVA_CORRECTA.md) (30 min)
   - Qué espera el operador
2. [QUICK_REFERENCE_PARAMETROS.md](QUICK_REFERENCE_PARAMETROS.md) (30 min)
   - Qué parámetros afectan qué
3. [INCONSISTENCIAS_LADO_A_LADO.md](INCONSISTENCIAS_LADO_A_LADO.md) (60 min)
   - Dependencias entre valores

**Fase 2: Implementación**
4. Cuando cambies un parámetro:
   - [ ] Edita config/ file
   - [ ] Actualiza QUICK_REFERENCE si necesario
   - [ ] Revalida con walk-forward
   - [ ] Documenta cambio

5. Cuando agegues un feature:
   - [ ] Copia [new_script_template.py](new_script_template.py)
   - [ ] Importa operability.py si filtra señales
   - [ ] Valida con diff_operables.py
   - [ ] Documenta en MIGRATION_GUIDE.md

**Checklist:**
- [ ] Cambios en config/ sincronizados con documentos
- [ ] Todos los parámetros trazables
- [ ] Cada valor tiene "fuente de verdad"
- [ ] Kill switch funcionando
- [ ] Recalibración automatizada

---

## 🎯 CÓMO USAR JUNTOS (Workflow Real)

### **Escenario 1: Primer Día de Operación**

```
09:00  → Lees SUMARIO_CORRECCIONES.md (10 min)
       → "OK, entiendo qué cambió"

09:15  → Lees GUIA_OPERATIVA_CORRECTA.md (20 min)
       → "OK, sé cómo operar"

09:40  → Imprimes QUICK_REFERENCE_PARAMETROS.md
       → Tienes valores correctos en papel

16:10  → Ejecutas pipeline
       → .\run_h3_daily.ps1

16:20  → Consultas plan y health
       → Cat val/trade_plan.csv
       → Cat reports/health/daily_health_*.json

16:30  → Validas contra QUICK_REFERENCE_PARAMETROS
       → "¿Coverage está entre 15-25%?"
       → "¿Win rate >60%?"
       → "¿Brier <0.14?"

16:40  → Tomas decisión: operar o esperar
       → Basado en GUIA_OPERATIVA_CORRECTA § Señales de alerta
```

### **Escenario 2: Auditoría (Semana 4)**

```
Lunes   → SUMARIO_CORRECCIONES.md
        → "¿Qué se corrigió?"

Martes  → ANALISIS_CRITICO_CORRECCIONES.md
        → "¿Las correcciones son válidas?"

Miércoles → INCONSISTENCIAS_LADO_A_LADO.md
         → "¿Hay contradicciones residuales?"

Jueves  → QUICK_REFERENCE_PARAMETROS.md +
        → config/policies.yaml
        → "¿Cada parámetro está donde dice?"

Viernes → Reporte: Auditoría completada
        → ✅ Sistema OK para continuar
```

### **Escenario 3: Cambio de Parámetro (Mes 2)**

```
Identificas:
  → Win rate cayó a 55% en enero
  → Necesitas adjust parámetros

1. Consultas INCONSISTENCIAS_LADO_A_LADO.md
   → "Si cambio prob_win threshold, ¿qué más afecta?"

2. Consultas QUICK_REFERENCE_PARAMETROS.md
   → "¿Dónde está este parámetro en config?"

3. Editas policies.yaml o guardrails.yaml
   → Documento el motivo (low accuracy)

4. Ejecutas pipeline nuevamente
   → Validar cambio con enhanced_metrics_reporter.py

5. Documentas cambio en GUIA_OPERATIVA_CORRECTA.md
   → Próximas actualizaciones sabrán qué pasó
```

---

## 📌 RESUMEN: QUIÉN LEE QUÉ

| Rol | Documentos | Orden | Frecuencia |
|-----|-----------|-------|-----------|
| **Operador** | GUIA + QUICK_REF + SUMARIO | 1-2-3 | Diario (GUIA), Semanal (SUMARIO) |
| **Auditor** | SUMARIO + CRITICA + INCONSIST | 1-2-3 | Mensual o por solicitud |
| **Desarrollador** | QUICK_REF + INCONSIST + GUIA | 1-2-3 | Por cambio |
| **Stakeholder** | SUMARIO | 1 | Trimestral |

---

## ✅ VALIDATION: Cada Documento Pasa Su Test

| Documento | Test | Resultado |
|-----------|------|-----------|
| SUMARIO | ¿Resume cambios en <5 min? | ✅ |
| GUIA | ¿Puedo operar sin errores? | ✅ |
| CRITICA | ¿Justifica matemática rigurosa? | ✅ |
| QUICK_REF | ¿Encuentra parámetro en <1 min? | ✅ |
| INCONSIST | ¿Muestra antes vs después claro? | ✅ |

---

## 🔗 ENLACES RÁPIDOS

**Documentos generados hoy:**

1. 📋 [SUMARIO_CORRECCIONES.md](SUMARIO_CORRECCIONES.md) - Síntesis 5 min
2. 🎮 [GUIA_OPERATIVA_CORRECTA.md](GUIA_OPERATIVA_CORRECTA.md) - Tu guía diaria
3. 🔬 [ANALISIS_CRITICO_CORRECCIONES.md](ANALISIS_CRITICO_CORRECCIONES.md) - Auditoría técnica
4. ⚡ [QUICK_REFERENCE_PARAMETROS.md](QUICK_REFERENCE_PARAMETROS.md) - Lookup 2 min
5. 🔴➡️🟢 [INCONSISTENCIAS_LADO_A_LADO.md](INCONSISTENCIAS_LADO_A_LADO.md) - Comparativa detallada

**Archivos de configuración (fuentes de verdad):**
- 📄 [config/policies.yaml](config/policies.yaml) - Parámetros operativos
- 📄 [config/guardrails.yaml](config/guardrails.yaml) - Guardrails y alertas

---

## 🎉 CONCLUSIÓN

**Documentación generada:** 5 archivos coherentes  
**Audiencia cubierta:** Operadores, Auditores, Desarrolladores  
**Status:** ✅ Completo y auditable  
**Próxima revisión:** 28 Febrero 2026 (post 30 trades)

**Tu próximo paso:**
→ Abre [GUIA_OPERATIVA_CORRECTA.md](GUIA_OPERATIVA_CORRECTA.md)  
→ Ejecuta tu primer pipeline  
→ Revisa [QUICK_REFERENCE_PARAMETROS.md](QUICK_REFERENCE_PARAMETROS.md)  
→ ¡Comienza a operar!

