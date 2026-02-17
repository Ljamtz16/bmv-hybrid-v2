# Script: 19_build_ticker_universe_enhanced.py
# Expande universo a 50-100 tickers líquidos con metadata de sector
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os

def get_sp500_tickers():
    """Descarga lista de S&P 500"""
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        df = tables[0]
        return df[['Symbol', 'Security', 'GICS Sector', 'GICS Sub-Industry']].rename(
            columns={'Symbol': 'ticker', 'Security': 'name', 'GICS Sector': 'sector', 'GICS Sub-Industry': 'subsector'}
        )
    except Exception as e:
        print(f"[WARN] Error descargando S&P 500: {e}")
        return None

def get_nasdaq100_tickers():
    """Descarga lista de Nasdaq 100"""
    try:
        url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
        tables = pd.read_html(url)
        df = tables[4]  # Tabla de componentes
        return df[['Ticker', 'Company', 'GICS Sector', 'GICS Sub-Industry']].rename(
            columns={'Ticker': 'ticker', 'Company': 'name', 'GICS Sector': 'sector', 'GICS Sub-Industry': 'subsector'}
        )
    except Exception as e:
        print(f"[WARN] Error descargando Nasdaq 100: {e}")
        return None

def filter_by_liquidity(tickers, min_volume=1_000_000, min_price=5, lookback_days=60):
    """Filtra tickers por volumen y precio mínimo"""
    print(f"\n[INFO] Filtrando {len(tickers)} tickers por liquidez...")
    print(f"  Criterios: Vol > {min_volume:,}, Price > ${min_price}, Lookback: {lookback_days}d")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)
    
    valid_tickers = []
    
    for idx, row in tickers.iterrows():
        ticker = row['ticker']
        try:
            data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            
            if len(data) < 20:  # Mínimo 20 días de datos
                continue
            
            avg_volume = data['Volume'].mean()
            avg_price = data['Close'].mean()
            
            if avg_volume >= min_volume and avg_price >= min_price:
                valid_tickers.append({
                    'ticker': ticker,
                    'name': row.get('name', ''),
                    'sector': row.get('sector', ''),
                    'subsector': row.get('subsector', ''),
                    'avg_volume': avg_volume,
                    'avg_price': avg_price
                })
                
                if len(valid_tickers) % 10 == 0:
                    print(f"  ✓ {len(valid_tickers)} tickers válidos encontrados...")
                    
        except Exception as e:
            continue
    
    return pd.DataFrame(valid_tickers)

def balance_by_sector(df, max_per_sector=15):
    """Balancea tickers por sector (evitar concentración)"""
    print(f"\n[INFO] Balanceando por sector (max {max_per_sector}/sector)...")
    
    balanced = []
    for sector in df['sector'].unique():
        sector_tickers = df[df['sector'] == sector].nlargest(max_per_sector, 'avg_volume')
        balanced.append(sector_tickers)
        print(f"  {sector:30s}: {len(sector_tickers)} tickers")
    
    return pd.concat(balanced, ignore_index=True)

def add_etfs(df):
    """Agrega ETFs principales para cobertura de índices"""
    etfs = [
        {'ticker': 'SPY', 'name': 'SPDR S&P 500', 'sector': 'ETF', 'subsector': 'Broad Market'},
        {'ticker': 'QQQ', 'name': 'Invesco QQQ', 'sector': 'ETF', 'subsector': 'Tech'},
        {'ticker': 'IWM', 'name': 'iShares Russell 2000', 'sector': 'ETF', 'subsector': 'Small Cap'},
        {'ticker': 'DIA', 'name': 'SPDR Dow Jones', 'sector': 'ETF', 'subsector': 'Blue Chip'},
        {'ticker': 'XLF', 'name': 'Financial Select', 'sector': 'ETF', 'subsector': 'Financials'},
        {'ticker': 'XLE', 'name': 'Energy Select', 'sector': 'ETF', 'subsector': 'Energy'},
        {'ticker': 'XLK', 'name': 'Technology Select', 'sector': 'ETF', 'subsector': 'Technology'},
        {'ticker': 'XLV', 'name': 'Health Care Select', 'sector': 'ETF', 'subsector': 'Health Care'},
    ]
    
    etf_df = pd.DataFrame(etfs)
    print(f"\n[INFO] Agregando {len(etf_df)} ETFs principales...")
    
    return pd.concat([df, etf_df], ignore_index=True)

def main():
    output_dir = 'data/us/'
    os.makedirs(output_dir, exist_ok=True)
    
    print("="*60)
    print("CONSTRUYENDO UNIVERSO EXPANDIDO (50-100 TICKERS)")
    print("="*60)
    
    # 1. Descargar listas
    print("\n[1/5] Descargando listas de tickers...")
    sp500 = get_sp500_tickers()
    nasdaq100 = get_nasdaq100_tickers()
    
    # Combinar y deduplicar
    all_tickers = pd.concat([sp500, nasdaq100], ignore_index=True).drop_duplicates(subset=['ticker'])
    print(f"[OK] {len(all_tickers)} tickers únicos combinados")
    
    # 2. Filtrar por liquidez
    print("\n[2/5] Filtrando por liquidez...")
    liquid_tickers = filter_by_liquidity(all_tickers, min_volume=1_000_000, min_price=5, lookback_days=60)
    print(f"[OK] {len(liquid_tickers)} tickers líquidos")
    
    # 3. Balancear por sector
    print("\n[3/5] Balanceando por sector...")
    balanced = balance_by_sector(liquid_tickers, max_per_sector=15)
    print(f"[OK] {len(balanced)} tickers balanceados")
    
    # 4. Agregar ETFs
    print("\n[4/5] Agregando ETFs...")
    final = add_etfs(balanced)
    
    # 5. Ordenar y guardar
    print("\n[5/5] Guardando universo final...")
    final = final.sort_values('avg_volume', ascending=False).reset_index(drop=True)
    
    # Limitar a 100 tickers top por volumen
    if len(final) > 100:
        final = final.head(100)
        print(f"[INFO] Limitado a top 100 por volumen")
    
    # Guardar
    output_path = os.path.join(output_dir, 'tickers_universe_expanded.csv')
    final.to_csv(output_path, index=False)
    
    print(f"\n{'='*60}")
    print(f"UNIVERSO FINAL: {len(final)} TICKERS")
    print(f"{'='*60}")
    
    # Resumen por sector
    print("\nDistribución por sector:")
    sector_counts = final['sector'].value_counts()
    for sector, count in sector_counts.items():
        print(f"  {sector:30s}: {count:3d} tickers")
    
    print(f"\nVolumen promedio: ${final['avg_volume'].mean():,.0f}")
    print(f"Precio promedio:  ${final['avg_price'].mean():.2f}")
    
    print(f"\n[OK] Guardado en: {output_path}")
    
    # Guardar también versión simple (solo tickers)
    simple_path = os.path.join(output_dir, 'tickers_expanded.csv')
    final[['ticker', 'sector']].to_csv(simple_path, index=False)
    print(f"[OK] Versión simple: {simple_path}")
    
    return final

if __name__ == "__main__":
    universe = main()
