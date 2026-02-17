from pathlib import Path
from typing import Dict, Iterable, List
import logging

from .state_store import atomic_write_csv, atomic_write_json, now_iso

logger = logging.getLogger(__name__)

POS_HEADERS = [
    "timestamp",
    "symbol",
    "qty",
    "avg_entry_price",
    "last_price",
    "unrealized_pnl",
    "market_value",
    "tp",
    "sl",
    "status",
]

EQUITY_HEADERS = [
    "timestamp",
    "equity",
    "cash",
    "buying_power",
    "day_pnl",
    "day_pnl_pct",
]

TRADES_HEADERS = [
    "timestamp",
    "order_id",
    "client_order_id",
    "symbol",
    "side",
    "qty",
    "filled_qty",
    "filled_avg_price",
    "status",
    "reason",
]


def write_positions_snapshot(path: Path, rows: Iterable[Iterable]) -> None:
    atomic_write_csv(path, POS_HEADERS, rows)
    logger.info("positions snapshot written -> %s", path)


def write_equity_snapshot(path: Path, rows: Iterable[Iterable]) -> None:
    atomic_write_csv(path, EQUITY_HEADERS, rows)
    logger.info("equity snapshot written -> %s", path)


def write_trades_snapshot(path: Path, rows: Iterable[Iterable]) -> None:
    atomic_write_csv(path, TRADES_HEADERS, rows)
    logger.info("trades snapshot written -> %s", path)


def write_heartbeat(path: Path, payload: Dict) -> None:
    payload = dict(payload)
    payload.setdefault("last_update", now_iso())
    atomic_write_json(path, payload)
    logger.debug("heartbeat updated -> %s", path)


def build_positions_rows(positions: List[Dict], price_cache: Dict[str, float]) -> List[List]:
    rows: List[List] = []
    for pos in positions:
        sym = pos.get("symbol") or pos.get("asset_id") or "?"
        last = price_cache.get(sym, pos.get("last_price", 0))
        qty = float(pos.get("qty", 0))
        avg = float(pos.get("avg_entry_price", 0))
        mvalue = qty * last
        unreal = (last - avg) * qty
        rows.append(
            [
                pos.get("timestamp") or now_iso(),
                sym,
                qty,
                avg,
                last,
                unreal,
                mvalue,
                pos.get("tp", ""),
                pos.get("sl", ""),
                pos.get("status", "OPEN" if qty else "CLOSED"),
            ]
        )
    return rows


def build_equity_row(account: Dict) -> List[List]:
    ts = account.get("timestamp") or now_iso()
    equity = float(account.get("equity", 0))
    cash = float(account.get("cash", 0))
    buying_power = float(account.get("buying_power", 0))
    day_pnl = float(account.get("day_pnl", 0))
    day_pnl_pct = float(account.get("day_pnl_pct", 0))
    return [[ts, equity, cash, buying_power, day_pnl, day_pnl_pct]]


def build_trades_rows(trades: List[Dict]) -> List[List]:
    rows: List[List] = []
    for t in trades:
        rows.append(
            [
                t.get("timestamp") or now_iso(),
                t.get("order_id", ""),
                t.get("client_order_id", ""),
                t.get("symbol", ""),
                t.get("side", ""),
                float(t.get("qty", 0)),
                float(t.get("filled_qty", 0)),
                float(t.get("filled_avg_price", 0)),
                t.get("status", "unknown"),
                t.get("reason", ""),
            ]
        )
    return rows
