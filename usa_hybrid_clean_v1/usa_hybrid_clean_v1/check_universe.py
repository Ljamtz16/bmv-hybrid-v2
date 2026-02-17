"""Check available universe in project data"""
import pandas as pd

INTRADAY_FILE = r"C:\Users\M3400WUAK-WA023W\bmv_hybrid_clean_v3\data\us\intraday_15m\consolidated_15m.parquet"
FORECAST_FILE = "evidence/forecast_retrained_robust/forecast_prob_win_retrained.parquet"

intraday = pd.read_parquet(INTRADAY_FILE)
forecast = pd.read_parquet(FORECAST_FILE)

intraday_tickers = sorted(intraday['ticker'].unique())
forecast_tickers = sorted(forecast['ticker'].unique())
intersection = sorted(set(intraday_tickers) & set(forecast_tickers))

print("=" * 80)
print("UNIVERSE ANALYSIS")
print("=" * 80)
print(f"\nIntraday tickers: {len(intraday_tickers)}")
print(f"  Sample: {intraday_tickers[:15]}")

print(f"\nForecast tickers: {len(forecast_tickers)}")
print(f"  Sample: {forecast_tickers[:15]}")

print(f"\nINTERSECTION (valid for backtest): {len(intersection)}")
print(f"  Tickers: {intersection}")

print("\nDate range (intraday):", intraday['date'].min(), "to", intraday['date'].max())
print("Date range (forecast):", forecast['date'].min(), "to", forecast['date'].max())
print("=" * 80)
