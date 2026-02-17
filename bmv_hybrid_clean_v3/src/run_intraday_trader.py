import argparse
import json
import logging
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional

from .alpaca_adapter import AlpacaAdapter
from .guardrails import can_place_order, client_order_id, guardrail_reason, make_limits
from .snapshot_writer import (
    build_equity_row,
    build_positions_rows,
    build_trades_rows,
    write_equity_snapshot,
    write_heartbeat,
    write_positions_snapshot,
    write_trades_snapshot,
)
from .state_store import ensure_runtime_dirs, load_runtime_env, now_iso

logger = logging.getLogger(__name__)


class TraderLoop:
    def __init__(self, env: Dict[str, str], orders_path: Path, snapshot_dir: Path) -> None:
        self.env = env
        self.symbols = self._parse_symbols(env)
        self.limits = make_limits(env)
        self.orders_path = orders_path
        self.snapshot_dir = snapshot_dir
        self.adapter = AlpacaAdapter(env)

        self.order_timestamps: Deque[datetime] = deque()
        self.today_notional = 0.0
        self.today = datetime.now(timezone.utc).date()
        self.trades: List[Dict] = []

    def _parse_symbols(self, env: Dict[str, str]) -> List[str]:
        raw = env.get("SYMBOLS", "")
        return [s.strip().upper() for s in raw.split(",") if s.strip()]

    def _roll_daily(self, now: datetime) -> None:
        if now.date() != self.today:
            self.today = now.date()
            self.today_notional = 0.0
            self.order_timestamps.clear()
            self.trades.clear()

    def _orders_last_hour(self, now: datetime) -> int:
        cutoff = now - timedelta(hours=1)
        while self.order_timestamps and self.order_timestamps[0] < cutoff:
            self.order_timestamps.popleft()
        return len(self.order_timestamps)

    def _load_orders(self) -> List[Dict]:
        if not self.orders_path.exists():
            return []
        try:
            return json.loads(self.orders_path.read_text()) or []
        except Exception as exc:
            logger.warning("Failed to read orders file %s: %s", self.orders_path, exc)
            return []

    def _archive_orders(self) -> None:
        try:
            stamp = int(time.time())
            archived = self.orders_path.with_suffix(f".processed.{stamp}.json")
            self.orders_path.rename(archived)
        except Exception as exc:
            logger.warning("Failed to archive orders file: %s", exc)
            try:
                self.orders_path.unlink()
            except Exception:
                pass

    def _latest_price(self, symbol: str) -> Optional[float]:
        return self.adapter.fetch_latest_price(symbol)

    def _guardrails_status(self, open_positions: int, orders_last_hour: int, today_notional: float, day_drawdown_pct: float) -> str:
        return guardrail_reason(
            self.limits,
            open_positions=open_positions,
            orders_last_hour=orders_last_hour,
            today_notional=today_notional,
            day_drawdown_pct=day_drawdown_pct,
        )

    def _record_trade(self, payload: Dict) -> None:
        self.trades.append(payload)
        if len(self.trades) > 200:
            self.trades = self.trades[-200:]

    def tick(self) -> None:
        now = datetime.now(timezone.utc)
        self._roll_daily(now)

        account = self.adapter.fetch_account()
        positions = self.adapter.fetch_positions()

        price_cache: Dict[str, float] = {}
        for sym in self.symbols:
            px = self._latest_price(sym)
            if px is not None:
                price_cache[sym] = px
        for pos in positions:
            sym = pos.get("symbol")
            if sym and sym not in price_cache and pos.get("last_price") is not None:
                price_cache[sym] = float(pos.get("last_price"))

        orders_last_hour = self._orders_last_hour(now)
        open_positions = len(positions)
        day_drawdown_pct = float(account.get("day_pnl_pct", 0))

        orders = self._load_orders()
        if orders:
            logger.info("processing %s orders", len(orders))

        for order in orders:
            symbol = str(order.get("symbol", "")).upper()
            side = str(order.get("side", "")).upper()
            qty = float(order.get("qty", 0) or 0)
            reason = order.get("reason", "")
            if not symbol or qty <= 0 or side not in {"BUY", "SELL"}:
                logger.warning("invalid order payload skipped: %s", order)
                continue

            last_price = price_cache.get(symbol) or self._latest_price(symbol)
            if last_price is None:
                logger.warning("no price for %s, skipping order", symbol)
                self._record_trade(
                    {
                        "timestamp": now_iso(),
                        "order_id": "",
                        "client_order_id": "",
                        "symbol": symbol,
                        "side": side,
                        "qty": qty,
                        "filled_qty": 0,
                        "filled_avg_price": 0,
                        "status": "blocked",
                        "reason": "no_price",
                    }
                )
                continue

            proposed_notional = self.today_notional + abs(qty * last_price)
            if not can_place_order(
                self.limits,
                open_positions=open_positions,
                orders_last_hour=orders_last_hour,
                today_notional=proposed_notional,
                day_drawdown_pct=day_drawdown_pct,
            ):
                block_reason = self._guardrails_status(open_positions, orders_last_hour, proposed_notional, day_drawdown_pct)
                logger.warning("guardrails block %s %s: %s", side, symbol, block_reason)
                self._record_trade(
                    {
                        "timestamp": now_iso(),
                        "order_id": "",
                        "client_order_id": "",
                        "symbol": symbol,
                        "side": side,
                        "qty": qty,
                        "filled_qty": 0,
                        "filled_avg_price": 0,
                        "status": "blocked",
                        "reason": block_reason,
                    }
                )
                continue

            coid = client_order_id(symbol, side, strategy_id=self.env.get("ENGINE_NAME", "hybrid"))
            try:
                alpaca_order = self.adapter.submit_order(symbol, qty, side, coid)
                order_id = getattr(alpaca_order, "id", "")
                filled_qty = float(getattr(alpaca_order, "filled_qty", 0) or 0)
                filled_avg_price = float(getattr(alpaca_order, "filled_avg_price", 0) or 0)
                status = str(getattr(alpaca_order, "status", "submitted"))

                self.today_notional = proposed_notional
                self.order_timestamps.append(now)

                self._record_trade(
                    {
                        "timestamp": now_iso(),
                        "order_id": order_id,
                        "client_order_id": coid,
                        "symbol": symbol,
                        "side": side,
                        "qty": qty,
                        "filled_qty": filled_qty,
                        "filled_avg_price": filled_avg_price,
                        "status": status,
                        "reason": reason or "order_submitted",
                    }
                )
                logger.info("order submitted %s %s qty=%s status=%s", side, symbol, qty, status)
            except Exception as exc:  # pragma: no cover - network
                logger.exception("order submit failed for %s %s: %s", side, symbol, exc)
                self._record_trade(
                    {
                        "timestamp": now_iso(),
                        "order_id": "",
                        "client_order_id": coid,
                        "symbol": symbol,
                        "side": side,
                        "qty": qty,
                        "filled_qty": 0,
                        "filled_avg_price": 0,
                        "status": "error",
                        "reason": str(exc),
                    }
                )

        if orders:
            self._archive_orders()

        write_positions_snapshot(self.snapshot_dir / "positions.csv", build_positions_rows(positions, price_cache))
        write_equity_snapshot(self.snapshot_dir / "equity.csv", build_equity_row(account))
        write_trades_snapshot(self.snapshot_dir / "trades.csv", build_trades_rows(self.trades))

        hb_payload = {
            "engine": self.env.get("ENGINE_NAME", "USA_Hybrid_Clean_V1"),
            "mode": self.env.get("MODE", "trader"),
            "symbols": self.symbols,
            "last_loop": now_iso(),
            "guardrail": self._guardrails_status(
                open_positions,
                orders_last_hour,
                self.today_notional,
                day_drawdown_pct,
            ),
        }
        write_heartbeat(self.snapshot_dir / "heartbeat.json", hb_payload)


def _resolve_snapshot_dir(env: Dict[str, str]) -> Path:
    base = Path(env.get("SNAPSHOT_DIR", "engine_runtime"))
    if not base.is_absolute():
        base = Path(__file__).resolve().parents[1] / base
    base.mkdir(parents=True, exist_ok=True)
    ensure_runtime_dirs(base)
    return base


def main() -> None:
    parser = argparse.ArgumentParser(description="Intraday trader with guardrails")
    parser.add_argument("--env", type=Path, default=Path(__file__).resolve().parents[1] / "config" / "runtime.env")
    parser.add_argument("--orders", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "orders.json")
    parser.add_argument("--interval", type=int, default=None, help="Polling interval seconds")
    args = parser.parse_args()

    env = load_runtime_env(args.env)
    interval = args.interval or int(env.get("INTERVAL_SEC", 60) or 60)

    snapshot_dir = _resolve_snapshot_dir(env)
    loop = TraderLoop(env, args.orders, snapshot_dir)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("trader started | symbols=%s interval=%ss", ",".join(loop.symbols), interval)

    while True:
        try:
            loop.tick()
        except Exception as exc:  # pragma: no cover - runtime loop
            logger.exception("trader loop failed: %s", exc)
            write_heartbeat(
                snapshot_dir / "heartbeat.json",
                {
                    "engine": env.get("ENGINE_NAME", "USA_Hybrid_Clean_V1"),
                    "mode": env.get("MODE", "trader"),
                    "status": "error",
                    "error": str(exc),
                    "last_loop": now_iso(),
                },
            )
        time.sleep(max(1, interval))


if __name__ == "__main__":
    main()
