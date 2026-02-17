# ⚡ QUICK REFERENCE: PARÁMETROS CORRECTOS

**Fuente única de verdad:** [config/policies.yaml](config/policies.yaml) y [config/guardrails.yaml](config/guardrails.yaml)

> ⚠️ **Si estos números cambian en config/, actualiza esta guía**

---

## 💰 CAPITAL Y RIESGO

| Parámetro | Valor | Significado |
|-----------|-------|-------------|
| `capital_max` | $100,000 | Techo de capital total |
| `per_trade_cash` | $2,500 | Asignación nominal por trade (cuentas grandes) |
| `max_open_positions` | 15 | Máximo trades simultáneos |
| `per_ticker_cap` | $5,000 | Max exposición en 1 ticker |
| `cooldown_days_same_ticker` | 2 | Espera min entre trades del mismo ticker |

**Para tu capital ($1-5k):**
- `per_trade_cash_scaled` = $2,500 × (tu capital / $100,000)
- Ejemplo: Capital $2,000 → $50 por trade ❌  
- **Correcto:** $2,000 × 0.12 = $250 por trade ✅

---

## 🎯 PROBABILIDAD Y UMBRALES

| Régimen | Threshold `prob_win` | Timing | Notas |
|---------|---|---|---|
| **LOW_VOL** | ≥ 0.60 (60%) | Mercado calmo, VIX <15 | Más señales |
| **MED_VOL** | ≥ 0.62 (62%) | Normal, VIX 15-20 | Filtro medio |
| **HIGH_VOL** | ≥ 0.65 (65%) | Volátil, VIX >20 | Muy selectivo |

**¿Cómo se detecta el régimen?**
```python
python scripts/12_detect_regime.py  # Genera data/daily/regime_daily.csv
cat data/daily/regime_daily.csv | tail -1  # Ver régimen de hoy
```

---

## 📊 STOP LOSS Y TAKE PROFIT

| Parámetro | Valor | Ejemplo |
|-----------|-------|---------|
| `stop_loss_pct_default` | 2% | Entry $100 → SL $98 |
| `take_profit_pct_default` | 10% | Entry $100 → TP $110 |
| **R:R Implícito** | 5:1 | Ganas $5 x cada $1 en riesgo |

**¿Puedo cambiar SL/TP?**
- ❌ NO durante operaciones
- ✅ SÍ, pero requiere revalidación walk-forward completa
- **Proceso:** Cambia → Re-entrena modelos → Backtest → Valida antes de operar

---

## 📈 CALIBRACIÓN Y CALIDAD

| Métrica | Umbral Aceptable | Umbral Crítico | Acción |
|---------|---|---|---|
| **Brier Score** | ≤ 0.14 | > 0.16 | Alerta; recalibra si persiste |
| **ECE** | ≤ 0.05 | > 0.07 | Reentrenamiento de modelos |
| **Coverage** | 15-25% | < 10% o > 35% | Ajusta gates |
| **Lift Top Decile** | ≥ 1.40 | < 1.20 | Modelo degradado |

**¿Qué significan?**
- **Brier:** Error de calibración (qué tan bien predice prob_win)
- **ECE:** Expected Calibration Error (generalización)
- **Coverage:** % de señales pasando gates (15-25% es saludable)
- **Lift:** Cuánto mejor que aleatorio es el modelo

---

## 🔔 COBERTURA Y CONCENTRACIÓN

| Parámetro | Min | Max | Acción si viola |
|-----------|-----|-----|---|
| Coverage % | 15% | 25% | Ajusta prob_win threshold |
| Max ticker % | - | 25% | Pasa max 25% capital en 1 ticker |
| Max top 5 % | - | 50% | Diversifica si top 5 > 50% |
| Max sector % | - | 40% | No todo tech, no todo financiero |

**Regla:** Si concentración > límite → sistema alerta pero NO bloquea.

---

## ⏱️ TIME-TO-HIT (TTH) PARÁMETROS

| Régimen | Max ETTH (minutos) | Significado |
|---------|---|---|
| LOW_VOL | 120 min (2h) | Movimiento lento, target largo |
| MED_VOL | 90 min | Movimiento normal |
| HIGH_VOL | 60 min (1h) | Volatilidad alta, cierre rápido |

**¿Es en minutos intraday?**
- Sí, pero se proyecta a días para H3
- Ejemplo: ETTH=90 min en intraday → ≈3-4 días en H3

---

## 🚨 KILL SWITCH Y ALERTAS

| Condición | Acción | Recuperación |
|-----------|--------|---|
| Win rate < 50% (5d window) | **Auto-pausa** sistema | Manual: fix + revalidar |
| Brier > 0.16 (2d seguido) | ⚠️ Warning | Auto-recalibra si `auto_recalibrate=true` |
| Coverage < 15% | ⚠️ Warning | Reduce prob_win threshold |
| Coverage > 35% | ⚠️ Warning | Aumenta prob_win threshold |
| Max DD > 6% | ⚠️ Warning | Reduce position size 50% |

**Cómo reseteamos kill switch?**
```powershell
# Revisar qué pasó
python scripts/41_daily_health_checks.py

# Recalibrar si necesario
python scripts/10b_calibrate_probabilities.py

# Revalidar
python production_orchestrator.py --date=2026-01-14

# Si healthy: resume operación
```

---

## 📋 MONITORING DIARIO (QUÉ REVISAR)

### **Archivo 1: Trade Plan**
```powershell
cat val/trade_plan.csv
```
**Columnas críticas:**
- `ticker`, `entry_price`, `tp_price`, `sl_price` ← Parámetros
- `prob_win_cal` ← Debe ser >60% (si no, algo raro)
- `etth_days` ← Debe estar 1-5 días
- `expected_pnl_pct` ← Debe ser >2% (si <0%, rechaza trade)

### **Archivo 2: Health Check**
```powershell
cat reports/health/daily_health_*.json
```
**Busca:**
```json
{
  "status": "healthy",           ✅ Debe ser "healthy"
  "kill_switch_active": false,   ✅ Debe ser false
  "coverage_pct": 18.5,          ✅ Debe estar 15-25%
  "brier_score": 0.128,          ✅ Debe ser <0.14
  "errors": [],                  ✅ Debe estar vacío
  "warnings": []                 ✅ Idealmente vacío
}
```

### **Archivo 3: Régimen Actual**
```powershell
cat data/daily/regime_daily.csv | tail -5
```
**Busca:**
- `2026-01-14,MED_VOL` ← Régimen hoy
- Si HIGH_VOL esperado → menos señales, eso es normal

---

## 🎯 ESCENARIOS DE RETORNO (SIN CAMBIOS)

**Después de 20+ trades propios, estos números se recomputan:**

| Escenario | Win% | EV/trade | Trades/mes | Return/mes |
|-----------|------|----------|-----------|-----------|
| 🔴 Conservador | 60% | 3.0% | 5 | +9% |
| 🟡 Base | 75% | 4.2% | 6 | +16% |
| 🟢 Optimista | 83% | 5.3% | 6 | +26% |

**⚠️ NOTA:** Con n=6 (octubre), NO puedes apostar a optimista. Base es lo razonable.

---

## 📞 QUICK FIXES COMUNES

| Problema | Check | Fix |
|----------|-------|-----|
| No hay señales | Régimen HIGH_VOL? | Normal, espera |
| Señales demasiadas | Coverage >25%? | Aumenta prob_win threshold |
| Win rate baja | Brier >0.14? | Recalibra modelos |
| Plan falla validación | Health JSON errors? | Ver validation.log |
| Excel no actualiza | Archivos locked? | Cierra Excel, re-run |

---

## 🔗 ARCHIVOS QUE CONSULTAR

| Cuando quieras... | Archivo |
|---|---|
| Verificar parámetros capital/riesgo | [config/policies.yaml](config/policies.yaml) |
| Ver umbrales de salud | [config/guardrails.yaml](config/guardrails.yaml) |
| Revisar plan del día | [val/trade_plan.csv](val/trade_plan.csv) |
| Chequear salud del sistema | [reports/health/daily_health_*.json](reports/health) |
| Ver historial regímenes | [data/daily/regime_daily.csv](data/daily/regime_daily.csv) |
| Analizar desempeño | `python enhanced_metrics_reporter.py` |
| Recalibrar modelos | `python scripts/10b_calibrate_probabilities.py` |
| Hacer health check | `python scripts/41_daily_health_checks.py` |

---

## ✅ TABLA DIFERENCIA: CONFIG vs REALIDAD

| Parámetro | Config Value | Lo que significa | ¿Cómo valido? |
|-----------|---|---|---|
| `capital_max: 100000` | Techo | No puedo operar > $100k | Revisar saldo broker |
| `per_trade_cash: 2500` | Nominal | Por cada trade, ~$2500 (escala si <$100k) | `val/trade_plan.csv` |
| `prob_threshold.low_vol: 0.60` | Minimum | Si LOW_VOL y prob<60%, rechaza | `val/trade_plan.csv` `prob_win_cal` |
| `stop_loss_pct: 0.02` | Fixed | Siempre -2% SL | Verificar `sl_price` vs `entry_price` |
| `coverage_target: 15-25%` | Range | Esperado 15-25% de universo pase gates | Health JSON `coverage_pct` |

---

## 🎓 CÓMO LEER ESTOS ARCHIVOS

### Ejemplo: Revisar trade_plan.csv

```powershell
# Ver encabezados
(cat val/trade_plan.csv | Select-Object -First 1) -split ','

# Ver primeros 5 trades
cat val/trade_plan.csv | Select-Object -First 6

# Contar total trades
(cat val/trade_plan.csv | wc -l) - 1  # -1 para header
```

### Ejemplo: Revisar health JSON

```powershell
# Pretty print
cat reports/health/daily_health_*.json | ConvertFrom-Json | ConvertTo-Json

# Ver solo status
cat reports/health/daily_health_*.json | grep "status"

# Ver warnings
cat reports/health/daily_health_*.json | grep -A5 "warnings"
```

### Ejemplo: Verificar régimen

```powershell
# Ver últimos 5 días
tail -5 data/daily/regime_daily.csv

# Ver hoy
tail -1 data/daily/regime_daily.csv
```

---

## 🚀 CHECKLIST: ANTES DE OPERAR

- [ ] Capital en broker
- [ ] `.\run_h3_daily.ps1` ejecutado sin errores
- [ ] `cat val/trade_plan.csv` genera N trades (3-15)
- [ ] `cat reports/health/daily_health_*.json` status = "healthy"
- [ ] `kill_switch_active` = false
- [ ] Coverage 15-25%
- [ ] Brier < 0.14
- [ ] Todas las fechas son T-1 (ayer)
- [ ] Broker configurado (órdenes TP/SL automáticas o manuales)
- [ ] Telegram notificaciones (opcional)

**Si algo falla:** STOP. No operes. Debuggea primero.

---

## 📞 EMERGENCY CONTACTS

Si algo anda mal:

1. **Health check muestra error:**
   ```powershell
   cat tmp/validation_*.log  # Ver detalles
   ```

2. **Kill switch activado (win rate <50%):**
   ```powershell
   python scripts/10b_calibrate_probabilities.py  # Recalibra
   python production_orchestrator.py --test        # Revalida
   ```

3. **Pipeline falla (yfinance, timeout):**
   ```powershell
   python scripts/00_download_daily.py --retry     # Reintenta descarga
   ```

4. **Números no cuadran:**
   ```powershell
   python enhanced_metrics_reporter.py  # Reporte detallado
   ```

---

**Última actualización:** 2026-01-14  
**Próxima revisión:** Después de 20 trades en enero 2026

