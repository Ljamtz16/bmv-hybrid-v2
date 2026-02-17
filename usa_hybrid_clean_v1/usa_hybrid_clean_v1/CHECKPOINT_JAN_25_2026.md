# CHECKPOINT - Sistema de Backtest con Múltiples Umbrales Prob_Win
**Fecha:** 25 de Enero de 2026
**Estado:** Funcional y validado

---

## 📋 RESUMEN EJECUTIVO

Se ha implementado y validado un sistema completo de backtesting semanal con capacidad de probar múltiples umbrales de probabilidad de ganancia (prob_win). El sistema permite ejecutar 105 semanas de backtests (2024-2025) con diferentes configuraciones de capital y umbrales para encontrar la configuración óptima.

**Resultado Principal (Threshold 0.55):**
- Return promedio: **+1.21%/semana** (+62.9% anualizado)
- Win rate: **60.9%**
- Semanas positivas: **89/105 (84.8%)**
- Total trades: **1,127**
- Total PnL: **+$2,486**
- Capital: $2,000 | Max Deploy: $1,900 | Per Trade: $500

---

## 🛠️ CONFIGURACIÓN ACTUAL DEL SISTEMA

### Parámetros de Capital
```python
CAPITAL = 2000              # Capital inicial
MAX_POSITIONS = 4           # Máximo 4 posiciones simultáneas
MAX_DEPLOY = 1900          # Máximo $1900 desplegados
PER_TRADE_CASH = 500       # Máximo $500 por operación
```

### Parámetros de Estrategia
```python
TP_PCT = 1.6%              # Take Profit
SL_PCT = 1.0%              # Stop Loss
MAX_HOLD_DAYS = 2          # Máximo 2 días holding
SLIPPAGE_PCT = 0.01%       # Slippage
```

### Universo de Trading
- **Tickers disponibles:** 18 US equities (intraday 15-min)
- **Forecast universe:** 5 tickers (AAPL, GS, IWM, JPM, MS)
- **Periodo de prueba:** 2024-01-01 a 2025-12-31 (105 semanas)

---

## 🔄 EVOLUCIÓN DEL TRABAJO

### 1. **Configuración Inicial**
- Sistema funcionando con capital $1,000
- Max deploy $900
- Per trade $225
- Threshold prob_win 0.55 fijo

### 2. **Upgrade a Capital $2,000**
**Cambios implementados:**
```python
# backtest_comparative_modes.py líneas 28-31
CAPITAL = 2000              # Era 1000
MAX_DEPLOY = 1900          # Era 900
PER_TRADE_CASH = 500       # Era 225
```

**Ejecución:**
```bash
backtest_weekly.py
```
**Resultado:** 105 semanas ejecutadas exitosamente con nuevo capital

### 3. **Sistema de Múltiples Umbrales**
**Objetivo:** Encontrar el umbral óptimo de prob_win probando diferentes valores

**Scripts creados:**

#### a) `backtest_weekly.py` (Modificado)
- Acepta parámetro `--pw_threshold`
- Acepta parámetro `--output_base`
- Ejecuta 105 semanas individuales
- Genera `weekly_summary.json` y `weekly_summary.csv`

**Uso:**
```bash
python backtest_weekly.py --pw_threshold 0.55 --output_base evidence/probwin_tests/pw_55
```

#### b) `test_single_threshold.py`
- Wrapper simple para ejecutar un umbral específico
- Muestra resultados al finalizar

**Uso:**
```bash
python test_single_threshold.py 0.55
```

#### c) `run_all_probwin_tests.ps1`
- Script PowerShell para ejecutar todos los umbrales secuencialmente
- Maneja 7 umbrales: 0.50, 0.52, 0.55, 0.58, 0.60, 0.65, 0.70

#### d) `compare_probwin_results.py`
- Compara resultados de todos los umbrales
- Genera ranking por performance
- Identifica umbral óptimo

**Uso:**
```bash
python compare_probwin_results.py
```

#### e) `consolidate_weekly_results.py`
- Consolida todas las semanas en archivos únicos
- Genera `ALL_TRADES_2024_2025.csv`
- Genera `METRICS_TABLE_2024_2025.csv`
- Genera `ALL_METRICS_2024_2025.json`

---

## 🐛 PROBLEMAS RESUELTOS

### Problema 1: Encoding de Emojis
**Error:**
```
UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f4ca'
```

**Causa:** Emojis en `backtest_comparative_modes.py` (📊, 💰, 📈, 🎯) no compatibles con Windows terminal encoding

**Solución:**
```python
# backtest_comparative_modes.py - Reemplazados emojis por texto
print(f"📊 RESULTS: {mode.upper()}")  # ANTES
print(f"RESULTS: {mode.upper()}")     # DESPUÉS

print(f"\n💰 P&L:")    # ANTES
print(f"\nP&L:")       # DESPUÉS

# Similar para 📈, 🎯
```

**Ubicaciones corregidas:**
- Línea 530: Título de resultados
- Línea 557: Sección P&L
- Línea 562: Sección Performance
- Línea 568: Sección Exits
- Línea 577: Sección Per-Ticker
- Línea 586: Sección Prob_Win Calibration

### Problema 2: Encoding en backtest_weekly.py
**Error:** Emojis ✅ ❌ causando errores

**Solución:**
```python
# backtest_weekly.py
print(f"✅ {metrics.get('return_pct', 0):.1f}%")  # ANTES
print(f"[OK] {metrics.get('return_pct', 0):.1f}%")  # DESPUÉS

print("❌ No metrics file")  # ANTES
print("[X] No metrics file")  # DESPUÉS
```

**Adicional:** Agregado encoding UTF-8 en subprocess.run:
```python
result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    timeout=120,
    encoding='utf-8',      # Agregado
    errors='replace'       # Agregado
)
```

### Problema 3: Mensajes de Error Truncados
**Solución:** Mejorado el logging de errores en backtest_weekly.py
```python
# ANTES
print(f"[X] Error: {result.stderr[:50]}")

# DESPUÉS
print(f"[X] Error code {result.returncode}")
if result.stderr:
    print(f"    STDERR: {result.stderr[:200]}")
if result.stdout:
    print(f"    STDOUT: {result.stdout[:200]}")
```

---

## 📂 ESTRUCTURA DE ARCHIVOS

```
project/
├── backtest_comparative_modes.py     # Motor principal (MODIFICADO: emojis, capital)
├── backtest_weekly.py                # Ejecutor semanal (MODIFICADO: args, encoding)
│
├── test_single_threshold.py          # [NUEVO] Test individual
├── run_all_probwin_tests.ps1         # [NUEVO] Batch execution
├── compare_probwin_results.py        # [NUEVO] Comparación de resultados
├── consolidate_weekly_results.py     # [NUEVO] Consolidador de datos
├── show_consolidated_summary.py      # [NUEVO] Mostrar resumen
│
├── evidence/
│   ├── weekly_analysis/              # Resultados threshold 0.55 (105 semanas)
│   │   ├── 2024_W01/ ... 2025_W105/
│   │   ├── weekly_summary.csv
│   │   ├── weekly_summary.json
│   │   └── consolidated/
│   │       ├── ALL_TRADES_2024_2025.csv        (1,127 trades)
│   │       ├── METRICS_TABLE_2024_2025.csv     (105 semanas)
│   │       └── ALL_METRICS_2024_2025.json
│   │
│   └── probwin_tests/                # [NUEVO] Tests múltiples umbrales
│       ├── pw_50/                    # (Por ejecutar)
│       ├── pw_52/                    # (Por ejecutar)
│       ├── pw_55/                    # (Copiar de weekly_analysis)
│       ├── pw_58/                    # (Por ejecutar)
│       ├── pw_60/                    # (Por ejecutar)
│       └── pw_65/                    # (Por ejecutar)
```

---

## 📊 RESULTADOS OBTENIDOS

### Backtest Completo - Threshold 0.55

#### Métricas Globales (2024-2025)
```
Total semanas:          105
Semanas positivas:      89 (84.8%)
Semanas negativas:      16 (15.2%)
Semanas sin trades:     0 (0%)

Return promedio:        +1.21%/semana
Return total:           +126.67%
Return anualizado:      +62.9%
Std dev:                1.38%

Total trades:           1,127
Avg trades/semana:      10.7
Win rate promedio:      60.9%
Profit factor promedio: 294.97x

Total PnL:              +$2,486.34
```

#### Mejores/Peores Semanas
```
Mejor semana:   2025_W89  +5.05%
Peor semana:    2025_W54  -1.95%

Top 5 Semanas:
1. 2025_W89: +5.05% (15 trades, WR 73.3%)
2. 2024_W12: +4.05% (15 trades, WR 80.0%)
3. 2024_W38: +4.19% (24 trades, WR 70.8%)
4. 2024_W32: +3.99% (18 trades, WR 72.2%)
5. 2025_W100: +3.84% (15 trades, WR 73.3%)
```

#### Distribución por Año
```
2024:
  Semanas:        53
  Avg Return:     +1.13%/semana
  Total Trades:   574
  
2025:
  Semanas:        52
  Avg Return:     +1.29%/semana
  Total Trades:   553
```

---

## 🚀 PRÓXIMOS PASOS

### 1. Completar Pruebas de Umbrales
Ejecutar backtests para umbrales pendientes:

```bash
# Threshold 0.50 (más liberal)
./.venv/Scripts/python.exe backtest_weekly.py --pw_threshold 0.50 --output_base evidence/probwin_tests/pw_50

# Threshold 0.52
./.venv/Scripts/python.exe backtest_weekly.py --pw_threshold 0.52 --output_base evidence/probwin_tests/pw_52

# Threshold 0.58
./.venv/Scripts/python.exe backtest_weekly.py --pw_threshold 0.58 --output_base evidence/probwin_tests/pw_58

# Threshold 0.60
./.venv/Scripts/python.exe backtest_weekly.py --pw_threshold 0.60 --output_base evidence/probwin_tests/pw_60

# Threshold 0.65 (más conservador)
./.venv/Scripts/python.exe backtest_weekly.py --pw_threshold 0.65 --output_base evidence/probwin_tests/pw_65
```

**Tiempo estimado:** ~15 minutos por umbral = ~75 minutos total

### 2. Análisis Comparativo
Una vez completados todos los umbrales:

```bash
python compare_probwin_results.py
```

Esto generará:
- Ranking por retorno promedio
- Análisis de trade-off (trades vs win rate)
- Identificación de umbral óptimo
- Archivo CSV con comparación completa

### 3. Validación Temporal
Analizar si el umbral óptimo es consistente en diferentes periodos:
- Q1 2024 vs Q1 2025
- Meses alcistas vs bajistas
- Alta vs baja volatilidad

### 4. Optimización de Capital
Una vez identificado el umbral óptimo, probar diferentes configuraciones de capital:
- $2,500 / $2,375 max deploy / $593 per trade
- $3,000 / $2,850 max deploy / $712 per trade
- $5,000 / $4,750 max deploy / $1,187 per trade

---

## 📝 COMANDOS DE REFERENCIA RÁPIDA

### Ejecutar Backtest Semanal
```bash
python backtest_weekly.py --pw_threshold 0.55 --output_base evidence/probwin_tests/pw_55
```

### Probar Un Solo Umbral
```bash
python test_single_threshold.py 0.55
```

### Ejecutar Todos los Umbrales
```powershell
.\run_all_probwin_tests.ps1
```

### Comparar Resultados
```bash
python compare_probwin_results.py
```

### Consolidar Semanas
```bash
python consolidate_weekly_results.py
```

### Mostrar Resumen
```bash
python show_consolidated_summary.py
```

### Ver Resultados de Threshold Específico
```bash
python -c "import json; data=json.load(open('evidence/probwin_tests/pw_55/weekly_summary.json')); print(f'Return: {data[\"overall_avg_return\"]}%, Trades: {data[\"overall_total_trades\"]}, WR: {data[\"overall_avg_win_rate\"]:.1%}')"
```

---

## 🔧 ARCHIVOS MODIFICADOS

### 1. `backtest_comparative_modes.py`
**Líneas modificadas:**
- 28-31: Capital de $1,000 → $2,000, max deploy $900 → $1,900, per trade $225 → $500
- 530, 557, 562, 568, 577, 586: Eliminación de emojis Unicode

### 2. `backtest_weekly.py`
**Cambios:**
- Líneas 1-20: Agregado argparse para `--pw_threshold` y `--output_base`
- Línea 60: Uso de `PW_THRESHOLD` variable en lugar de hardcoded 0.55
- Líneas 74-80: Agregado encoding='utf-8' en subprocess.run
- Líneas 103, 105, 107, 109: Reemplazo de emojis ✅ ❌ por [OK] [X]
- Líneas 200, 231: Paths dinámicos usando OUTPUT_BASE
- Línea 208: Guardar PW_THRESHOLD en summary JSON

---

## 📊 ARCHIVOS DE DATOS GENERADOS

### Principales
1. **`evidence/weekly_analysis/weekly_summary.json`**
   - Resumen ejecutivo de 105 semanas
   - Métricas agregadas
   - Mejor/peor semana
   
2. **`evidence/weekly_analysis/weekly_summary.csv`**
   - Tabla con todas las semanas
   - Formato tabular para análisis

3. **`evidence/weekly_analysis/consolidated/ALL_TRADES_2024_2025.csv`**
   - 1,127 operaciones individuales
   - Incluye columna 'week' para filtrado

4. **`evidence/weekly_analysis/consolidated/METRICS_TABLE_2024_2025.csv`**
   - Métricas por semana en formato tabla
   - 105 filas × 11 columnas

### Estructura de Semana Individual
Cada directorio `evidence/weekly_analysis/YYYY_WWW/` contiene:
- `metrics.json` - Métricas de la semana
- `trades.csv` - Operaciones de la semana

---

## ⚙️ CONFIGURACIÓN DE ENTORNO

### Python
```
Python 3.12
.venv (virtual environment)
```

### Dependencias Principales
```python
pandas
numpy
json
argparse
pathlib
datetime
subprocess
```

### Encoding
```
PYTHONIOENCODING=utf-8  # Variable de entorno configurada
```

---

## 🎯 OBJETIVO FINAL

**Encontrar la configuración óptima de:**
1. **Umbral prob_win** (0.50 - 0.70)
2. **Capital deployment** (ya optimizado a $2,000)
3. **Validar consistencia temporal** (2024 vs 2025)

**Meta de rendimiento:**
- Return > +1.0%/semana sostenible
- Win rate > 58%
- Semanas positivas > 80%
- Drawdown máximo < -5% semanal

---

## 📞 SOPORTE

**Scripts de diagnóstico:**
- `check_progress.ps1` - Ver progreso general
- `show_consolidated_summary.py` - Resumen rápido
- `compare_probwin_results.py` - Comparación detallada

**Logs:**
- `weekly_analysis.log` - Log de ejecución semanal
- `probwin_threshold_tests.log` - Log de pruebas de umbrales

---

## ✅ CHECKLIST DE VALIDACIÓN

- [x] Sistema funciona con capital $2,000
- [x] Backtest completo 105 semanas ejecutado (threshold 0.55)
- [x] Resultados consolidados generados
- [x] Encoding issues resueltos
- [x] Scripts de comparación creados
- [ ] Pruebas de umbrales 0.50, 0.52, 0.58, 0.60, 0.65 pendientes
- [ ] Análisis comparativo final pendiente
- [ ] Selección de umbral óptimo pendiente
- [ ] Validación temporal pendiente

---

**Última actualización:** 25 de Enero de 2026
**Autor:** GitHub Copilot
**Versión:** 2.0 - Sistema Multi-Threshold con Capital $2K
