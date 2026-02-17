# CHECKLIST DE IMPLEMENTACIÓN: Swing + Fase 2 en tu Dashboard

## Pre-Requisitos

- [ ] Python 3.8+
- [ ] Flask (existente)
- [ ] Pandas (existente)
- [ ] Logger configurado (existente)

## Paso 1: Verificar Archivos (2 min)

```powershell
# Verifica que existan
Get-Item dashboard_unified_temp.py
Get-Item test_capital_risk.py
Get-Item example_integration.py
Get-Item SWING_FASE2_GUIDE.md
Get-Item SWING_FASE2_SUMMARY.md
```

- [ ] dashboard_unified_temp.py (3,326 líneas)
- [ ] test_capital_risk.py (247 líneas)
- [ ] example_integration.py (300 líneas)
- [ ] SWING_FASE2_GUIDE.md (350+ líneas)
- [ ] SWING_FASE2_SUMMARY.md (300+ líneas)

## Paso 2: Validar Sintaxis (1 min)

```powershell
.\.venv\Scripts\python -m py_compile dashboard_unified_temp.py
if ($?) { Write-Host "Sintaxis OK" }
```

- [ ] Sintaxis Python válida

## Paso 3: Ejecutar Tests (2 min)

```powershell
.\.venv\Scripts\python test_capital_risk.py 2>&1 | Where-Object {$_ -match 'SUMMARY|PASS|FAIL'}
```

Debe mostrar:
```
[TEST 1-11] Todos pasan
SUMMARY: Todos los tests pasaron!
```

- [ ] 11/11 tests passing
- [ ] CapitalManager funciona
- [ ] RiskManager funciona
- [ ] Intraday Gates funciona

## Paso 4: Ver Ejemplo Integración (2 min)

```powershell
.\.venv\Scripts\python example_integration.py 2>&1 | Where-Object {$_ -match 'SCENARIO|Result:|PnL'}
```

Debe mostrar:
```
[SCENARIO 1-5] Resultados
REPORTE DE PnL POR LIBRO
Swing PnL: $15.00
Intraday PnL: $-4.00
```

- [ ] 5/5 escenarios ejecutados
- [ ] Swing trades ejecutados
- [ ] Intraday gates rechazaron correctamente
- [ ] PnL calculado correctamente

## Paso 5: Entender Arquitectura (5 min)

Lee `SWING_FASE2_SUMMARY.md`:
- [ ] Entiendo qué es CapitalManager
- [ ] Entiendo qué es RiskManager
- [ ] Entiendo los 4 Intraday Gates
- [ ] Entiendo flujo de ejecución

## Paso 6: Revisar Guía de Uso (5 min)

Lee `SWING_FASE2_GUIDE.md`:
- [ ] Sé cómo usar CapitalManager.allows()
- [ ] Sé cómo usar RiskManager.is_intraday_enabled()
- [ ] Sé cómo usar intraday_gates_pass()
- [ ] Sé qué logs esperar

## Paso 7: Copiar a Production (2 min)

Cuando esté listo pasar a `dashboard_unified.py` principal:

```powershell
# 1. Respalda original
Copy-Item dashboard_unified.py dashboard_unified.backup

# 2. Identifica secciones a copiar de dashboard_unified_temp.py
#    - CapitalManager class (líneas ~117-217)
#    - RiskManager class (líneas ~220-307)
#    - intraday_gates_pass() function (líneas ~310-393)
#    - CAPITAL_MANAGER instancia global (línea ~311)
#    - RISK_MANAGER instancia global (línea ~312)

# 3. Pega en dashboard_unified.py (después del logger setup)

# 4. Valida sintaxis
.\.venv\Scripts\python -m py_compile dashboard_unified.py

# 5. Reinicia servidor
```

- [ ] Backup de original hecho
- [ ] Clases copiadas al archivo principal
- [ ] Sintaxis validada
- [ ] Servidor reinicia sin errores

## Paso 8: Integración con tu Generador de Señales (15-30 min)

En tu código que genera señales:

```python
from dashboard_unified import CAPITAL_MANAGER, RISK_MANAGER, intraday_gates_pass

# Para cada señal generada:
signal = {
    'book': 'swing',  # o 'intraday'
    'ticker': 'AAPL',
    'entry': 180.0,
    'qty': 3,
    'side': 'BUY',
    'sl': 175.0,
    'tp': 190.0,
    # Para Intraday Gates:
    'daily_trend': get_daily_trend('AAPL'),  # 'UP', 'DOWN', 'FLAT'
    'signal_strength': get_signal_strength()  # 0-100
}

# Validar
if CAPITAL_MANAGER.allows(signal):
    if signal['book'] == 'intraday':
        if RISK_MANAGER.is_intraday_enabled():
            market = get_market_context()
            passed, reason = intraday_gates_pass(signal, market)
            if not passed:
                logger.info(f"Gate rejected: {reason}")
                continue
    
    # Ejecutar
    execute_trade(signal)
    CAPITAL_MANAGER.add_open(signal['book'], signal['ticker'], signal['qty'])
    logger.info(f"Opened {signal['book']} {signal['ticker']}")

# Al cerrar trade:
pnl = calculate_pnl(...)
RISK_MANAGER.update_pnl(pnl)
CAPITAL_MANAGER.remove_open(signal['book'], signal['ticker'])
logger.info(f"Closed {signal['book']} {signal['ticker']}: PnL=${pnl:.2f}")
```

- [ ] Generador integrado con CapitalManager
- [ ] Generador integrado con RiskManager (si Intraday)
- [ ] Generador integrado con Gates (si Intraday)
- [ ] PnL se registra correctamente

## Paso 9: Logging y Monitoreo (5 min)

Verifica que los logs muestren:

```
[INFO] [CAPITAL] Initialized: Total=$2000, Swing=70% ($1400.0), Intraday=30% ($600.0)
[INFO] [RISK] Initialized: Daily stop 3.0%, Weekly stop 6.0%, DD threshold 10.0%
[INFO] [CAPITAL] Swing opened: AAPL x3
[INFO] [INTRADAY] All gates passed for TSLA: strength=75%, RR=2.00:1
[WARNING] [RISK] Daily stop hit: Intraday disabled
```

- [ ] Logs muestran inicialización
- [ ] Logs muestran trades abiertos/cerrados
- [ ] Logs muestran gates correctamente
- [ ] Logs muestran kill-switches si aplica

## Paso 10: Métrica Separada por Libro (Importante!)

Asegúrate que calcules PnL separado:

```python
# En tu reporte semanal:
swing_trades = [t for t in history if t['book'] == 'swing']
intraday_trades = [t for t in history if t['book'] == 'intraday']

swing_pnl = sum(t['pnl'] for t in swing_trades)
intraday_pnl = sum(t['pnl'] for t in intraday_trades)
total_pnl = swing_pnl + intraday_pnl

# Calcula métricas separadas:
swing_pf = calculate_pf(swing_trades)
intraday_pf = calculate_pf(intraday_trades)

print(f"Swing: PnL=${swing_pnl:.2f}, PF={swing_pf:.2f}, trades={len(swing_trades)}")
print(f"Intraday: PnL=${intraday_pnl:.2f}, PF={intraday_pf:.2f}, trades={len(intraday_trades)}")
print(f"Total: PnL=${total_pnl:.2f}")
```

- [ ] Swing PnL calculado separado
- [ ] Intraday PnL calculado separado
- [ ] Métricas (PF, winrate) separadas
- [ ] Reporte semanal muestra ambos libros

## Paso 11: Validación Inicial (Semana 1)

Durante la primera semana:

- [ ] Sistema ejecuta Swing sin problemas
- [ ] Sistema ejecuta Intraday (si lo activas) sin problemas
- [ ] Logs son claros y completos
- [ ] Kill-switches funcionan (si necesario testear)
- [ ] PnL por libro es preciso

## Paso 12: Seguimiento (Semanas 2-12)

### Semanas 2-4:
- [ ] Colecta datos de Swing PnL/PF/trades
- [ ] Colecta datos de Intraday PnL/PF/trades
- [ ] Valida que Intraday Gates rechacen ruido
- [ ] Chequea que heat control funcione

### Semanas 5-8:
- [ ] Análisis semanal: ¿Intraday suma value?
- [ ] Si Intraday PF < 1.10: considera apagar
- [ ] Si Intraday PF > 1.15: sigue el plan

### Semanas 9-12:
- [ ] Si validó (PF > 1.25, DD < 5%): pasá a "Fase 2 afinada"
- [ ] Implementa selección dinámica semanal
- [ ] Prueba TP/SL adaptativo

---

## Troubleshooting Rápido

### "CapitalManager says no capital"
→ Verifica que no hayas superado el bucket disponible
→ Chequea `CAPITAL_MANAGER.available_swing()` / `.available_intraday()`

### "Intraday está disabled"
→ Ejecuta `RISK_MANAGER.get_status()` para ver por qué
→ Puede ser: daily stop, weekly stop, o drawdown

### "Gates rechaza todas mis señales intraday"
→ Chequea `signal_strength` (mín 50%, Gate 3)
→ Chequea SL (máx 3%, Gate 4)
→ Chequea RR (mín 1.5:1, Gate 4)
→ Chequea `daily_trend` alineación (Gate 2)

### "Logs no muestran actividad"
→ Verifica que estés llamando a `add_open()` y `remove_open()`
→ Verifica que estés llamando a `update_pnl()`
→ Revisa `reports/logs/dashboard.log`

---

## Timeline Estimado

| Paso | Duración | Cumplido |
|---|---|---|
| 1-4: Setup y tests | 7 min | ☐ |
| 5-7: Documentación | 12 min | ☐ |
| 8: Integración | 30 min | ☐ |
| 9-10: Logging y métricas | 10 min | ☐ |
| **TOTAL IMPLEMENTACIÓN** | **~1 hora** | ☐ |
| 11-12: Validación | 12 semanas | ☐ |

---

## Final Checklist

**Antes de ir a producción:**
- [ ] Todos los tests pasan
- [ ] Logs muestran flow correcto
- [ ] PnL por libro es preciso
- [ ] Kill-switches funcionan
- [ ] Documentación revisada
- [ ] Equipo alineado en parámetros
- [ ] Backup del código original hecho

**Go Live:**
- [ ] Cambiar `dashboard_unified_temp.py` por `dashboard_unified.py`
- [ ] Monitorear logs primera hora
- [ ] Validar que Swing trades ejecuten
- [ ] Validar que Intraday Gates funcionen

**Semanas 2-12:**
- [ ] Reporte semanal PnL/PF por libro
- [ ] Decisión: ¿Continuar con Fase 2 o apagar?

---

**Creado**: Feb 2, 2026  
**Estado**: LISTO PARA IMPLEMENTACIÓN

