# FASE 2-3 Implementation Guide
**Validación y Operación con Métricas Separadas**

---

## Arquitectura de Fase 2-3

### Componentes Implementados

#### 1. **METRICS_TRACKER** (Clase)
- **Propósito**: Rastrear métricas separadas por libro (Swing vs Intraday)
- **Ubicación**: `dashboard_unified_temp.py` línea ~315
- **Métodos principales**:
  - `log_trade()`: Registra un trade cerrado (entrada, salida, PnL)
  - `get_status()`: Retorna estado actual de ambos libros
  - `get_weekly_report()`: Genera reporte semanal con métricas
  - `_recalculate_stats()`: Actualiza PF, winrate, avg_win/loss

#### 2. **Separated Logging**
- **Prefijos de logging**:
  - `[SWING]`: Trades del libro Swing
  - `[INTRADAY]`: Trades del libro Intraday
  - `[CAPITAL]`: Advertencias de capital
  - `[RISK]`: Cambios en stop automático
  - `[PHASE3]`: Operación real (Fase 3)

#### 3. **Capital Manager & Risk Manager**
- **CapitalManager**: Gestiona buckets 70/30 y límites de posiciones
- **RiskManager**: Stop automático diario (-3%), semanal (-6%), drawdown (-10%)

---

## FASE 2: Validación (Semanas 2-3)

### Objetivo
Validar que:
- Swing PF > 1.05 (rentable)
- Intraday agregue valor (PF > 1.15)
- Risk controls funcionan automáticamente

### Endpoints de Fase 2

#### 1. **GET /api/phase2/metrics**
Retorna métricas actuales por libro.

**Response**:
```json
{
  "status": "ok",
  "timestamp": "2025-01-20T10:30:45.123456",
  "capital_manager": {
    "total": 2000,
    "swing_bucket": 1400,
    "intraday_bucket": 600,
    "open_swing": 0,
    "open_intraday": 0
  },
  "risk_manager": {
    "daily_pnl": -45.0,
    "weekly_pnl": 120.5,
    "drawdown_pct": 2.25,
    "intraday_enabled": true
  },
  "metrics": {
    "swing": {
      "trades": 12,
      "winners": 8,
      "losers": 4,
      "pnl": 450.00,
      "pf": 1.32,
      "winrate": 66.67,
      "avg_win": 75.25,
      "avg_loss": -31.50,
      "dd": 2.50
    },
    "intraday": {
      "trades": 8,
      "winners": 5,
      "losers": 3,
      "pnl": 120.00,
      "pf": 1.18,
      "winrate": 62.50,
      "avg_win": 48.50,
      "avg_loss": -42.00,
      "dd": 1.20
    },
    "total": {
      "trades": 20,
      "pnl": 570.00,
      "pf": 1.27
    }
  },
  "phase": "PHASE 2 - VALIDATION"
}
```

#### 2. **GET /api/phase2/weekly-report**
Genera reporte semanal y recomendación.

**Response**:
```json
{
  "status": "ok",
  "report": {
    "swing": {
      "trades": 12,
      "pnl": 450.00,
      "pf": 1.32,
      "winrate": 66.67,
      "best_trade": 125.00,
      "worst_trade": -60.00
    },
    "intraday": {
      "trades": 8,
      "pnl": 120.00,
      "pf": 1.18,
      "winrate": 62.50,
      "best_trade": 85.00,
      "worst_trade": -50.00
    },
    "total": {
      "trades": 20,
      "pnl": 570.00,
      "pf": 1.27,
      "week": "2025-W03"
    }
  },
  "decision": {
    "swing_pf": 1.32,
    "intraday_pf": 1.18,
    "intraday_enabled": true,
    "recommendation": "CONTINUE - Intraday adding value, keep collecting data"
  }
}
```

### Validación Semanal Checklist

**Semana 2 Check**:
- [ ] Swing PF > 1.05
- [ ] Intraday PF > 1.10 (initial)
- [ ] DD < 5%
- [ ] Capital manager respeta límites (0 overflow)
- [ ] Risk manager ejecutó stop si necesario

**Semana 3 Check**:
- [ ] Swing PF consistente (misma dirección)
- [ ] Intraday PF > 1.15 (criterio de continuación)
- [ ] DD individual < 3% cada libro
- [ ] 20-30 trades totales (muestra significativa)

**Decisión al final de Fase 2**:
- **Si Intraday PF > 1.15**: Continuar a Fase 3 con Intraday habilitado
- **Si Intraday PF < 1.05**: Deshabilitar Intraday, pasar a Swing only
- **Si 1.05 < PF < 1.15**: Extender validación 1 semana más

---

## FASE 3: Operación Real (Semanas 4-12)

### Objetivo
Ejecutar con datos reales durante 12 semanas y decidir:
1. ¿Fase 2 afinada (mecanismos dinámicos)?
2. ¿Swing only?
3. ¿Ajustes de risk parameters?

### Endpoints de Fase 3

#### 1. **POST /api/phase3/log-trade**
Registra un trade cerrado durante operación real.

**Request body**:
```json
{
  "book": "swing",
  "ticker": "AAPL",
  "side": "BUY",
  "entry": 225.50,
  "exit": 232.25,
  "qty": 3,
  "pnl": 20.25,
  "reason": "TP"
}
```

**Response**:
```json
{
  "status": "ok",
  "message": "Trade logged for swing AAPL",
  "metrics": {
    "swing": {
      "trades": 50,
      "pnl": 2340.00,
      "pf": 1.42
    },
    "intraday": {
      "trades": 35,
      "pnl": 890.00,
      "pf": 1.22
    }
  }
}
```

**Automatización**: En tu sistema de ejecución, llama este endpoint cuando un trade cierre:

```python
import requests

def close_trade(book, ticker, entry, exit_price, qty, pnl, reason):
    """Cierra un trade y lo registra en dashboard"""
    
    payload = {
        'book': book,  # 'swing' o 'intraday'
        'ticker': ticker,
        'side': 'BUY',  # o 'SELL'
        'entry': entry,
        'exit': exit_price,
        'qty': qty,
        'pnl': pnl,
        'reason': reason  # 'TP', 'SL', 'TIME'
    }
    
    response = requests.post(
        'http://localhost:8050/api/phase3/log-trade',
        json=payload
    )
    
    return response.json()
```

#### 2. **GET /api/phase3/validation-plan**
Retorna plan de validación actual y progreso hacia decisión.

**Response**:
```json
{
  "phase": "PHASE 3 - OPERATION",
  "current_metrics": {
    "swing": {...},
    "intraday": {...},
    "total": {...}
  },
  "decision_criteria": {
    "swing_pf": {"value": 1.45, "requirement": "> 1.05"},
    "intraday_pf": {"value": 1.28, "requirement": "> 1.25 for READY"},
    "intraday_dd": {"value": 2.15, "requirement": "< 5%"},
    "weeks_collected": {"value": 5, "requirement": "8-12"}
  },
  "next_decision": "CONTINUE_PHASE2 - Need more validation weeks",
  "weekly_reports": [
    {"week": "2025-W04", "swing_pf": 1.32, "intraday_pf": 1.18},
    {"week": "2025-W05", "swing_pf": 1.40, "intraday_pf": 1.22},
    ...
  ]
}
```

#### 3. **GET /api/phase3/checklist**
Verifica readiness para Fase 3.

**Response**:
```json
{
  "phase": "PHASE 3 - OPERATION READINESS",
  "checks": {
    "code_ready": {
      "CapitalManager": "IMPLEMENTED",
      "RiskManager": "IMPLEMENTED",
      "IntraDayGates": "IMPLEMENTED",
      "MetricsTracker": "IMPLEMENTED",
      "Logging": "IMPLEMENTED"
    },
    "validation": {
      "Tests passing": "11/11 PASS",
      "Example scenarios": "5/5 PASS",
      "Documentation": "COMPLETE"
    },
    "operation_ready": {
      "Logging separated": true,
      "Metrics tracking": true,
      "Weekly reports": true,
      "Risk controls": true
    }
  },
  "ready": true,
  "timestamp": "2025-01-20T10:35:00.123456"
}
```

### Operación Real: Checklist Semanal

**Cada Lunes (inicio de semana)**:
1. `GET /api/phase3/validation-plan` → Revisa progreso
2. Verifica `weeks_collected` >= objetivo actual
3. Revisa `intraday_pf` trending hacia 1.25+ o < 1.05

**Cada Viernes (fin de semana)**:
1. `GET /api/phase2/weekly-report` → Guarda reporte
2. Documenta PF, winrate, DD por libro
3. Nota cualquier anomalía (comportamiento inesperado)

**Decisión final (Semana 8-12)**:

| Condición | Decisión |
|-----------|----------|
| Intraday PF > 1.25 & DD < 5% | **FASE 2 AFINADA**: Implementar gates dinámicos |
| Intraday PF < 1.05 | **SWING ONLY**: Deshabilitar Intraday |
| 1.05 < PF < 1.25 | **PHASE 2+ MEJORADA**: Reducir frequency, mejorar filters |

---

## Integración en Tu Sistema

### Dónde Enganchar METRICS_TRACKER.log_trade()

En tu sistema de ejecución actual (donde cierras trades):

```python
# Cuando un trade cierra (TP, SL, o time-stop):
METRICS_TRACKER.log_trade(
    book='swing',  # 'swing' o 'intraday'
    ticker='AAPL',
    side='BUY',  # 'BUY' o 'SELL'
    entry=225.50,
    exit_price=232.25,
    qty=3,
    pnl=20.25,  # Puede ser negativo (pérdida)
    reason_exit='TP'  # 'TP', 'SL', 'TIME'
)

# Opcionalmente, registra en API (si ejecutas desde otro proceso):
requests.post('http://localhost:8050/api/phase3/log-trade', json={
    'book': 'swing',
    'ticker': 'AAPL',
    'side': 'BUY',
    'entry': 225.50,
    'exit': 232.25,
    'qty': 3,
    'pnl': 20.25,
    'reason': 'TP'
})
```

### Logging Separado: Qué Esperar

**Archivo**: `reports/logs/dashboard.log`

```
2025-01-20 10:25:30 [INFO] [SWING] Trade closed: AAPL BUY @ 225.50 -> 232.25 (PnL: +20.25)
2025-01-20 10:26:15 [INFO] [INTRADAY] Trade closed: SPY BUY @ 510.30 -> 510.80 (PnL: +5.00)
2025-01-20 10:30:00 [INFO] [CAPITAL] Swing bucket available: 1,200 / 1,400
2025-01-20 10:45:30 [INFO] [RISK] Daily PnL: -45.00, Intraday enabled: true
2025-01-20 15:30:00 [INFO] [PHASE3] Trade logged: swing AAPL, PnL=20.25
```

---

## Flujo Completo de Fase 2-3

```
SEMANA 1-2: FASE 2 (Validación)
├─ Ejecutar Swing + Intraday con datos históricos
├─ Recolectar 20-30 trades por libro
├─ Revisar GET /api/phase2/metrics
├─ Revisar GET /api/phase2/weekly-report
└─ DECISIÓN: ¿Continuar con Intraday?

SEMANA 3-12: FASE 3 (Operación Real)
├─ Semana 4: POST /api/phase3/log-trade con trades reales
├─ Cada lunes: GET /api/phase3/validation-plan
├─ Cada viernes: GET /api/phase2/weekly-report & guardar
├─ Semana 8: Revisar criterios de decisión
├─ Semana 12: DECISIÓN FINAL
└─ OUTPUT: Fase 2 afinada, Swing only, o ajustes

SEMANA 13+: IMPLEMENTACIÓN
├─ Si Fase 2 afinada: Gates dinámicos, multi-ticker
├─ Si Swing only: Ajustar capital 100% Swing, optimizar
└─ Si ajustes: Modify risk parameters, re-validate
```

---

## Archivos de Referencia

**Código**:
- `dashboard_unified_temp.py`: Endpoints + MetricsTracker

**Documentación**:
- `FASE1_IMPLEMENTATION.md`: Arquitectura base (si existe)
- Este archivo: Fase 2-3 detallado
- `example_integration.py`: Ejemplos de integración

**Logs**:
- `reports/logs/dashboard.log`: Logging separado por libro

---

## Ejemplo de Uso

```python
import requests
import json
from datetime import datetime

# Monitorear Fase 2 (Validación)
response = requests.get('http://localhost:8050/api/phase2/metrics')
print(json.dumps(response.json(), indent=2))

# Registrar trade Fase 3 (Operación)
trade_data = {
    'book': 'swing',
    'ticker': 'AAPL',
    'side': 'BUY',
    'entry': 225.50,
    'exit': 232.25,
    'qty': 3,
    'pnl': 20.25,
    'reason': 'TP'
}
response = requests.post(
    'http://localhost:8050/api/phase3/log-trade',
    json=trade_data
)
print(f"Trade logged: {response.json()['message']}")

# Revisar plan de validación
response = requests.get('http://localhost:8050/api/phase3/validation-plan')
plan = response.json()
print(f"Current decision: {plan['next_decision']}")
print(f"Intraday PF: {plan['current_metrics']['intraday']['pf']:.2f}")
print(f"Weeks collected: {plan['decision_criteria']['weeks_collected']['value']}/12")
```

---

## Próximos Pasos

1. **Ahora**: Ejecuta `GET /api/phase3/checklist` para confirmar readiness
2. **Fase 2**: Ejecuta backtest con datos Ene 2024 - Feb 2024
3. **Fase 3**: Pasa a datos reales cuando Intraday PF > 1.15
4. **Semana 8-12**: Toma decisión basada en criterios

