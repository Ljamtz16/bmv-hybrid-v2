import time
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AlpacaAdapter:
    def __init__(self, env: Dict[str, str]):
        self.env = env
        self._trading_client = None
        self._data_client = None

    def _trading(self):
        if self._trading_client:
            return self._trading_client
        from alpaca.trading.client import TradingClient

        paper = str(self.env.get("ALPACA_PAPER", "1")) == "1"
        self._trading_client = TradingClient(
            self.env.get("ALPACA_API_KEY", ""),
            self.env.get("ALPACA_API_SECRET", ""),
            paper=paper,
        )
        return self._trading_client

    def _data(self):
        if self._data_client:
            return self._data_client
        from alpaca.data.historical import StockHistoricalDataClient

        self._data_client = StockHistoricalDataClient(
            self.env.get("ALPACA_API_KEY", ""),
            self.env.get("ALPACA_API_SECRET", ""),
        )
        return self._data_client

    def fetch_account(self) -> Dict:
        from alpaca.trading.requests import GetAccountRequest

        acc = self._retry(lambda: self._trading().get_account(GetAccountRequest()))
        return {
            "equity": float(acc.equity),
            "cash": float(acc.cash),
            "buying_power": float(acc.buying_power),
            "day_pnl": float(acc.equity) - float(acc.last_equity),
            "day_pnl_pct": ((float(acc.equity) - float(acc.last_equity)) / float(acc.last_equity)) * 100 if float(acc.last_equity) else 0,
        }

    def fetch_positions(self) -> List[Dict]:
        pos = self._retry(self._trading().get_all_positions)
        out: List[Dict] = []
        for p in pos:
            out.append(
                {
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "avg_entry_price": float(p.avg_entry_price),
                    "market_value": float(p.market_value),
                    "last_price": float(p.current_price),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "status": "OPEN",
                }
            )
        return out

    def fetch_latest_price(self, symbol: str) -> Optional[float]:
        try:
            from alpaca.data.requests import StockLatestTradeRequest

            req = StockLatestTradeRequest(symbol_or_symbols=symbol)
            resp = self._retry(lambda: self._data().get_stock_latest_trade(req))
            trade = resp[symbol] if isinstance(resp, dict) else resp
            return float(trade.price)
        except Exception as exc:
            logger.warning("latest price failed for %s: %s", symbol, exc)
            return None

    def submit_order(self, symbol: str, qty: float, side: str, client_order_id: str):
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide(side.lower()),
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )
        return self._retry(lambda: self._trading().submit_order(req))

    def fetch_order_by_client_id(self, client_order_id: str):
        from alpaca.trading.requests import GetOrdersRequest

        req = GetOrdersRequest(client_order_id=client_order_id)
        orders = self._retry(lambda: self._trading().get_orders(req))
        return orders[0] if orders else None

    def _retry(self, func, retries: int = 3, backoff: float = 1.5):
        last_exc = None
        for attempt in range(retries):
            try:
                return func()
            except Exception as exc:  # pragma: no cover - network dependent
                last_exc = exc
                logger.warning("alpaca call failed (attempt %s/%s): %s", attempt + 1, retries, exc)
                time.sleep(backoff * (attempt + 1))
        raise RuntimeError(f"alpaca call failed after {retries} attempts: {last_exc}")
