# QUICK START: Swing + Fase 2 (2 minutos)

## Lo que implementamos

**3 clases en `dashboard_unified_temp.py`:**

1. **CapitalManager** (~100 líneas)
   - Gestiona buckets Swing (70%) e Intraday (30%)
   - Rechaza trades sin capital
   - Rechaza duplicados y exceso de posiciones

2. **RiskManager** (~88 líneas)
   - Kill-switches automáticos
   - Daily stop: -3% del bucket intraday
   - Weekly stop: -6% del bucket intraday
   - Drawdown gate: 10% del capital total

3. **intraday_gates_pass()** (~84 líneas)
   - 4 filtros de calidad para Intraday
   - Gate 1: Contexto (macro)
   - Gate 2: Multi-TF (alineación)
   - Gate 3: Signal strength (min 50%)
   - Gate 4: Risk/Reward (min 1.5:1)

## Tests incluidos

```bash
.\.venv\Scripts\python test_capital_risk.py     # 11 tests ✓
.\.venv\Scripts\python example_integration.py    # 5 escenarios ✓
```

## Cómo usar en 3 líneas

```python
from dashboard_unified_temp import CAPITAL_MANAGER, RISK_MANAGER, intraday_gates_pass

# Validar signal
if CAPITAL_MANAGER.allows(signal) and RISK_MANAGER.is_intraday_enabled():
    if intraday_gates_pass(signal, market_data): execute_trade(signal)
```

## Parámetros clave (editables)

**En línea ~311 de dashboard_unified_temp.py:**
```python
CapitalManager(
    total_capital=2000,      # Cambiar a tu capital
    swing_pct=0.70,          # 70% Swing / 30% Intraday
    intraday_pct=0.30
)
```

**Límites:**
- Max 4 posiciones abiertas total
- Max 3 en Swing
- Max 2 en Intraday

## Logging esperado

```
[CAPITAL] Swing opened: AAPL x3
[INTRADAY] All gates passed for TSLA: strength=75%, RR=2.00:1
[RISK] Daily stop hit: Intraday disabled (loss $-23.00)
```

## Próximos pasos

1. **Leer** `SWING_FASE2_SUMMARY.md` (5 min)
2. **Revisar** `SWING_FASE2_GUIDE.md` (10 min)
3. **Seguir** `CHECKLIST_IMPLEMENTACION.md` (~1 hora de integración)
4. **Validar** 8-12 semanas con métricas separadas Swing vs Intraday

---

**Estado**: LISTO PARA PRODUCCIÓN (tests 11/11 passing, documentación completa)
