# VISUAL GUIDE: Swing + Fase 2 Architecture

## 1️⃣ FLUJO DE EJECUCIÓN (High Level)

```
┌─────────────────────┐
│  Tu Generador de    │
│  Señales (forecast  │
│  + patterns +       │
│  memory)            │
└──────────┬──────────┘
           │
           ▼
      ┌────────────┐
      │ Signal:    │
      │ {book,     │
      │  ticker,   │
      │  entry,    │
      │  qty, ...} │
      └────┬───────┘
           │
           ▼
   ┌───────────────────────────────────┐
   │  CAPITAL MANAGER                  │
   │  ├─ ¿Capital disponible?          │
   │  ├─ ¿No está duplicado?           │
   │  └─ ¿No excede límites?           │
   │                                   │
   │  Si NO → RECHAZA                  │
   │  Si SÍ → CONTINUA                 │
   └────┬────────────────────────────────┘
        │
        ▼
   ┌──────────────────────────────────┐
   │ ¿Es INTRADAY?                    │
   └─┬─────────────────────────────────┘
     │
  NO │                        SÍ
     │                        │
     │                        ▼
     │              ┌──────────────────────┐
     │              │ RISK MANAGER         │
     │              │ ¿Intraday enabled?   │
     │              │ (kill-switches OK?)  │
     │              │                      │
     │              │ Si NO → RECHAZA      │
     │              │ Si SÍ → CONTINUA     │
     │              └────┬─────────────────┘
     │                   │
     │                   ▼
     │         ┌──────────────────────────┐
     │         │ INTRADAY GATES (4)       │
     │         │ ├─ Gate 1: Contexto      │
     │         │ ├─ Gate 2: Multi-TF      │
     │         │ ├─ Gate 3: Strength      │
     │         │ └─ Gate 4: R:R           │
     │         │                          │
     │         │ Si CUALQUIERA falla →    │
     │         │ RECHAZA                  │
     │         │                          │
     │         │ Si TODAS pasan →         │
     │         │ CONTINUA                 │
     │         └────┬─────────────────────┘
     │              │
     └──────────────┴──────────────────────┐
                    │                       │
                    ▼                       │
             EJECUTAR TRADE ◄──────────────┘
                    │
                    ▼
        ┌──────────────────────────┐
        │ Registrar en:            │
        │ • open_swing             │
        │ • open_intraday          │
        └──────────────────────────┘
                    │
                    ▼
            (Monitorear en mercado)
                    │
                    ▼
        ┌──────────────────────────┐
        │ TRADE CIERRA (TP/SL/TO)  │
        └────┬─────────────────────┘
             │
             ▼
    ┌────────────────────┐
    │ Actualizar:        │
    │ • update_pnl()     │
    │ • remove_open()    │
    └────────────────────┘
```

---

## 2️⃣ ARQUITECTURA POR COMPONENTE

### CapitalManager

```
┌─────────────────────────────────────┐
│        CapitalManager               │
│     Total: $2,000                   │
├─────────────────────────────────────┤
│ Swing Bucket: $1,400 (70%)          │
│ ├─ AAPL x3   = $540                 │
│ ├─ MSFT x2   = $760                 │
│ └─ Available = $100                 │
├─────────────────────────────────────┤
│ Intraday Bucket: $600 (30%)         │
│ ├─ TSLA x2   = $480                 │
│ └─ Available = $120                 │
├─────────────────────────────────────┤
│ Heat Control: Si TSLA en Swing →    │
│ Intraday TSLA reduce 50%            │
├─────────────────────────────────────┤
│ Límites:                            │
│ • Total open: 4/4 (FULL)            │
│ • Swing open: 2/3                   │
│ • Intraday open: 1/2                │
└─────────────────────────────────────┘
```

### RiskManager

```
┌──────────────────────────────────────┐
│      RiskManager (Kill-Switches)     │
├──────────────────────────────────────┤
│ Intraday Enabled: TRUE               │
├──────────────────────────────────────┤
│ Daily Stop:                          │
│ • Limit: -$18 (-3% de $600)         │
│ • Loss today: -$5 ✓ OK              │
│ • Status: ENABLED                   │
├──────────────────────────────────────┤
│ Weekly Stop:                         │
│ • Limit: -$36 (-6% de $600)         │
│ • Loss this week: -$12 ✓ OK         │
│ • Status: ENABLED                   │
├──────────────────────────────────────┤
│ Drawdown Gate:                       │
│ • Limit: -$200 (-10% de $2000)      │
│ • Current drawdown: -$50 ✓ OK       │
│ • Status: ENABLED                   │
├──────────────────────────────────────┤
│ AUTO-ACTIONS:                        │
│ • Si daily loss > -$18 → OFF         │
│ • Si weekly loss > -$36 → OFF        │
│ • Si DD > -$200 → OFF               │
│ • Lunes 00:00 → Reset weekly        │
└──────────────────────────────────────┘
```

### Intraday Gates

```
100 SEÑALES INTRADAY
    │
    ▼
┌─────────────────────────────────────┐
│ Gate 1: Contexto Macro (10% rechaza)│
│ ├─ ¿SPY/QQQ en rango lateral?       │
│ ├─ ¿Día de evento? (CPI/FOMC/etc)   │
│ └─ [90 señales pasan]               │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Gate 2: Multi-TF (20% rechaza)      │
│ ├─ ¿BUY vs daily UP? ✓              │
│ ├─ ¿SELL vs daily DOWN? ✓           │
│ └─ [72 señales pasan]               │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Gate 3: Signal Strength (15% rechaza)│
│ ├─ Min strength: 50%                │
│ └─ [61 señales pasan]               │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Gate 4: Risk/Reward (10% rechaza)   │
│ ├─ Max SL: 3% distancia             │
│ ├─ Min R:R: 1.5:1                   │
│ └─ [55 señales pasan] = 55% ratio   │
└─────────────────────────────────────┘

👉 55% de señales = ALTA CALIDAD
```

---

## 3️⃣ BUCKETS OVER TIME

```
Día 1:
Swing: $1,400
├─ AAPL +$100 → $1,500 (ganancias acumuladas)
│
Intraday: $600
├─ TSLA -$20 → $580

Semana 1:
Swing: $1,500 (70% del capital)
Intraday: $580 (30% del capital)
Total: $2,080 (+4%)

Si Intraday PF > 1.25 & DD < 5% en 8 semanas:
├─ Semana 9: Cambiar a 60% Swing / 40% Intraday
└─ Implementar Gates dinámicas
```

---

## 4️⃣ LOGGING ESPERADO

### Startup
```
[INFO] [CAPITAL] Initialized: Total=$2000, Swing=70% ($1400.0), Intraday=30% ($600.0)
[INFO] [RISK] Initialized: Daily stop 3.0%, Weekly stop 6.0%, DD threshold 10.0%
```

### Ejecución (Swing)
```
[INFO] [CAPITAL] Swing opened: AAPL x3
[INFO] [HTTP] OK POST /api/execute 200 (15.2ms)
```

### Ejecución (Intraday)
```
[INFO] [CAPITAL] Intraday opened: TSLA x2
[INFO] [INTRADAY] All gates passed for TSLA: strength=75%, RR=2.00:1
```

### Gates Rechazadas
```
[INFO] [GATE2] AMD BUY conflicts with daily DOWN trend
[INFO] [GATE3] AMD signal weak: 30% < 50%
[INFO] [GATE4] AMD SL too large: 3.33% > 3%
```

### Kill-Switch Disparado
```
[WARNING] [RISK] Daily stop hit: Intraday disabled (loss $-23.00)
[INFO] [RISK] Weekly reset: Intraday enabled
```

---

## 5️⃣ MÉTRICAS POR SEMANA

```
REPORTE SEMANAL (Week 1):
────────────────────────────
SWING:
  Trades: 5
  Winners: 3 (60%)
  Losers: 2
  PnL: +$80.00
  PF: 1.45

INTRADAY:
  Trades: 8
  Winners: 5 (62.5%)
  Losers: 3
  PnL: +$20.00
  PF: 1.20

TOTAL:
  PnL: +$100.00
  Buckets: Swing $1,480 | Intraday $620
  DD: -1.0%

DECISION: ✓ Intraday adding value, continue
```

---

## 6️⃣ DECISIÓN EN SEMANA 12

```
IF Intraday PF > 1.25 AND DD < 5%:
  → Fase 2 AFINADA
    ├─ Cambiar a 60% Swing / 40% Intraday
    ├─ Selección dinámica de tickers semanal
    └─ TP/SL adaptativo (Gate 4 dinámico)

ELSE IF Intraday PF < 1.05:
  → Apagar Intraday
    └─ Volver a Swing only

ELSE:
  → Continuar Fase 2 básica
    └─ Esperar más datos
```

---

## 7️⃣ CONFIGURACIÓN (Editables)

```python
# Capital
CAPITAL_MANAGER = CapitalManager(
    total_capital=2000,        # ← Cambiar aquí
    swing_pct=0.70,            # ← O aquí (70/30)
    intraday_pct=0.30
)

# Límites de posiciones
max_open_total = 4             # ← 4 simultáneos
max_open_swing = 3             # ← 3 Swing
max_open_intraday = 2          # ← 2 Intraday

# Kill-switches
daily_stop = 0.03              # ← -3% del bucket intraday
weekly_stop = 0.06             # ← -6% del bucket intraday
dd_threshold = 0.10            # ← -10% del capital total

# Gates intraday
gate3_min_strength = 50        # ← Signal strength mínimo
gate4_max_sl = 0.03            # ← SL máximo 3%
gate4_min_rr = 1.5             # ← R:R mínimo 1.5:1
```

---

## 8️⃣ TIMELINE

```
DAY 1:          Read docs → Run tests → Understand
WEEK 1:         Integrate with your signal generator
WEEK 2-4:       Collect data (Swing + Intraday separate)
WEEK 5-8:       Analyze value (Is Intraday worth it?)
WEEK 9-12:      Decision (Fase 2 afinada? Or stop?)
```

---

**Creado**: Feb 2, 2026  
**Formato**: Visual Guide para referencia rápida
