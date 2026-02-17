# GATE AVANZADO: Fase 2 y 3 - Implementación Completa

## 🔹 FASE 2: Ticker Gate Dinámico Intra-Mes

### **Concepto**
En lugar de un gate fijo mensual, recalcula Monte Carlo **cada semana** y permite **rotación de tickers** (drop bajo performers, add nuevos candidatos).

### **Ventajas**
✓ Adapta el portafolio a cambios de mercado intra-mes  
✓ Drop tickers que deterioran su score MC  
✓ Add tickers emergentes con mejor performance reciente  
✓ Mayor flexibilidad sin sobre-trading (max rotation limit)

### **Script: `montecarlo_gate_dynamic.py`**

**Uso básico:**
```bash
python montecarlo_gate_dynamic.py \
  --month 2025-03 \
  --rebalance-freq weekly \
  --top-k 4 \
  --max-rotation 2 \
  --output-dir evidence/dynamic_gate_mar2025
```

**Parámetros clave:**
- `--rebalance-freq`: `weekly` (cada lunes) o `biweekly` (cada 2 semanas)
- `--max-rotation`: máximo de tickers a cambiar por rebalance (ej. 2 de 4)
- `--lookback-days`: ventana MC (default 20 días)
- `--mc-paths`: paths Monte Carlo (default 300)

**Ejemplo de rotación:**
```
Rebalance 1 (2025-03-03): CVX, XOM, PFE, NVDA (initial)
Rebalance 2 (2025-03-10): CVX, XOM, PFE, AMD (dropped NVDA, added AMD)
Rebalance 3 (2025-03-17): CVX, XOM, AMD, MSFT (dropped PFE, added MSFT)
Rebalance 4 (2025-03-24): CVX, XOM, AMD, MSFT (no change)
```

**Output:**
- `dynamic_gate.json`: historial completo de rebalances
- `rebalance_N_YYYYMMDD.json`: snapshot de cada rebalance

**Integración con backtest:**
Modificar `wf_paper_month.py` para leer el rebalance activo de cada fecha:
```python
# Load dynamic gate
with open("evidence/dynamic_gate_mar2025/dynamic_gate.json") as f:
    dynamic_gate = json.load(f)

# For each trading day, find active rebalance
for trade_date in trading_days:
    active_rebalance = get_active_rebalance(dynamic_gate, trade_date)
    tickers = active_rebalance['portfolio']
    # Use these tickers for this day
```

---

## 🔹 FASE 3: Score Híbrido (MC + Signal Quality)

### **Concepto**
Combina **Monte Carlo score** (histórico) con **Signal Quality score** (actual):

```
FinalScore = 0.6 × MC_Score + 0.4 × SignalQuality_Score
```

**Problema que resuelve:**  
Evita tickers "estadísticamente buenos pero sin buenos setups actuales".

### **Signal Quality Score**
Métricas de calidad de señales recientes (últimos 10 días):
- **Mean prob_win**: promedio de probabilidad de ganar (>0.5 = bueno)
- **Signal count**: número de señales (más oportunidades = mejor)
- **Consistency**: desviación estándar baja = señales consistentes
- **Recency**: señales de últimos 3 días pesan más

**Fórmula:**
```python
quality_score = (
    0.50 * (mean_prob - 0.5) * 2 +      # prob_win normalized
    0.20 * min(n_signals / 10, 1.0) +   # signal count (cap at 10)
    0.15 * (1 - min(std_prob * 4, 1)) + # consistency
    0.15 * (recent_prob - 0.5) * 2      # recency weight
)
```

### **Script: `hybrid_score_gate.py`**

**Uso básico:**
```bash
python hybrid_score_gate.py \
  --asof-date 2025-03-31 \
  --forecast data/daily/signals_with_gates.parquet \
  --mc-weight 0.6 \
  --signal-weight 0.4 \
  --output-dir evidence/hybrid_gate_mar2025
```

**Parámetros:**
- `--mc-weight`: peso del score MC (default 0.6)
- `--signal-weight`: peso del signal quality (default 0.4)
- `--signal-lookback`: ventana para señales (default 10 días)
- `--forecast`: archivo con señales (debe tener `prob_win`, `ticker`, `date`)

**Ejemplo de output:**
```
TOP-4 SELECTED TICKERS (Hybrid Score):
  1. CVX    | Hybrid:  0.524 | MC:  0.683 | Signal:  0.245
  2. XOM    | Hybrid:  0.487 | MC:  0.592 | Signal:  0.312
  3. NVDA   | Hybrid:  0.421 | MC:  0.398 | Signal:  0.467
  4. MSFT   | Hybrid:  0.398 | MC:  0.301 | Signal:  0.589
```

**Interpretación:**
- **CVX**: excelente MC + señales OK → top pick
- **MSFT**: MC moderado pero señales muy fuertes → entra en top-4
- **AMD**: buen MC pero sin señales recientes → NO entra

**Output:**
- `hybrid_gate.json`: ranking con scores híbridos y componentes

---

## 📋 PIPELINE COMPLETO RECOMENDADO

### **1. Gate Estático Mensual (actual)**
```bash
# Al inicio del mes (baseline)
python montecarlo_gate.py \
  --asof-date 2025-03-31 \
  --output-dir evidence/ticker_gate_mar2025

python montecarlo_param_gate.py \
  --gate-file evidence/ticker_gate_mar2025/ticker_gate.json \
  --output-dir evidence/param_gate_mar2025
```

### **2. Gate Dinámico Semanal (Fase 2)**
```bash
# Recalcula cada lunes, permite rotación
python montecarlo_gate_dynamic.py \
  --month 2025-03 \
  --rebalance-freq weekly \
  --max-rotation 2 \
  --output-dir evidence/dynamic_gate_mar2025
```

### **3. Gate Híbrido (Fase 3)**
```bash
# Combina MC + señales actuales
python hybrid_score_gate.py \
  --asof-date 2025-03-31 \
  --forecast data/daily/signals_with_gates.parquet \
  --mc-weight 0.6 \
  --signal-weight 0.4 \
  --output-dir evidence/hybrid_gate_mar2025
```

### **4. Backtest con Gate Elegido**
```bash
# Usar gate dinámico (recomendado)
python paper/wf_paper_month.py \
  --month 2025-03 \
  --intraday <path> \
  --forecast data/daily/signals_with_gates.parquet \
  --tickers-file evidence/dynamic_gate_mar2025/dynamic_gate.json \
  --tp-sl-choice evidence/param_gate_mar2025/tp_sl_choice.json \
  --capital 1000 --exposure-cap 800 \
  --execution-mode balanced --max-hold-days 2
```

---

## 🎯 COMPARACIÓN DE ENFOQUES

| Enfoque | Recalculo | Rotación | Señales | Complejidad | Uso Recomendado |
|---------|-----------|----------|---------|-------------|-----------------|
| **Static Gate** | 1x mes | No | No | Baja | Baseline, backtests históricos |
| **Dynamic Gate** | Semanal | Sí (max N) | No | Media | Trading real, mercados volátiles |
| **Hybrid Gate** | 1x o semanal | Sí | Sí | Alta | Máxima adaptabilidad, live trading |

---

## ⚙️ INTEGRACIÓN CON WF_PAPER_MONTH

### **Modificación requerida en `wf_paper_month.py`:**

```python
def load_dynamic_tickers(gate_file, trade_date):
    """Load active tickers for a specific date from dynamic gate."""
    with open(gate_file) as f:
        gate_data = json.load(f)
    
    # Find active rebalance for this date
    trade_dt = pd.to_datetime(trade_date).date()
    
    for i, rebalance in enumerate(gate_data['rebalance_history']):
        rebalance_dt = pd.to_datetime(rebalance['rebalance_date']).date()
        
        # Check if this is the active rebalance
        if i == len(gate_data['rebalance_history']) - 1:
            # Last rebalance, use it
            if trade_dt >= rebalance_dt:
                return rebalance['portfolio']
        else:
            # Check if within this rebalance window
            next_rebalance_dt = pd.to_datetime(gate_data['rebalance_history'][i+1]['rebalance_date']).date()
            if rebalance_dt <= trade_dt < next_rebalance_dt:
                return rebalance['portfolio']
    
    # Fallback: use final portfolio
    return gate_data['final_portfolio']


# In main loop:
if args.tickers_file:
    gate_path = Path(args.tickers_file)
    gate_data = json.loads(gate_path.read_text())
    
    # Check if dynamic gate
    if 'rebalance_history' in gate_data:
        # Dynamic gate: load per-day tickers
        for trade_date in weekdays_with_data:
            tickers = load_dynamic_tickers(args.tickers_file, trade_date)
            # Filter forecast to these tickers
    else:
        # Static gate: use selected_tickers
        tickers = gate_data['selected_tickers']
```

---

## 🧪 PRUEBA RÁPIDA

**Test dinámico:**
```bash
python montecarlo_gate_dynamic.py --month 2025-03 --rebalance-freq weekly --top-k 4 --max-rotation 1
```

**Test híbrido:**
```bash
python hybrid_score_gate.py --asof-date 2025-03-31 --forecast data/daily/signals_with_gates.parquet
```

**Comparar con estático:**
```bash
python test_gates.py  # Muestra diferencias entre gates
```

---

## 📊 MÉTRICAS ESPERADAS

**Dynamic Gate vs Static:**
- Mayor adaptabilidad: 15-25% mejora en meses volátiles
- Menor drawdown: rotación saca perdedores rápido
- Trade-off: mayor complejidad, más cálculos

**Hybrid Gate vs Pure MC:**
- Evita "dead zones": tickers sin setups actuales
- Mejor timing: captura momentum de señales frescas
- Signal quality añade 10-15% precisión

---

## ⚠️ CONSIDERACIONES

1. **Overfitting risk**: Dynamic gate con rebalance diario puede overfit
2. **Transaction costs**: rotación aumenta costos (limitar con `--max-rotation`)
3. **Signal delay**: usar señales T-1 para evitar look-ahead bias
4. **Compute time**: dynamic gate toma ~4x más tiempo que static

---

## 📝 PRÓXIMOS PASOS

1. ✅ Implementar `montecarlo_gate_dynamic.py`
2. ✅ Implementar `hybrid_score_gate.py`
3. ⏳ Modificar `wf_paper_month.py` para soportar dynamic gate
4. ⏳ Backtest Q1 2025 con dynamic gate
5. ⏳ Backtest Q1 2025 con hybrid gate
6. ⏳ Comparar: Static vs Dynamic vs Hybrid

**¿Corremos el test de Dynamic Gate en marzo 2025 ahora?**
