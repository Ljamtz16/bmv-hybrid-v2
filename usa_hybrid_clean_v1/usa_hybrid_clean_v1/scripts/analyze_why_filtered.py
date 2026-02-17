"""
Analiza por qué los tickers no pasan filtros
"""
import pandas as pd
from pathlib import Path
import numpy as np

dates = ['2025-10-16', '2025-10-17', '2025-10-22', '2025-10-31']

print("="*80)
print("ANÁLISIS DE FILTROS - ¿POR QUÉ SOLO AMD Y TSLA?")
print("="*80)

for d in dates:
    print(f"\n{'='*80}")
    print(f"FECHA: {d}")
    print(f"{'='*80}")
    
    # Cargar after_model (antes de filtros)
    before_path = Path(f'reports/intraday/{d}/forecast_after_model.parquet')
    after_path = Path(f'reports/intraday/{d}/forecast_after_filters.parquet')
    
    if not before_path.exists():
        print(f"  ⚠️  No existe forecast_after_model.parquet")
        continue
    
    df_before = pd.read_parquet(before_path)
    df_after = pd.read_parquet(after_path) if after_path.exists() else pd.DataFrame()
    
    print(f"\n📊 Señales ANTES de filtros: {len(df_before)}")
    if len(df_before) > 0:
        print(f"   Tickers: {df_before['ticker'].unique().tolist()}")
        
        # Analizar por ticker
        for ticker in df_before['ticker'].unique():
            ticker_df = df_before[df_before['ticker'] == ticker]
            passed = ticker in df_after['ticker'].unique() if len(df_after) > 0 else False
            
            print(f"\n  {'✅' if passed else '❌'} {ticker}:")
            
            # Spread
            if 'spread_bps' in ticker_df.columns:
                spread = ticker_df['spread_bps'].iloc[0]
                print(f"     Spread: {spread:.2f} bps (límites: 50/70/90 bps)")
            
            # ATR
            if 'ATR_pct' in ticker_df.columns:
                atr = ticker_df['ATR_pct'].iloc[0]
                print(f"     ATR: {atr:.4f} ({atr*100:.2f}%) (límites: 0.4%-2.5%)")
            
            # Volume ratio
            if 'volume_ratio' in ticker_df.columns:
                vol_ratio = ticker_df['volume_ratio'].iloc[0]
                print(f"     Volume ratio: {vol_ratio:.2f} (límite: >= P40)")
            
            # Prob win
            if 'prob_win' in ticker_df.columns:
                prob = ticker_df['prob_win'].iloc[0]
                print(f"     Prob win: {prob:.3f} ({prob*100:.1f}%) (límite: >= 25%)")
            
            # Direction
            if 'direction' in ticker_df.columns:
                direction = ticker_df['direction'].iloc[0]
                print(f"     Direction: {direction}")
    
    print(f"\n📊 Señales DESPUÉS de filtros: {len(df_after)}")
    if len(df_after) > 0:
        print(f"   Tickers: {df_after['ticker'].unique().tolist()}")

print(f"\n{'='*80}")
print("RESUMEN DEL PROBLEMA")
print(f"{'='*80}")
print("""
🔍 Hallazgos:

1. **Whitelist activa:** 11 tickers configurados
   ["AMD", "NVDA", "TSLA", "MSFT", "AAPL", "AMZN", "META", "GOOG", "NFLX", "JPM", "XOM"]

2. **Problema principal: SPREAD FILTER**
   - Límites: 50/70/90 bps según hora y volatilidad
   - Spreads reales (high-low): 50-112 bps
   - Resultado: Solo AMD y TSLA (ocasionalmente) pasan

3. **Otros tickers filtrados:**
   - NVDA: Spreads ~110 bps (demasiado alto)
   - MSFT/AAPL/AMZN: Probablemente sin datos o spreads altos
   - Resto: Sin señales del modelo

💡 Soluciones:

A) **Relajar spread caps** (conserva filosofía actual):
   spread_base_bps: 50 → 100 bps
   spread_late_bps: 70 → 120 bps
   spread_high_vol_bps: 90 → 150 bps

B) **Remover filtro de spread** (más agresivo):
   Comentar o eliminar filtro de spread en script 11

C) **Ajustar cálculo de spread**:
   Usar bid-ask real en vez de high-low si disponible

D) **Ampliar whitelist**:
   Agregar más tickers líquidos de diferentes sectores
""")
