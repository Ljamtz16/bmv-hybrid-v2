# 📊 INTRADAY TRADING SYSTEM

Sistema de trading intradía con horizonte de 1 día (cierre forzado EOD).

## 📁 Estructura

```
intraday/
├── config/
│   └── intraday.yaml          # Configuración Intraday 2.0
├── scripts/
│   ├── 09_make_targets_intraday.py      # Generar targets TP/SL
│   ├── 10_train_intraday_brf.py         # Entrenar modelo BRF
│   ├── 11_infer_and_gate_intraday.py    # Predicción + filtros
│   ├── 39_predict_tth_intraday.py       # Monte Carlo TTH
│   ├── 40_make_trade_plan_intraday.py   # Plan de trades
│   ├── validate_intraday_2_0.py         # Validación con datos reales
│   └── generate_intraday_2_0_report.py  # Reportes
├── models/
│   └── clf_intraday_brf_calibrated.joblib  # Modelo reentrenado ✅
├── data/
│   ├── raw/                   # OHLCV 15m (data/intraday)
│   └── features/              # Features procesadas (parquet)
└── reports/
    └── runs/                  # Reportes por fecha (2025-XX-XX/)
```

## ⚙️ Configuración Actual (Intraday 2.0)

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| **TP** | 1.2% | Take Profit (realista para 15m) |
| **SL** | 0.35% | Stop Loss |
| **R:R** | 3.4:1 | Risk-Reward ratio |
| **Capital** | $300/trade | Capital por operación |
| **Max Capital** | $900 | Capital total máximo |
| **Trades/día** | 1-2 | Objetivo conservador |
| **Filtros** | prob_win ≥ 8%, P(TP<SL) ≥ 15%, ETTH ≤ 0.28d | |

## 🚀 Pipeline Diario

```bash
# 1. Generar predicciones y filtrar señales
python intraday/scripts/11_infer_and_gate_intraday.py --date 2025-11-04 --prob-min 0.08

# 2. Predecir TTH con Monte Carlo
python intraday/scripts/39_predict_tth_intraday.py --date 2025-11-04

# 3. Crear plan de trades
python intraday/scripts/40_make_trade_plan_intraday.py --date 2025-11-04 \
    --tp-pct 0.012 --sl-pct 0.0035 --per-trade-cash 300 --capital-max 900
```

## 🔄 Re-entrenamiento

```bash
# 1. Re-generar targets con nuevos TP/SL
python intraday/scripts/09_make_targets_intraday.py \
    --start 2025-09-01 --end 2025-10-31 \
    --tp-pct 0.012 --sl-pct 0.0035 --horizon-bars 26

# 2. Re-entrenar modelo
python intraday/scripts/10_train_intraday_brf.py \
    --start 2025-09-01 --end 2025-10-31 \
    --features-dir intraday/data/features \
    --models-dir intraday/models --use-smote
```

## ✅ Validación Oct 28, 2025

**Modelo reentrenado:**
- ✅ TP hit en 60 minutos
- PnL: **+$2.40** (+1.2%)
- Prob win: 100% (calibrado correctamente)

**Modelo anterior (TP=2.8%):**
- ❌ SL hit en 15 minutos
- PnL: -$0.70 a -$1.60

## 📊 Métricas del Modelo

| Métrica | Valor |
|---------|-------|
| ROC-AUC | 0.9568 |
| PR-AUC | 0.5074 |
| Brier Score | 0.0248 |
| P@20 | 65.0% |
| Win Rate Train | 2.26% |
| Win Rate Val | 2.58% |

## 🎯 Diferencias vs Multidía

| Característica | Intraday | Multidía (H3) |
|----------------|----------|---------------|
| Horizonte | Mismo día (EOD) | 3 días máximo |
| Intervalo | 15 minutos | Diario EOD |
| TP | 1.2% | 3-5% |
| SL | 0.35% | 1.5-2% |
| Trades/día | 1-2 | Variable |
| Modelo | clf_intraday_brf_calibrated.joblib | prob_win_clean.joblib |
| Cierre | Forzado 15:55 ET | Hold overnight |

## 📝 Notas

- Modelo **reentrenado** (Nov 4, 2025) con targets TP=1.2%, SL=0.35%
- Whitelist: 11 tickers líquidos (AMD, NVDA, TSLA, MSFT, AAPL, AMZN, META, GOOG, NFLX, JPM, XOM)
- Spread adaptativo: 50-90 bps según volatilidad
- Monte Carlo: 500 sims, 26 steps/día (6.5h mercado)
