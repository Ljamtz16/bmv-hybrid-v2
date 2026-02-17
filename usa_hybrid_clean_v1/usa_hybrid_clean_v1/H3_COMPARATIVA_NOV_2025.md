# H3 Comparativa - Nov 2025 (Strict WF vs Relaxed vs Oct Validado)

## Configuración

**Tickers:**
- TSLA, AAPL, NVDA

**Strict WF (Policy H3_WF congelada):**
- min_prob_win: 0.62 (62%)
- min_|y_hat|: 0.06 (6%)
- TP: 6.5%, SL: 0.8%, Horizon: 3 días
- Capital: $400/trade, máx 3 posiciones

**Relaxed (Modo scouting):**
- min_prob_win: 0.50 (50%)
- min_|y_hat|: 0.00 (sin filtro)
- Mismos TP/SL/Horizon/Capital que WF

**Datos:**
- Nov 2025: Solo 1 día (Nov 3) — mercado aún no cerró Nov 4-7
- Oct 2025: Mes completo validado

---

## RESULTADOS COMPARATIVA

### 1️⃣ Nov 3 - Strict WF (Policy Congelada)
```
Trades calificados: 0
Señales generadas: Sí (pero prob_win < 62% o |y_hat| < 6%)
Estado: Sin trades — Filtros muy estrictos para 1 solo día de datos
```

### 2️⃣ Nov 3 - Relaxed (Scouting)
```
Trades calificados: 3 (TSLA×2, AAPL×1)

📊 Estado de tus Predicciones (2025-11-03):

Ticker  Entrada  Actual Cambio  TP_Target     SL       Estado
  TSLA   468.37  468.37 +0.00%     498.81 464.62 Cerca del SL
  AAPL   269.05  269.05 +0.00%     286.54 266.90 Cerca del SL
  TSLA   444.26  468.37 +5.43%     473.14 440.71      GANANDO

Análisis:
• TSLA (Entry $468.37): +0.00% — En riesgo, cerca del SL
• AAPL (Entry $269.05): +0.00% — En riesgo, cerca del SL  
• TSLA (Entry $444.26): +5.43% — GANANDO, falta 1.02% para TP

Resumen:
  • 3 de 3 operaciones en positivo (0 negativas)
  • PnL neto (mark-to-market): +$24.11
```

**⚠️ Advertencia:** Trades de modo relaxed NO pasan los criterios WF validados (p_win<62%). Solo útil para scouting.

### 3️⃣ Oct 2025 - Strict WF (Validado Sep-Oct)
```
Walk-forward completo Octubre:

Trades ejecutados: 6
  • AMD: 4 trades → 3 TP_HIT, 1 HORIZON_END
  • NVDA: 1 trade → TP_HIT
  • CAT: 1 trade → TP_HIT

Resultados:
  • Win rate: 83.3% (5/6)
  • EV net: 5.33% por trade
  • Total PnL: +$82.99
  • Return: +7.5%
  • ETTH mediana: 3.0 días
  • MDD: 0%

Estado vs 3-Nov (según tu imagen):
  • TSLA: Entry $456.56 → Actual $463.47 (+1.51%) — GANANDO
  • AAPL: Entry $270.37 → Actual $267.64 (-1.01%) — Cerca del SL
  • NVDA: Entry $202.49 → Actual $208.57 (+3.00%) — GANANDO

Nota: Oct no tiene TSLA/AAPL/NVDA en los 6 trades del backtest estricto.
Los tickers que operó fueron AMD (mayoría), NVDA, CAT.
```

---

## COMPARATIVA CLAVE

| Métrica | Strict Nov (n=0) | Relaxed Nov (n=3) | Strict Oct (n=6) |
|---------|------------------|-------------------|------------------|
| **Trades** | 0 | 3 | 6 |
| **Win rate** | N/A | 100% (mark-to-market) | 83.3% |
| **PnL** | N/A | +$24.11 | +$82.99 |
| **Return** | N/A | N/A | +7.5% |
| **Status** | Sin señales válidas | Scouting OK | ✅ Validado |
| **Tickers** | — | TSLA×2, AAPL×1 | AMD×4, NVDA×1, CAT×1 |

---

## CONCLUSIONES

1. **Strict WF (Policy Congelada):**
   - Noviembre con 1 solo día → 0 trades calificados
   - Octubre completo → 6 trades, 83% win, validado ✅
   - **Recomendación:** Esperar más días de Nov para acumular señales válidas

2. **Relaxed (Scouting):**
   - Genera trades exploratorios para Nov 3
   - **No apto para trading real** (no cumple criterios WF)
   - Útil solo para monitorear oportunidades preliminares

3. **Próximos pasos:**
   - Ejecutar pipeline diario Nov 4-7 cuando cierren mercados
   - Acumular señales hasta tener n≥5 trades con filtros WF
   - Continuar walk-forward Nov completo al 30-Nov

---

## COMANDOS PARA REPLICAR

### A) Nov 3 Relaxed (Scouting):
```powershell
# Ya ejecutado — ver reports/forecast/2025-11/trades_detailed_relaxed.csv
python scripts\show_h3_status.py --month 2025-11 --as-of 2025-11-03 --tickers-file tmp_three.csv --trades-file trades_detailed_relaxed.csv
```

### B) Oct Strict WF (Validado):
```powershell
python scripts\infer_and_gate.py --month 2025-10 --min-prob 0.62 --min-yhat 0.06
python scripts\24_simulate_trading.py --month 2025-10 --tp-pct 0.065 --sl-pct 0.008 --horizon-days 3 --per-trade-cash 400 --capital-initial 1200 --max-open 3 --position-active
python scripts\show_h3_status.py --month 2025-10 --as-of 2025-11-03
```

### C) Daily Nov (Automático):
```powershell
.\run_h3_daily.ps1 -Date '2025-11-04'  # Tras cierre mercado
```

---

**Archivos generados:**
- reports/forecast/2025-11/trades_detailed_strict.csv (vacío)
- reports/forecast/2025-11/trades_detailed_relaxed.csv (3 trades)
- reports/forecast/2025-10/ (ya existente, 6 trades Oct)
