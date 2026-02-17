import time
import hashlib
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class Limits:
    trading_enabled: bool
    max_orders_per_hour: int
    max_open_positions: int
    max_daily_notional_usd: float
    max_daily_drawdown_pct: float


def make_limits(env: Dict[str, str]) -> Limits:
    return Limits(
        trading_enabled=str(env.get("TRADING_ENABLED", "0")) == "1",
        max_orders_per_hour=int(env.get("MAX_ORDERS_PER_HOUR", 20)),
        max_open_positions=int(env.get("MAX_OPEN_POSITIONS", 5)),
        max_daily_notional_usd=float(env.get("MAX_DAILY_NOTIONAL_USD", 5000)),
        max_daily_drawdown_pct=float(env.get("MAX_DAILY_DRAWDOWN_PCT", 3.0)),
    )


def client_order_id(symbol: str, side: str, strategy_id: str = "hybrid") -> str:
    ts = time.strftime("%Y%m%d%H%M%S")
    payload = f"{ts}-{symbol}-{side}-{strategy_id}"
    digest = hashlib.sha1(payload.encode()).hexdigest()[:6]
    return f"{ts}-{symbol}-{side}-{strategy_id}-{digest}"


def can_place_order(
    limits: Limits,
    open_positions: int,
    orders_last_hour: int,
    today_notional: float,
    day_drawdown_pct: float,
) -> bool:
    if not limits.trading_enabled:
        return False
    if open_positions >= limits.max_open_positions:
        return False
    if orders_last_hour >= limits.max_orders_per_hour:
        return False
    if today_notional >= limits.max_daily_notional_usd:
        return False
    if day_drawdown_pct <= -abs(limits.max_daily_drawdown_pct):
        return False
    return True


def guardrail_reason(
    limits: Limits,
    open_positions: int,
    orders_last_hour: int,
    today_notional: float,
    day_drawdown_pct: float,
) -> str:
    if not limits.trading_enabled:
        return "trading_disabled"
    if open_positions >= limits.max_open_positions:
        return "max_open_positions"
    if orders_last_hour >= limits.max_orders_per_hour:
        return "max_orders_per_hour"
    if today_notional >= limits.max_daily_notional_usd:
        return "max_daily_notional"
    if day_drawdown_pct <= -abs(limits.max_daily_drawdown_pct):
        return "max_daily_drawdown"
    return "ok"
