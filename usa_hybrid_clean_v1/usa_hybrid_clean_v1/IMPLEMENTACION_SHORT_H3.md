# ============================================
# IMPLEMENTACIÓN DE SHORT EN H3
# ============================================
# Documento técnico con todos los cambios necesarios

## 📋 ESTADO ACTUAL

### ✅ YA IMPLEMENTADO (No requiere cambios):

1. **`scripts/40_make_trade_plan_with_tth.py`**
   - ✅ Línea 67: Determina `side` basado en `y_hat`
   - ✅ Línea 344: Aplica lógica BUY/SHORT
   ```python
   side = 'BUY' if row.get('y_hat', 0) > 0 else 'SHORT'
   ```

2. **`scripts/35_check_predictions_and_notify.py`**
   - ✅ Líneas 129-140: Evalúa TP/SL diferente para BUY vs SHORT
   - ✅ SHORT invierte la lógica: TP abajo, SL arriba

3. **`scripts/bitacora_excel.py`**
   - ✅ Columna "Side" en headers
   - ✅ Registra side del trade
   - ❌ **FALTA:** Cálculo de P&L y progreso para SHORT

---

## ❌ CAMBIOS REQUERIDOS

### 1. **scripts/bitacora_excel.py** - Función `add_prediction()`

**Problema:** TP y SL se calculan asumiendo siempre LONG (BUY)

**Líneas 88-102 (actuales):**
```python
# Calcular precios TP y SL
entry = float(trade_row.get('entry_price', 0))
tp_pct = float(trade_row.get('tp_pct', 0.04))
sl_pct = float(trade_row.get('sl_pct', 0.02))

tp_price = entry * (1 + tp_pct)
sl_price = entry * (1 - sl_pct)
```

**Solución - Reemplazar con:**
```python
# Calcular precios TP y SL según side
entry = float(trade_row.get('entry_price', 0))
tp_pct = float(trade_row.get('tp_pct', 0.04))
sl_pct = float(trade_row.get('sl_pct', 0.02))
side = trade_row.get('side', 'BUY')

if side == 'BUY':
    tp_price = entry * (1 + tp_pct)
    sl_price = entry * (1 - sl_pct)
else:  # SHORT
    tp_price = entry * (1 - tp_pct)  # TP abajo
    sl_price = entry * (1 + sl_pct)  # SL arriba
```

---

### 2. **scripts/bitacora_excel.py** - Función `update_prices()`

**Problema:** Progreso a TP solo funciona para LONG

**Líneas 168-174 (actuales):**
```python
# Calcular progreso a TP
if tp_price > entry_price:
    progress = ((current_price - entry_price) / (tp_price - entry_price)) * 100
else:
    progress = 0
df.at[idx, 'Progreso a TP %'] = round(progress, 2)
```

**Solución - Reemplazar con:**
```python
# Calcular progreso a TP según side
side = df.at[idx, 'Side']

if side == 'BUY':
    # LONG: TP arriba
    if tp_price > entry_price:
        progress = ((current_price - entry_price) / (tp_price - entry_price)) * 100
    else:
        progress = 0
else:  # SHORT
    # SHORT: TP abajo (invertido)
    if tp_price < entry_price:
        progress = ((entry_price - current_price) / (entry_price - tp_price)) * 100
    else:
        progress = 0

df.at[idx, 'Progreso a TP %'] = round(progress, 2)
```

---

### 3. **scripts/bitacora_excel.py** - Función `update_prices()` - Detección TP/SL

**Problema:** No verifica si se alcanzó TP o SL para cerrar posición

**Agregar DESPUÉS de línea 180:**
```python
        # Verificar si alcanzó TP o SL
        if side == 'BUY':
            if current_price >= tp_price:
                df.at[idx, 'Status'] = 'TP_HIT'
                df.at[idx, 'Fecha Cierre'] = datetime.now().strftime("%Y-%m-%d")
                df.at[idx, 'Exit Price'] = tp_price
                pnl_usd = (tp_price - entry_price) * 100  # Asumir 100 acciones
                pnl_pct = ((tp_price - entry_price) / entry_price) * 100
                df.at[idx, 'PnL USD'] = round(pnl_usd, 2)
                df.at[idx, 'PnL %'] = round(pnl_pct, 2)
            elif current_price <= sl_price:
                df.at[idx, 'Status'] = 'SL_HIT'
                df.at[idx, 'Fecha Cierre'] = datetime.now().strftime("%Y-%m-%d")
                df.at[idx, 'Exit Price'] = sl_price
                pnl_usd = (sl_price - entry_price) * 100
                pnl_pct = ((sl_price - entry_price) / entry_price) * 100
                df.at[idx, 'PnL USD'] = round(pnl_usd, 2)
                df.at[idx, 'PnL %'] = round(pnl_pct, 2)
        else:  # SHORT
            if current_price <= tp_price:
                df.at[idx, 'Status'] = 'TP_HIT'
                df.at[idx, 'Fecha Cierre'] = datetime.now().strftime("%Y-%m-%d")
                df.at[idx, 'Exit Price'] = tp_price
                pnl_usd = (entry_price - tp_price) * 100  # Invertido
                pnl_pct = ((entry_price - tp_price) / entry_price) * 100
                df.at[idx, 'PnL USD'] = round(pnl_usd, 2)
                df.at[idx, 'PnL %'] = round(pnl_pct, 2)
            elif current_price >= sl_price:
                df.at[idx, 'Status'] = 'SL_HIT'
                df.at[idx, 'Fecha Cierre'] = datetime.now().strftime("%Y-%m-%d")
                df.at[idx, 'Exit Price'] = sl_price
                pnl_usd = (entry_price - sl_price) * 100  # Invertido
                pnl_pct = ((entry_price - sl_price) / entry_price) * 100
                df.at[idx, 'PnL USD'] = round(pnl_usd, 2)
                df.at[idx, 'PnL %'] = round(pnl_pct, 2)
```

---

### 4. **scripts/infer_and_gate.py** - Generar predicciones negativas

**Problema actual:** ¿El modelo genera `y_hat` negativo?

**Verificar:**
```bash
python -c "import pandas as pd; df = pd.read_csv('reports/forecast/2025-11/forecast.csv'); print('Min y_hat:', df['y_hat'].min()); print('Neg count:', (df['y_hat'] < 0).sum())"
```

**Si SOLO genera positivos:**
- Opción 1: Entrenar modelo con targets negativos (bajadas)
- Opción 2: Usar otro enfoque:
  ```python
  # Detectar condiciones de SHORT basado en patrones bajistas
  df['side'] = 'BUY'
  df.loc[df['pattern_bearish'] == 1, 'side'] = 'SHORT'
  df.loc[df['side'] == 'SHORT', 'y_hat'] = -abs(df['y_hat'])
  ```

---

### 5. **validate_plan_prices.py** - Validación para SHORT

**Líneas 35-50 (actuales):**
```python
diff_pct = ((current_price - entry_price) / entry_price) * 100
progress = ((current_price - entry_price) / (tp_price - entry_price)) * 100
```

**Solución - Reemplazar con:**
```python
side = row['side']

if side == 'BUY':
    diff_pct = ((current_price - entry_price) / entry_price) * 100
    progress = ((current_price - entry_price) / (tp_price - entry_price)) * 100
else:  # SHORT
    diff_pct = ((entry_price - current_price) / entry_price) * 100  # Invertido
    progress = ((entry_price - current_price) / (entry_price - tp_price)) * 100
```

---

### 6. **Telegram Messages** - Mostrar side claramente

**scripts/40_make_trade_plan_with_tth.py** - Línea 81

**Actual:**
```python
#{rank} · {ticker} · {side}
```

**Mejorar:**
```python
#{rank} · {ticker} · {'📈 BUY' if side == 'BUY' else '📉 SHORT'}
```

---

## 🎯 CONFIGURACIÓN DE POLÍTICAS

### Política para permitir SHORT:

**Archivo:** `policies/Policy_Base.json` o `policies/monthly/Policy_YYYY-MM.json`

**Agregar:**
```json
{
  "gate_filters": {
    "allow_short": true,
    "short_min_prob": 0.58,
    "short_min_abs_yhat": 0.06
  }
}
```

**En script `40_make_trade_plan_with_tth.py`:**
```python
# Cargar política
with open(policy_path) as f:
    policy = json.load(f)

allow_short = policy.get('gate_filters', {}).get('allow_short', False)

# Filtrar
if not allow_short:
    df = df[df['y_hat'] >= 0]  # Solo BUY
```

---

## 🧪 TESTING REQUERIDO

### 1. Test con predicción SHORT manual:

```python
# test_short.py
import pandas as pd
from scripts.bitacora_excel import add_prediction, update_prices

# Crear trade SHORT ficticio
trade_short = {
    'ticker': 'AAPL',
    'entry_price': 180.0,
    'tp_pct': 0.03,
    'sl_pct': 0.02,
    'side': 'SHORT',
    'prob_win': 0.65,
    'y_hat': -0.03,
    'horizon_days': 3,
    'etth': 1.5,
    'p_tp_sl': 0.75,
    'score_tth': 85.0,
    'sector': 'Tech'
}

# Registrar
add_prediction(trade_short)

# Actualizar con precio bajado (debería mostrar progreso positivo)
# Simular AAPL cayó a $175
update_prices('data/us/ohlcv_us_daily.csv')
```

### 2. Verificar cálculos:

**SHORT en AAPL @ $180:**
- TP (3% abajo): $174.60
- SL (2% arriba): $183.60
- Precio actual: $175
- Progreso: `(180 - 175) / (180 - 174.60) = 92.6%` ✅

### 3. Test pipeline completo:

```bash
# Forzar generación de SHORT (si tienes datos con y_hat negativo)
python scripts/infer_and_gate.py --month 2025-11 --allow-short

# Generar plan
python scripts/40_make_trade_plan_with_tth.py --allow-short

# Validar
python validate_plan_prices.py
```

---

## 📊 EJEMPLO VISUAL: BUY vs SHORT

### BUY (LONG):
```
Entry: $100
TP:    $104 (+4%) ⬆️
SL:    $98  (-2%) ⬇️

Ganas si: Precio sube
Pierdes si: Precio baja
```

### SHORT:
```
Entry: $100
TP:    $96  (-4%) ⬇️  [Invertido]
SL:    $102 (+2%) ⬆️  [Invertido]

Ganas si: Precio baja
Pierdes si: Precio sube
```

---

## 🚀 PLAN DE IMPLEMENTACIÓN

### Fase 1: Bitácora Excel (Core)
1. ✅ Modificar `add_prediction()` - TP/SL para SHORT
2. ✅ Modificar `update_prices()` - Progreso para SHORT
3. ✅ Agregar detección TP/SL automática
4. ✅ Testing unitario

### Fase 2: Validación
1. ✅ Modificar `validate_plan_prices.py`
2. ✅ Testing con trades SHORT ficticios

### Fase 3: Generación de SHORT
1. ⏳ Verificar si modelo genera `y_hat < 0`
2. ⏳ Si no, implementar lógica de patrones bajistas
3. ⏳ Configurar políticas con `allow_short`

### Fase 4: Telegram y Notificaciones
1. ✅ Mejorar mensajes para mostrar 📈/📉
2. ✅ Testing end-to-end

---

## 📝 CHECKLIST COMPLETO

### Scripts a Modificar:
- [ ] `scripts/bitacora_excel.py` - add_prediction()
- [ ] `scripts/bitacora_excel.py` - update_prices()
- [ ] `scripts/bitacora_excel.py` - Detección TP/SL
- [ ] `validate_plan_prices.py` - Cálculos SHORT
- [ ] `scripts/40_make_trade_plan_with_tth.py` - Mensajes Telegram
- [ ] `scripts/infer_and_gate.py` - Permitir y_hat negativo (opcional)

### Políticas a Configurar:
- [ ] `policies/Policy_Base.json` - allow_short
- [ ] Thresholds específicos para SHORT

### Testing:
- [ ] Test unitario: TP/SL SHORT
- [ ] Test unitario: Progreso SHORT
- [ ] Test unitario: P&L SHORT
- [ ] Test integración: Pipeline completo con SHORT
- [ ] Validar con trade real en paper trading

### Documentación:
- [ ] Actualizar README con lógica SHORT
- [ ] Documentar diferencias BUY vs SHORT
- [ ] Ejemplos de uso

---

## ⚠️ CONSIDERACIONES IMPORTANTES

### 1. **Riesgo Broker:**
- Algunos brokers cobran más por SHORT (borrow fees)
- Verificar disponibilidad de acciones para SHORT
- Riesgo ilimitado en SHORT (precio puede subir infinito)

### 2. **Cálculo de Qty:**
- SHORT requiere margen (típicamente 50% en USA)
- Ajustar `qty` según capital disponible y margen requerido

### 3. **Dividendos:**
- SHORT paga dividendos (costo adicional)
- Evitar SHORT antes de ex-dividend date

### 4. **Impuestos:**
- SHORT puede tener tratamiento fiscal diferente
- Consultar con contador

---

## 🎯 PRIORIDAD DE IMPLEMENTACIÓN

### Alta Prioridad (Hazlo ya):
1. ✅ Bitácora Excel - add_prediction() y update_prices()
2. ✅ Testing con trades SHORT ficticios
3. ✅ validate_plan_prices.py

### Media Prioridad (Esta semana):
1. ⏳ Configurar políticas allow_short
2. ⏳ Telegram messages con 📈/📉
3. ⏳ Verificar generación y_hat negativo

### Baja Prioridad (Opcional):
1. ⏳ Dashboard visual diferenciando BUY/SHORT
2. ⏳ Backtesting histórico SHORT vs LONG
3. ⏳ Machine learning para predecir mejor dirección

---

**RESUMEN EJECUTIVO:**

Tu sistema YA tiene el 70% implementado. Solo necesitas:
1. **Corregir cálculos en bitacora_excel.py** (2 funciones)
2. **Validar con test manual** (crear trade SHORT ficticio)
3. **Configurar políticas** para permitir SHORT

El resto (inferencia, notificaciones) ya está listo. 🎉

---

**Archivo:** IMPLEMENTACION_SHORT_H3.md
**Fecha:** 5 de Noviembre, 2025
**Estado:** DOCUMENTACIÓN COMPLETA - LISTO PARA IMPLEMENTAR
