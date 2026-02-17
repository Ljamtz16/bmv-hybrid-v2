# OPERACIÓN FASE 3: Quick Start Guide

## 🚀 TL;DR - Cómo Operar

### Inicio (Lunes)
```bash
# Terminal 1: Inicia dashboard
python dashboard_unified_temp.py

# Terminal 2: Verifica readiness
python -c "import requests; print(requests.get('http://localhost:8050/api/phase3/checklist').json())"
```

### Durante la Semana
```bash
# Cuando un trade CIERRA (TP, SL, TIME):
curl -X POST http://localhost:8050/api/phase3/log-trade \
  -H "Content-Type: application/json" \
  -d '{
    "book": "swing",
    "ticker": "AAPL",
    "side": "BUY",
    "entry": 225.50,
    "exit": 232.25,
    "qty": 3,
    "pnl": 20.25,
    "reason": "TP"
  }'
```

### Fin de Semana (Viernes)
```bash
# Revisa reporte semanal
curl http://localhost:8050/api/phase2/weekly-report | python -m json.tool

# Revisa plan de validación
curl http://localhost:8050/api/phase3/validation-plan | python -m json.tool
```

---

## 📊 Qué Esperar en Cada Semana

### Semana 1-2 (Fase 2: Validación Rápida)
- **Target**: 20-30 trades total (12-16 swing, 8-12 intraday)
- **Stop si**: Swing PF < 1.00 o Intraday PF < 0.90
- **Continue si**: Swing PF > 1.05 y Intraday PF > 1.10

**Resultado esperado**:
```json
{
  "swing_pf": 1.25,
  "intraday_pf": 1.15,
  "recommendation": "CONTINUE - Intraday adding value"
}
```

### Semana 3-4 (Fase 3: Operación Real Comienza)
- **Start**: Ejecutar con dinero real en Swing + Intraday
- **Monitor**: PnL acumulado, drawdown diario
- **Stop si**: Daily DD > -3% (intraday se desactiva automático)

**Métrica clave**:
```
Intraday contributing: PF > 1.15 + DD < 2%
```

### Semana 5-8 (Fase 3: Validación Intermedia)
- **Monitor**: PF estable o mejorando
- **Decision point semana 8**: 
  - Si Intraday PF > 1.25 & DD < 5% → Preparar Fase 2 afinada
  - Si Intraday PF < 1.05 → Considerar Swing only

**Control**:
```
GET /api/phase3/validation-plan
→ next_decision debe estar en camino a una decisión
```

### Semana 9-12 (Fase 3: Decisión Final)
- **Criterios de Decisión**:
  | Condición | Acción |
  |-----------|--------|
  | Intraday PF > 1.25 & DD < 5% | Fase 2 afinada (dinámico) |
  | Intraday PF < 1.05 | Swing only (desabilitar intraday) |
  | 1.05 ≤ PF ≤ 1.25 | Continuar Fase 2 estándar |

---

## 🔄 Flujo de Datos Real

```
Tu Sistema de Trading
    ↓
    ├─ [Trade Close Event]
    │   ├─ Registra en tu DB
    │   ├─ POST /api/phase3/log-trade  ← AQUÍ ENGANCHAR
    │   └─ METRICS_TRACKER.log_trade() actualiza
    │
    └─ [Dashboard Dashboard]
        ├─ GET /api/phase2/metrics      ← Revisar diario
        ├─ GET /api/phase2/weekly-report ← Revisar viernes
        └─ GET /api/phase3/validation-plan ← Revisar semana 8-12
```

---

## 💻 Integración en Tu Código

### Opción A: Direct Call (Si tienes METRICS_TRACKER en memoria)
```python
# En tu ejecutor de trades
METRICS_TRACKER.log_trade(
    book='swing',
    ticker='AAPL',
    side='BUY',
    entry=225.50,
    exit_price=232.25,
    qty=3,
    pnl=20.25,
    reason_exit='TP'
)
```

### Opción B: HTTP Call (Si ejecutas desde otro proceso)
```python
import requests

def on_trade_close(trade_dict):
    """Llamada cuando un trade cierra en tu sistema"""
    
    requests.post('http://localhost:8050/api/phase3/log-trade', json={
        'book': trade_dict['book'],  # 'swing' o 'intraday'
        'ticker': trade_dict['ticker'],
        'side': trade_dict['side'],  # 'BUY' o 'SELL'
        'entry': trade_dict['entry_price'],
        'exit': trade_dict['exit_price'],
        'qty': trade_dict['quantity'],
        'pnl': trade_dict['pnl'],
        'reason': trade_dict['close_reason']  # 'TP', 'SL', 'TIME'
    })
```

---

## 📈 Métricas Clave a Monitorear

### Diarias
- Daily PnL
- Current DD (drawdown)
- Intraday enabled status

### Semanales
- Trades count (swing vs intraday)
- PF (Profit Factor) by book
- Winrate by book
- Avg Win / Avg Loss

### Criterios Decisión (Semana 8-12)
```
READY_FOR_ADVANCED:
  ├─ Swing PF > 1.15
  ├─ Intraday PF > 1.25
  ├─ Intraday DD < 5%
  └─ Capital growth > 10%

SWING_ONLY:
  ├─ Intraday PF < 1.05
  └─ Intraday contributing negativo

PHASE2_STANDARD:
  └─ Entre los dos anteriores
```

---

## 🛑 Stop Rules (Kill-Switches Automáticos)

**Risk Manager ejecutará automático**:

1. **Daily Stop** (-3% intraday bucket)
   - Intraday se desactiva por el día
   - Swing continúa normalmente

2. **Weekly Stop** (-6% total capital)
   - Todas operaciones se pausan por 1 día
   - Se resetea automáticamente

3. **Drawdown Stop** (-10% capital total)
   - Kill-switch: ambos libros pausados
   - Manual reset requerido

**Logging**: Revisar `reports/logs/dashboard.log` para ver triggers

---

## ✅ Checklist Semanal

### Lunes (Inicio)
- [ ] Dashboard corriendo en terminal (`python dashboard_unified_temp.py`)
- [ ] Verificar health: `curl http://localhost:8050/api/health`
- [ ] Revisar métricas acumuladas: `/api/phase2/metrics`

### Viernes (Fin)
- [ ] Exportar reporte semanal: `GET /api/phase2/weekly-report`
- [ ] Guardar en archivo: `weekly_report_2025-W03.json`
- [ ] Revisar `/api/phase3/validation-plan`
- [ ] Documentar en spreadsheet (PF, winrate, DD)

### Cada 2 Semanas
- [ ] Comparar PF con semana anterior (trend?)
- [ ] Si Intraday PF < 1.10: revisar qué salió mal
- [ ] Si Swing PF < 1.05: auditar señales de entrada

### Semana 8-12
- [ ] Revisar criterios finales
- [ ] Hacer decisión (Fase 2 afinada, Swing only, etc.)
- [ ] Documentar reasoning
- [ ] Implementar siguiente fase

---

## 🐛 Troubleshooting

### "Cannot connect to API"
```bash
# Verificar que dashboard está corriendo
netstat -an | grep 8050

# Reiniciar dashboard
# Terminal 1:
# Ctrl+C → python dashboard_unified_temp.py
```

### "Metrics not updating"
```bash
# Verificar logging
tail -f reports/logs/dashboard.log | grep "Trade logged\|PHASE3"

# Revisar /api/phase2/metrics → check "trades" count incrementa
```

### "PF shows 0.00"
```
Normal al inicio (sin trades aún)
Espera a que el primer trade cierre
Revisa logs: grep "METRICS_TRACKER\|PF" dashboard.log
```

### "Risk manager disabled intraday"
```bash
# Check why:
GET /api/phase2/metrics → check "daily_pnl" 
Si daily_pnl < -3% intraday_bucket → auto-disabled

# Reset: cambiar RISK_MANAGER.kill_switch manualmente
# O esperar a siguiente día (auto-reset)
```

---

## 📁 Files to Monitor

| File | Purpose | Check Frequency |
|------|---------|-----------------|
| `reports/logs/dashboard.log` | Trade logging + risk alerts | Daily |
| `trade_plan_EXECUTE.csv` | Active trades | Real-time (tu sistema) |
| `trade_history_closed.csv` | Closed trades | Weekly (reconciliar) |

---

## 🎯 Decision Template (Semana 8-12)

Cuando llegues a la semana 8-12, usa este template:

```markdown
# PHASE 3 DECISION - Semana XX

## Métricas Finales
- Swing PF: 1.XX
- Intraday PF: 1.XX
- Intraday DD: X.XX%
- Capital Growth: +X%
- Total Trades: XXX (YYY swing, ZZZ intraday)

## Análisis
- Swing está rentable: SI / NO
- Intraday agregó valor: SI / NO
- Drawdown fue aceptable: SI / NO

## DECISIÓN FINAL
- [ ] FASE 2 AFINADA: Implementar gates dinámicos + multi-ticker
- [ ] SWING ONLY: Deshabilitar intraday, optimizar swing
- [ ] PHASE 2+: Ajustar parámetros, continuar validación

## Next Steps
1. [Implementación específica]
2. [Parámetros a cambiar]
3. [Testing requerido]
```

---

## 📞 Support Resources

- **Dashboard API**: `http://localhost:8050/` (check all endpoints)
- **Logging**: `tail -f reports/logs/dashboard.log`
- **Tests**: `pytest test_capital_risk.py -v`
- **Integration example**: `python fase3_integration_example.py`

---

## 🎬 Let's Go!

```bash
# 1. Inicia dashboard
python dashboard_unified_temp.py

# 2. Verifica readiness
python fase3_integration_example.py

# 3. Comienza a operar + registra trades
# POST /api/phase3/log-trade cuando cierres

# 4. Revisa progreso semanal
# GET /api/phase3/validation-plan

# 5. Semana 8-12: Toma decisión final
```

**Let's validate this system! 🚀**
