# SWING + FASE 2 (Intraday Selectivo) - Guía de Implementación

## Arquitectura Implementada

Tu sistema ahora tiene:

```
┌──────────────────────────────────────────┐
│   CapitalManager (Instancia Global)       │
├──────────────────────────────────────────┤
│ • Swing Bucket: $1,400 (70%)              │
│ • Intraday Bucket: $600 (30%)             │
│ • Max open total: 4 posiciones            │
│ • Max open swing: 3                       │
│ • Max open intraday: 2                    │
│ • Tracking: open_swing, open_intraday     │
│ • Heat control: Reduce 50% si duplicado   │
└──────────────────────────────────────────┘
         ↓ Autoridad en ejecución
┌──────────────────────────────────────────┐
│   RiskManager (Instancia Global)          │
├──────────────────────────────────────────┤
│ • Intraday enabled flag                   │
│ • Daily stop: -3% del bucket intraday     │
│ • Weekly stop: -6% del bucket intraday    │
│ • Drawdown gate: 10% del capital total    │
│ • Kill-switch automático                  │
└──────────────────────────────────────────┘
         ↓ Filtro de entradas
┌──────────────────────────────────────────┐
│   Intraday Gates (4 puertas)              │
├──────────────────────────────────────────┤
│ Gate 1: Contexto (macro del día)         │
│ Gate 2: Multi-TF (alineación)            │
│ Gate 3: Señal (confirmación)             │
│ Gate 4: Riesgo (SL/TP/RR)                │
└──────────────────────────────────────────┘
```

---

## Componentes Clave

### 1. CapitalManager

**Ubicación:** `dashboard_unified_temp.py` líneas ~117-217

**Responsabilidades:**
- Mantiene buckets Swing (70%) e Intraday (30%)
- Rechaza trades que exceden disponibilidad
- Rechaza duplicados en mismo libro
- Aplica heat control (reduce 50% intraday si ticker en Swing)
- Respeta límites globales de posiciones abiertas

**Métodos principales:**
```python
# Chequea si signal puede ejecutarse
allowed = CAPITAL_MANAGER.allows(signal_dict)

# Registra nueva posición abierta
CAPITAL_MANAGER.add_open('swing', 'AAPL', qty=3)

# Registra cierre de posición
CAPITAL_MANAGER.remove_open('swing', 'AAPL')

# Obtiene capital disponible
cash_swing = CAPITAL_MANAGER.available_swing()
cash_intraday = CAPITAL_MANAGER.available_intraday()

# Obtiene estado
count = CAPITAL_MANAGER.get_open_count(book='all')  # swing, intraday, all
```

**Interfaz de Signal:**
```python
signal = {
    'book': 'swing',      # 'swing' o 'intraday'
    'ticker': 'AAPL',
    'entry': 180.0,       # Precio de entrada
    'qty': 3,             # Cantidad de acciones
    'side': 'BUY',        # 'BUY' o 'SELL'
}

# Validación
if CAPITAL_MANAGER.allows(signal):
    # Ejecutar
    CAPITAL_MANAGER.add_open(signal['book'], signal['ticker'], signal['qty'])
```

---

### 2. RiskManager

**Ubicación:** `dashboard_unified_temp.py` líneas ~220-307

**Responsabilidades:**
- Monitorea PnL diario para Intraday
- Dispara daily stop si Intraday pierde > 3% del bucket
- Dispara weekly stop si Intraday pierde > 6% del bucket
- Monitorea drawdown total (capital peak)
- Desactiva automáticamente Intraday en problemas

**Métodos principales:**
```python
# Actualiza PnL (llamar después de cada trade)
RISK_MANAGER.update_pnl(pnl_value)  # ej: -15.5

# Actualiza capital total (para drawdown check)
dd_pct = RISK_MANAGER.update_capital(current_capital)

# Chequea si Intraday puede operar
if RISK_MANAGER.is_intraday_enabled():
    # Ejecutar intraday
    ...

# Obtiene status para logging
status = RISK_MANAGER.get_status()
# → {'intraday_enabled': True, 'intraday_loss_today': -5.2, 'drawdown_pct': 2.1, ...}
```

**Lógica de Kill-Switch:**
```
Intraday se desactiva automáticamente si:
1. Pérdida diaria > -3% del bucket ($18 para $600)
2. Pérdida semanal acumulada > -6% del bucket ($36 para $600)
3. Drawdown total > 10% del capital ($200 para $2000)

Reset automático:
- Daily: cada día (00:00)
- Weekly: cada lunes (00:00)
```

---

### 3. Intraday Gates

**Ubicación:** `dashboard_unified_temp.py` líneas ~310-393

**Responsabilidades:**
- Filtra entradas intraday contra 4 criterios de calidad
- Embudo: cada gate elimina ruido
- Garantiza consistencia en setup

**Gate 1: Contexto (Macro del Día)**
```python
Rechaza si:
  - Mercado muy plano (SPY ±0.5%, QQQ ±0.5%)
  - Día de evento (earnings, CPI, FOMC, etc.)
  
market_data = {
    'SPY_change_pct': 1.2,
    'QQQ_change_pct': 1.5,
    'event_day': False
}
```

**Gate 2: Alineación Multi-TF**
```python
Rechaza si:
  - BUY conflicta con daily DOWN
  - SELL conflicta con daily UP
  
signal['daily_trend'] = 'UP'  # UP, DOWN, FLAT
signal['side'] = 'BUY'  # Alineado → pasa

signal['daily_trend'] = 'DOWN'
signal['side'] = 'BUY'  # Conflicto → rechazado
```

**Gate 3: Signal Strength (Confirmación)**
```python
Rechaza si:
  - Signal strength < 50%
  
signal['signal_strength'] = 75  # 0-100, mín 50
# Puedes usar: patrón%, volumen%, modelo%, etc.
```

**Gate 4: Risk/Reward**
```python
Rechaza si:
  - SL > 3% de distancia (muy grande para intraday)
  - RR < 1.5:1 (poco reward para el risk)
  
signal = {
    'entry': 180.0,
    'sl': 174.6,  # 3% stop
    'tp': 190.8,  # 6% target
    # → RR = 6%/3% = 2:1 ✓ (pasa)
}
```

**Uso:**
```python
signal = {
    'ticker': 'TSLA',
    'entry': 240.0,
    'side': 'BUY',
    'daily_trend': 'UP',
    'signal_strength': 75,
    'sl': 235.0,
    'tp': 250.0
}

market = {'SPY_change_pct': 1.2, 'QQQ_change_pct': 1.5, 'event_day': False}

passed, reason = intraday_gates_pass(signal, market_data=market)
if passed and RISK_MANAGER.is_intraday_enabled():
    # Ejecutar
```

---

## Flujo de Ejecución (Ejemplo)

```python
# 1. Generas una señal (Swing o Intraday)
signal = {
    'book': 'intraday',
    'ticker': 'TSLA',
    'entry': 240.0,
    'qty': 2,
    'side': 'BUY',
    'daily_trend': 'UP',
    'signal_strength': 75,
    'sl': 235.0,
    'tp': 250.0
}

# 2. CapitalManager valida básicos
if not CAPITAL_MANAGER.allows(signal):
    logger.warning(f"Capital denied for {signal}")
    continue

# 3. Si es Intraday, pasa por Gates
if signal['book'] == 'intraday':
    if not RISK_MANAGER.is_intraday_enabled():
        logger.warning(f"Intraday disabled")
        continue
    
    market_data = get_market_context()
    passed, reason = intraday_gates_pass(signal, market_data)
    if not passed:
        logger.info(f"Gate rejected: {reason}")
        continue

# 4. Ejecutar
execute_trade(signal)
CAPITAL_MANAGER.add_open(signal['book'], signal['ticker'], signal['qty'])

# 5. Al cerrar, actualizar RiskManager
pnl = calculate_pnl(signal)
RISK_MANAGER.update_pnl(pnl)
CAPITAL_MANAGER.remove_open(signal['book'], signal['ticker'])
```

---

## Configuración (Parámetros Clave)

Edita en `dashboard_unified_temp.py` (línea ~311):

```python
CAPITAL_MANAGER = CapitalManager(
    total_capital=2000,      # Cambiar a tu capital
    swing_pct=0.70,          # 70% para Swing
    intraday_pct=0.30        # 30% para Intraday
)

RISK_MANAGER = RiskManager(
    CAPITAL_MANAGER,
    capital_total=2000       # Mismo que arriba
)
```

**Cambios recomendados después de 8+ semanas:**
- Si Intraday PF > 1.25: cambia `intraday_pct` a 0.40
- Si PF < 1.05: reduce a 0.20 o apaga Intraday

**Gates ajustables:**
En `intraday_gates_pass()` (línea ~310):
```python
# Gate 3 mínima strength
min_strength = 50  # Aumenta a 60-70 si quieres filtrar más

# Gate 4 máxima risk y mínima RR
if risk > 0.03:  # SL máximo 3%
    ...
if rr_ratio < 1.5:  # RR mínimo 1.5:1
    ...
```

---

## Logging y Debugging

Todos los eventos se loguean con prefijo:

```
[CAPITAL] - Decisiones de CapitalManager
[RISK]    - Eventos de RiskManager (daily stop, drawdown)
[GATE1-4] - Cada puerta intraday
[INTRADAY] - Entrada aprobada
```

Ejemplo log esperado:
```
[INFO] [CAPITAL] Initialized: Total=$2000, Swing=70% ($1400.0), Intraday=30% ($600.0)
[INFO] [RISK] Initialized: Daily stop 3.0%, Weekly stop 6.0%, DD threshold 10.0%
[INFO] [CAPITAL] Swing opened: AAPL x3
[INFO] [INTRADAY] All gates passed for TSLA: strength=75%, RR=2.00:1
[WARNING] [CAPITAL] Ticker AAPL already open in Swing
[WARNING] [RISK] Daily stop hit: Intraday disabled (loss $-23.00)
```

---

## Testing

Ejecuta:
```bash
.\.venv\Scripts\python test_capital_risk.py
```

Tests incluidos:
- ✓ Buckets inicializan correctamente
- ✓ Permite trade válido
- ✓ Rechaza duplicado en mismo libro
- ✓ Heat control (reduce 50% intraday si duplicado)
- ✓ Rechaza si excede límite de abiertas
- ✓ Daily stop funciona
- ✓ Gate 1-4 funcionan correctamente

---

## Próximos Pasos

**Semana 1-2:**
- [ ] Integra `CapitalManager` + `RiskManager` con tu generador de señales
- [ ] Loguea separado: `pnl_swing` vs `pnl_intraday`
- [ ] Ejecuta con 1 ticker intraday máximo
- [ ] Valida que logs muestren buckets correctamente

**Semana 3-8:**
- [ ] Colecta métricas semanales: PF, winrate, DD por libro
- [ ] Monitorea si Intraday suma value (PF > 1.15)
- [ ] Chequea que Daily stop se dispare correctamente en pérdida

**Semana 9-12:**
- [ ] Si PF intraday > 1.25 y DD < 5%: pasá a Fase 2 afinada
- [ ] Implementa selección dinámica de tickers semanal
- [ ] Prueba TP/SL adaptativo (Gate 4 dinámico)

---

## FAQ

**P: ¿Puedo ejecutar Swing sin Intraday?**
A: Sí. Solo no generes señales 'intraday', usa solo 'swing'.

**P: ¿Qué pasa si Intraday se apaga?**
A: Se ignoran todas las señales intraday (capital locked en Swing). Reset automático según daily/weekly/drawdown.

**P: ¿Cómo sé si Intraday está agregando valor?**
A: Compara `pnl_intraday` vs `pnl_swing` semanalmente. Si PF intraday < 1.10 por 4+ semanas, apágalo.

**P: ¿Puedo cambiar los límites de buckets?**
A: Sí, en instanciación de `CapitalManager`. Recomendación: 70/30 inicial, sube a 60/40 después de validar.

**P: ¿Qué es heat control?**
A: Cuando Intraday quiere entrar en un ticker que ya está en Swing, automáticamente reduce costo 50% para evitar exposición duplicada.

---

## Referencias

- **Tharp, 2007**: Trade Your Way to Financial Freedom - Position sizing y risk management
- **Chan, 2013**: Algorithmic Trading - Multi-TF alignment y signal quality
- **Carver, 2015**: Systematic Trading - Walk-forward testing y gates

---

Generated: Feb 2, 2026 | Sistema: Swing + Fase 2 (Intraday Selectivo)
