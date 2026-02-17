# Script: 19_build_ticker_universe_manual.py
# Construye universo con lista manual curada + filtro de liquidez
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os

# Lista curada de tickers líquidos por sector
CURATED_TICKERS = {
    'Technology': [
        'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'AMZN', 'TSLA', 'AMD', 'INTC', 'CRM',
        'ORCL', 'AVGO', 'ADBE', 'CSCO', 'QCOM', 'TXN', 'NOW', 'INTU', 'AMAT', 'MU'
    ],
    'Financials': [
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW', 'AXP', 'USB',
        'PNC', 'TFC', 'COF', 'BK', 'STT'
    ],
    'Health Care': [
        'UNH', 'JNJ', 'LLY', 'ABBV', 'MRK', 'PFE', 'TMO', 'ABT', 'DHR', 'BMY',
        'AMGN', 'GILD', 'CVS', 'CI', 'MDT'
    ],
    'Consumer Discretionary': [
        'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'TGT', 'LOW', 'TJX', 'BKNG', 'MAR',
        'GM', 'F', 'EBAY', 'ROST', 'YUM'
    ],
    'Consumer Staples': [
        'WMT', 'PG', 'KO', 'PEP', 'COST', 'PM', 'MDLZ', 'MO', 'CL', 'KMB',
        'GIS', 'SYY', 'HSY', 'K', 'CPB'
    ],
    'Energy': [
        'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'PXD', 'MPC', 'PSX', 'VLO', 'HES',
        'OXY', 'HAL', 'BKR', 'DVN', 'FANG'
    ],
    'Industrials': [
        'CAT', 'BA', 'HON', 'UPS', 'RTX', 'DE', 'LMT', 'GE', 'MMM', 'UNP',
        'FDX', 'NSC', 'CSX', 'GD', 'NOC'
    ],
    'Materials': [
        'LIN', 'APD', 'SHW', 'FCX', 'NEM', 'ECL', 'DD', 'DOW', 'NUE', 'VMC'
    ],
    'Utilities': [
        'NEE', 'DUK', 'SO', 'D', 'AEP', 'EXC', 'SRE', 'XEL', 'WEC', 'ES'
    ],
    'Communication Services': [
        'GOOGL', 'META', 'DIS', 'NFLX', 'CMCSA', 'VZ', 'T', 'TMUS', 'CHTR', 'EA'
    ],
    'Real Estate': [
        'AMT', 'PLD', 'CCI', 'EQIX', 'PSA', 'SPG', 'DLR', 'O', 'WELL', 'AVB'
    ],
    'ETF': [
        'SPY', 'QQQ', 'IWM', 'DIA', 'XLF', 'XLE', 'XLK', 'XLV', 'XLP', 'XLI',
        'XLU', 'XLB', 'XLRE', 'XLC', 'VTI', 'VOO', 'VEA', 'VWO', 'AGG', 'BND'
    ]
}

def validate_liquidity(ticker, min_volume=1_000_000, min_price=5, lookback_days=60):
    """Valida liquidez de un ticker"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)
        
        data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        if len(data) < 20:
            return None
        
        avg_volume = data['Volume'].mean()
        avg_price = data['Close'].mean()
        
        if avg_volume >= min_volume and avg_price >= min_price:
            return {
                'avg_volume': avg_volume,
                'avg_price': avg_price,
                'data_points': len(data)
            }
        
        return None
        
    except Exception:
        return None

def build_universe(min_volume=1_000_000, min_price=5, max_tickers=100):
    """Construye universo validado"""
    print("="*60)
    print(f"CONSTRUYENDO UNIVERSO (Target: {max_tickers} tickers)")
    print("="*60)
    
    all_tickers = []
    
    for sector, tickers in CURATED_TICKERS.items():
        print(f"\n[INFO] Procesando {sector}...")
        sector_valid = 0
        
        for ticker in tickers:
            liquidity = validate_liquidity(ticker, min_volume, min_price)
            
            if liquidity:
                all_tickers.append({
                    'ticker': ticker,
                    'sector': sector,
                    'avg_volume': liquidity['avg_volume'],
                    'avg_price': liquidity['avg_price'],
                    'data_points': liquidity['data_points']
                })
                sector_valid += 1
        
        print(f"  ✓ {sector_valid}/{len(tickers)} tickers válidos")
    
    df = pd.DataFrame(all_tickers)
    
    # Deduplicar (algunos tickers en múltiples categorías)
    df = df.drop_duplicates(subset=['ticker']).reset_index(drop=True)
    
    # Ordenar por volumen y limitar
    df = df.sort_values('avg_volume', ascending=False)
    
    if len(df) > max_tickers:
        df = df.head(max_tickers)
    
    return df

def main():
    output_dir = 'data/us/'
    os.makedirs(output_dir, exist_ok=True)
    
    # Construir universo
    universe = build_universe(min_volume=1_000_000, min_price=5, max_tickers=100)
    
    print(f"\n{'='*60}")
    print(f"UNIVERSO FINAL: {len(universe)} TICKERS")
    print(f"{'='*60}")
    
    # Resumen por sector
    print("\nDistribución por sector:")
    sector_counts = universe['sector'].value_counts()
    for sector, count in sector_counts.items():
        print(f"  {sector:30s}: {count:3d} tickers")
    
    print(f"\nVolumen promedio: {universe['avg_volume'].mean():,.0f}")
    print(f"Precio promedio:  ${universe['avg_price'].mean():.2f}")
    
    # Guardar
    output_path = os.path.join(output_dir, 'tickers_universe_expanded.csv')
    universe.to_csv(output_path, index=False)
    print(f"\n[OK] Guardado en: {output_path}")
    
    # Versión simple
    simple_path = os.path.join(output_dir, 'tickers_expanded.csv')
    universe[['ticker', 'sector']].to_csv(simple_path, index=False)
    print(f"[OK] Versión simple: {simple_path}")
    
    return universe

if __name__ == "__main__":
    universe = main()
