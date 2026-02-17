# Dashboard Unificado - Guía Rápida

## Estado: ✅ ACTIVO EN http://localhost:7777

### Dos Pestañas Integradas

#### Pestaña 1: 📊 Trade Monitor
- **Propósito:** Monitorear posiciones activas en ejecución
- **Información:**
  - P&L total en tiempo real
  - Exposición actual vs. límite
  - Trades activos
  - Prob Win promedio del portfolio
  - Tarjetas detalladas por trade con:
    - Entrada, precio actual, TP, SL
    - PnL y porcentaje
    - Progreso hacia TP/SL
    - Distancia a objetivos

#### Pestaña 2: ⚖️ Plan Comparison
- **Propósito:** Comparar STANDARD vs PROBWIN_55
- **Información:**
  - Resumen de estadísticas por plan:
    - Cantidad de posiciones
    - Exposición total
    - Prob Win promedio
    - Tickers incluidos
  - Tarjetas de señales por plan con:
    - Ticker, Side (BUY/SELL)
    - Entry, TP, SL
    - Prob Win individual

### Datos en Tiempo Real

**Actualización automática:**
- Cada 10 segundos
- Precios vivos desde yfinance
- Manual: Botón "Actualizar"

**APIs disponibles:**
```
GET /api/data        → Datos de trades activos
GET /api/plans       → Datos de planes semanales
```

### Archivos Monitoreados

```
Trade Monitor:
  └── val/trade_plan_EXECUTE.csv

Plan Comparison:
  ├── evidence/weekly_plans/plan_standard_2026-01-26.csv
  └── evidence/weekly_plans/plan_probwin55_2026-01-26.csv
```

### Fuentes de verdad (estado activo)

```
PROBWIN activo → val/trade_plan_EXECUTE.csv
STANDARD activo → val/standard_plan_tracking.csv
```

> Los archivos plan_standard_*.csv son ideas (PLANNED). El estado ACTIVE de STANDARD vive en tracking.

### Apertura STANDARD (virtual)

- Trigger: al generar el plan STANDARD (o primer tracking del día)
- Acción:

```
plan_standard_*.csv
        ↓
standard_plan_tracking.csv
```

- El plan NO se modifica al abrir
- Tracking es el único archivo que puede cerrarse

### Comandos

```bash
# Ejecutar dashboard unificado
./.venv/Scripts/python.exe dashboard_unified.py

# Generar nuevos planes (próxima semana)
./.venv/Scripts/python.exe generate_weekly_plans.py

# Ver planes en CSV
cat evidence/weekly_plans/plan_standard_2026-01-26.csv
cat evidence/weekly_plans/plan_probwin55_2026-01-26.csv
```

### Características

✅ **Responsive:** Funciona en desktop y móvil  
✅ **Auto-refresh:** Actualización cada 10 segundos  
✅ **Pestañas dinámicas:** Cambio rápido entre vistas  
✅ **Precios en vivo:** yfinance actualizado  
✅ **Métricas agregadas:** Resúmenes por plan  
✅ **Colores intuitivos:** Verde (ganancia), Rojo (pérdida)  

---

**Dashboard Unificado: Trade Monitor + Plan Comparison en una sola aplicación**
