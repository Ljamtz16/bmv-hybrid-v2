# MEJORAS DE ROBUSTEZ IMPLEMENTADAS - 26 ENE 2026

## ✅ PRIORIDAD ALTA - IMPLEMENTADAS

### 1. Calendario Real NYSE con Feriados y Early Closes
**Problema resuelto:** Sistema operaba 24/7 sin considerar feriados ni cierres tempranos

**Implementación:**
- ✅ Integración con `pandas_market_calendars` (NYSE calendar oficial)
- ✅ Detección automática de:
  - Feriados (mercado cerrado)
  - Early closes (cierres a las 1:00 PM ET)
  - Horario regular (9:30 AM - 4:00 PM ET)
- ✅ Función `is_market_open_advanced()` retorna:
  - `is_open`: bool (¿mercado abierto?)
  - `reason`: str (explicación detallada)
  - `is_early_close`: bool (¿cierre temprano hoy?)

**Ejemplo de mensajes:**
```
🔴 Mercado cerrado (feriado o fin de semana)
🔴 Mercado cerrado (cerró 01:00 PM) [Early Close]
🟢 Mercado abierto hasta 04:00 PM
```

---

### 2. Separación: "Market Open" vs "Trade Allowed"
**Problema resuelto:** Operaciones durante alta volatilidad (apertura/cierre)

**Implementación:**
- ✅ Función `is_trading_allowed()` con ventanas prohibidas:
  - **Evitar primeros 5 minutos** después de apertura (9:30 - 9:35 AM ET)
  - **Evitar últimos 10 minutos** antes de cierre (3:50 - 4:00 PM ET)
- ✅ Configurable vía constantes:
  - `AVOID_FIRST_MINUTES = 5`
  - `AVOID_LAST_MINUTES = 10`

**Estados visuales:**
```
🟢 OPERANDO              → Todo OK, trading activo
🟡 ABIERTO - Evitando primeros 5 min (espera 3 min)
🟡 ABIERTO - Evitando últimos 10 min antes de cierre
🔴 CERRADO - Mercado cerrado (cerró 04:00 PM)
```

---

### 3. Cooldown y Lock File (Anti Loop de Regeneración)
**Problema resuelto:** Regeneración múltiple de planes en segundos

**Implementación:**
- ✅ **Lock File:** `val/generation.lock`
  - Se crea al iniciar generación
  - Se elimina al finalizar
  - Previene ejecuciones concurrentes
  
- ✅ **Cooldown:** `COOLDOWN_MINUTES = 5`
  - No regenera más de 1 vez cada 5 minutos
  - Función `can_regenerate_plan()` valida tiempo transcurrido
  - Mensaje: `"Cooldown activo (espera 3 min)"`

**Flujo protegido:**
```
1. Todas las posiciones se cierran
2. ¿Lock activo? → ESPERA
3. ¿Cooldown activo? → ESPERA
4. ¿Mercado abierto? → Verificar
5. ¿Trading permitido? → Verificar
6. ¿Datos frescos? → Verificar
7. ✅ GENERAR PLAN
```

---

### 4. Persistencia Atómica del Estado
**Problema resuelto:** Corrupción de estado en escritura

**Implementación:**
- ✅ Archivo: `val/system_state.json`
- ✅ Escritura atómica: `write temp → rename`
- ✅ Funciones: `load_state()` / `save_state()`

**Contenido del estado:**
```json
{
  "last_generation": "2026-01-26T10:45:23",
  "plan_id": "20260126_104523",
  "last_close_all": "2026-01-26T10:40:15",
  "generation_reason": "auto_reload",
  "closed_positions_tracked": ["AAPL_BUY_248.04_2026-01-20", ...]
}
```

**Usos:**
- Cooldown: validar `last_generation`
- Duplicados: track en `closed_positions_tracked`
- Auditoría: `plan_id` + `generation_reason`
- Dashboard: mostrar en tooltip del badge

---

### 5. Validación de Freshness de Datos
**Problema resuelto:** Generar planes con precios obsoletos

**Implementación:**
- ✅ Función: `validate_data_freshness(tickers)`
- ✅ Configurable: `MAX_DATA_AGE_MINUTES = 15`
- ✅ Valida timestamp del último dato de yfinance (1m interval)
- ✅ Bloquea generación si datos > 15 minutos

**Lógica:**
```python
last_timestamp = yf.Ticker(ticker).history("1d", "1m").index[-1]
age_minutes = (now_UTC - last_timestamp).total_seconds() / 60

if age_minutes > 15:
    return False, f"Datos obsoletos para {ticker} ({age_minutes} min)"
```

**Mensaje:**
```
⚠️ Datos obsoletos para AAPL (18 min) - Esperando datos frescos...
```

---

### 6. Evitar Duplicados en Historial
**Problema resuelto:** 1,051 registros → 6 trades únicos (1,045 duplicados)

**Implementación:**
- ✅ Generación de `trade_id` único:
  ```
  ticker_side_entry_date_generated_at
  Ej: AAPL_BUY_248.04_2026-01-20_2026-01-26T07:44:12
  ```
- ✅ Tracking en `state['closed_positions_tracked']` (set)
- ✅ Verificación antes de guardar en `check_and_close_positions()`
- ✅ Script de limpieza: `clean_history_duplicates.py`

**Antes:**
```
Total registros: 1051
```

**Después:**
```
Total registros: 6
Duplicados eliminados: 1045
WINS: 2 | LOSSES: 4 | Win Rate: 33.3%
P&L Total: $-9.66
```

---

### 7. Dashboard: Indicadores de Estado Avanzados
**Problema resuelto:** Usuario no sabía por qué el sistema no generaba

**Implementación:**
- ✅ Badge de mercado con 3 estados:
  - 🟢 OPERANDO (todo OK)
  - 🟡 ABIERTO - [razón de espera]
  - 🔴 CERRADO - [razón de cierre]
  
- ✅ Tooltip con metadata (hover sobre badge):
  ```
  Plan ID: 20260126_104523
  Última gen: 2026-01-26T10:45:23
  ```

- ✅ API `/api/data` incluye `market_status`:
  ```json
  {
    "is_open": true,
    "reason": "Mercado abierto hasta 04:00 PM",
    "is_early_close": false,
    "trading_allowed": true,
    "trading_reason": "Trading permitido",
    "can_regenerate": false,
    "regen_reason": "Cooldown activo (espera 3 min)",
    "current_time": "10:45 AM ET",
    "day": "Sunday",
    "last_generation": "2026-01-26T10:45:23",
    "plan_id": "20260126_104523"
  }
  ```

---

## 📊 RESUMEN DE CONSTANTES CONFIGURABLES

```python
# Calendario y horarios
AVOID_FIRST_MINUTES = 5       # Evitar primeros 5 min post-apertura
AVOID_LAST_MINUTES = 10       # Evitar últimos 10 min pre-cierre

# Regeneración
COOLDOWN_MINUTES = 5          # Espera mínima entre generaciones

# Datos
MAX_DATA_AGE_MINUTES = 15     # Máximo age de precios para considerar frescos

# Accuracy (pendiente implementar regla de pause)
MIN_ACCURACY_THRESHOLD = 0.52 # 52% mínimo para operar (futuro)
```

---

## 🔄 FLUJO COMPLETO DE REGENERACIÓN

```
1. Todas las posiciones se cierran
   ↓
2. ¿Lock file existe?
   NO → Continuar | SÍ → ⏸️ Esperar
   ↓
3. ¿Pasaron 5+ minutos desde última gen?
   SÍ → Continuar | NO → ⏸️ "Cooldown activo"
   ↓
4. ¿Mercado abierto? (NYSE calendar)
   SÍ → Continuar | NO → 🔴 "Mercado cerrado"
   ↓
5. ¿Trading permitido? (evita primeros/últimos min)
   SÍ → Continuar | NO → 🟡 "Evitando primeros/últimos min"
   ↓
6. ¿Datos frescos? (<15 min age)
   SÍ → Continuar | NO → ⚠️ "Datos obsoletos"
   ↓
7. ✅ GENERAR PLAN
   - Crear lock file
   - Ejecutar generate_weekly_plans.py
   - Actualizar estado (timestamp, plan_id, reason)
   - Eliminar lock file
   ↓
8. Cargar nuevas posiciones desde plan_standard_YYYY-MM-DD.csv
```

---

## 🚀 PENDIENTES (Opcional - Media Prioridad)

### 8. Regla de "No Operar si No Hay Edge"
**Objetivo:** Pausar trading si accuracy reciente < 52%

**Implementación sugerida:**
- Calcular win rate de últimos N trades
- Si < `MIN_ACCURACY_THRESHOLD` → mostrar "PAUSE" en dashboard
- No generar nuevas posiciones aunque mercado esté abierto

---

## 📁 ARCHIVOS MODIFICADOS

1. `dashboard_unified.py` - Implementación completa
2. `clean_history_duplicates.py` - Script de limpieza
3. `val/system_state.json` - Estado persistente (nuevo)
4. `val/generation.lock` - Lock file temporal (nuevo)
5. `val/trade_history_closed.csv` - Ahora incluye columna `trade_id`

---

## 🧪 VALIDACIÓN

### Probar escenarios:
1. ✅ Regeneración durante cooldown → debe esperar
2. ✅ Regeneración fuera de horario → debe esperar
3. ✅ Regeneración en primeros 5 min → debe esperar
4. ✅ Regeneración en últimos 10 min → debe esperar
5. ✅ Cerrar 2 posiciones idénticas → solo 1 en historial
6. ✅ Dashboard muestra estado correcto en badge
7. ✅ Tooltip del badge muestra plan_id y timestamp

---

## 📞 SOPORTE

- **Lock file activo permanente?** → Eliminar manualmente `val/generation.lock`
- **Estado corrupto?** → Eliminar `val/system_state.json`
- **Historial con duplicados?** → Ejecutar `python clean_history_duplicates.py`
- **Cooldown muy largo?** → Ajustar `COOLDOWN_MINUTES` en dashboard_unified.py

---

## 🎯 BENEFICIOS

✅ **Robustez:** No opera en feriados, early closes, ni horarios de alta volatilidad  
✅ **Performance:** No regenera planes innecesariamente (cooldown + lock)  
✅ **Integridad:** Sin duplicados, estado persistente, escritura atómica  
✅ **Transparencia:** Usuario ve razones exactas de cada decisión  
✅ **Auditoría:** Cada plan tiene ID + timestamp + reason  
✅ **Escalabilidad:** Listo para producción con validaciones completas
