# DEFINICIÓN ÚNICA: ¿QUÉ ES "OPERABLE"?

## DEFINICIÓN OFICIAL

Una señal es **OPERABLE** si cumple TODAS las siguientes condiciones:

```python
OPERABLE = (
    (confidence_score >= 4) AND
    (macro_risk <= "MEDIUM") AND
    (ticker IN ["CVX", "XOM", "WMT", "MSFT", "SPY"])
)
```

### Desglose

1. **Conf >= 4**
   - Valor: 4 o 5 (de 5 total)
   - Razón: Reglas de confianza automáticas deben cumplirse

2. **Risk <= MEDIUM**
   - Válido: "LOW" o "MEDIUM"
   - Inválido: "HIGH" o "CRITICAL"
   - Razón: No operar en días de alto riesgo macro (FOMC, etc)

3. **Ticker en Whitelist**
   - MAE < 5% en histórico
   - Tickers: CVX, XOM, WMT, MSFT, SPY
   - Razón: Modelos probados y confiables

---

## Implementaciones Correctas

### ✅ `production_orchestrator.py` (REFERENCIA)

```python
def filter_operable_signals(df: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
    """GATE: Filtrar solo señales operables"""
    
    # Risk
    df["macro_risk"] = df["date"].apply(get_macro_risk_level)
    risk_ok = df["macro_risk"].isin(["LOW", "MEDIUM"])
    
    # Confidence
    conf_ok = df["confidence_score"] >= CONF_THRESHOLD  # 4
    
    # Ticker
    ticker_ok = df["ticker"].isin(WHITELIST_TICKERS)  # CVX, XOM, WMT, MSFT, SPY
    
    operable = df[risk_ok & conf_ok & ticker_ok].copy()
    return operable
```

**Usar ESTE como referencia para todos los scripts**

---

## Implementaciones que Necesitan Correción

### ⚠️ `enhanced_metrics_reporter.py`

```python
# INCORRECTO (falta columna exacta):
operable = df[
    (df["confidence_score"] >= 4) &
    (df["risk_level"] != "HIGH") &          # ← Debería usar macro_risk
    (df["ticker"].isin(WHITELIST_TICKERS))
]

# CORRECTO:
df["macro_risk"] = df["date"].apply(calculate_risk_level)
operable = df[
    (df["confidence_score"] >= 4) &
    (df["macro_risk"].isin(["LOW", "MEDIUM"])) &
    (df["ticker"].isin(WHITELIST_TICKERS))
]
```

### ⚠️ `backtest_confidence_rules.py`

```python
# INCORRECTO (falta Risk + Whitelist):
df_backtest["operable"] = (df_backtest["confidence_score"] >= confidence_threshold) & \
                          (df_backtest["trading_signal"].isin(["BUY", "SELL"]))

# CORRECTO:
df_backtest["macro_risk"] = df_backtest["date"].apply(calculate_risk_level)
df_backtest["operable"] = (
    (df_backtest["confidence_score"] >= confidence_threshold) &
    (df_backtest["macro_risk"].isin(["LOW", "MEDIUM"])) &
    (df_backtest["ticker"].isin(WHITELIST_TICKERS))
)
```

---

## Verificación: Cuándo Hayás Dudas

Si ves "aparentes contradicciones" entre análisis:

1. **Verifica la definición de "operable"**
   - ¿Tiene los 3 filtros?
   - ¿Usa las mismas constantes?

2. **Imprime los datos filtrados**
   ```python
   print(f"Conf>=4: {len(df[df['confidence_score']>=4])}")
   print(f"+ Risk<=MEDIUM: {len(df[(df['confidence_score']>=4) & (df['macro_risk'].isin(['LOW','MEDIUM']))])}")
   print(f"+ Whitelist: {len(df[(df['confidence_score']>=4) & (df['macro_risk'].isin(['LOW','MEDIUM'])) & (df['ticker'].isin(WHITELIST))])}")
   ```

3. **Compara LINEALMENTE**
   ```
   Global:        26,634 observaciones
   Conf>=4:       3,880 observaciones
   + Risk OK:     3,850 observaciones
   + Whitelist:   3,780 observaciones
   ```

---

## Constantes Globales

Todas deben estar sincronizadas:

```python
CONF_THRESHOLD = 4
RISK_THRESHOLD = "MEDIUM"  # Operar si <= MEDIUM
WHITELIST_TICKERS = ["CVX", "XOM", "WMT", "MSFT", "SPY"]
```

---

## Checksum: Cuenta Rápida

Para verificar consistencia rápidamente:

```bash
# Si ves 3,880 operables en producción_orchestrator.py
# Debes ver 3,880 también en enhanced_metrics_reporter.py
# Si ves diferente → hay inconsistencia en los filtros
```

---

## Por Qué Importa

Si defines "operable" de forma inconsistente:

1. **Script A dice**: 5,000 señales operables
2. **Script B dice**: 3,000 señales operables
3. **Conclusión falsa**: "El sistema es contradictorio"
4. **Realidad**: Scripts usando filtros distintos

**Solución**: Siempre usa la definición oficial (3 filtros)

---

## Última Actualización

**Fecha**: 2026-01-13
**Versión**: 1.0 (establecida)
**Responsable**: Kill Switch V2 Improvements

