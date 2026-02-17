import os
from datetime import datetime, timedelta, timezone
import pandas as pd

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

# =========================
# KEYS (DESDE ENTORNO)
# =========================
APCA_API_KEY_ID = os.getenv("APCA_API_KEY_ID")
APCA_API_SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")

if not APCA_API_KEY_ID or not APCA_API_SECRET_KEY:
    raise RuntimeError("Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY in environment")

# =========================
# CONFIG
# =========================
TICKERS = ["AAPL", "AMD", "AMZN", "CAT", "CVX", "GS", "IWM", "JNJ", "JPM", "MS", "MSFT", "NVDA", "PFE", "QQQ", "SPY", "TSLA", "WMT", "XOM"]

TIMEFRAME = TimeFrame(15, TimeFrameUnit.Minute)
YEARS_BACK = 6

BASE_DIR = "data/us/intraday_15m"
PER_TICKER_DIR = os.path.join(BASE_DIR, "per_ticker")
os.makedirs(PER_TICKER_DIR, exist_ok=True)

# =========================
# CLIENTE
# =========================
client = StockHistoricalDataClient(APCA_API_KEY_ID, APCA_API_SECRET_KEY)

# =========================
# RANGO FECHAS
# =========================
end = datetime.now(timezone.utc)
start = end - timedelta(days=365 * YEARS_BACK)

dfs = []

for i, ticker in enumerate(TICKERS, 1):
    print(f"\n[{i}/{len(TICKERS)}] Descargando {ticker} (15m)")

    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TIMEFRAME,
        start=start,
        end=end,
        adjustment="raw",
        feed="iex"  # <<< evita SIP (premium) y usa IEX (gratis)
    )

    bars = client.get_stock_bars(request).df
    if bars.empty:
        raise RuntimeError(f"❌ No se recibieron datos para {ticker} (feed=iex)")

    # Normalizar: multiindex (symbol, timestamp) -> columnas
    bars = bars.reset_index().rename(columns={"symbol": "ticker"})
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)

    bars = bars[["timestamp", "open", "high", "low", "close", "volume", "ticker"]]
    bars = bars.sort_values(["ticker", "timestamp"])

    out_ticker = os.path.join(PER_TICKER_DIR, f"{ticker}.parquet")
    bars.to_parquet(out_ticker, index=False)
    print(f"✅ Guardado: {out_ticker} | filas: {len(bars):,}")

    dfs.append(bars)

consolidated = pd.concat(dfs, ignore_index=True).sort_values(["ticker", "timestamp"])
out_consolidated = os.path.join(BASE_DIR, "consolidated_15m.parquet")
consolidated.to_parquet(out_consolidated, index=False)

print("\n✅ DESCARGA COMPLETA")
print(f"📦 Consolidado: {out_consolidated}")
print(f"📊 Total filas: {len(consolidated):,}")
