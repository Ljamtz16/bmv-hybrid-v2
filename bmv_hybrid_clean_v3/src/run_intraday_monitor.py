import argparse
import logging
import time
from pathlib import Path
from typing import Dict, List

from .alpaca_adapter import AlpacaAdapter
from .guardrails import guardrail_reason, make_limits
from .snapshot_writer import (
    build_equity_row,
    build_positions_rows,
    write_equity_snapshot,
    write_heartbeat,
    write_positions_snapshot,
)
from .state_store import ensure_runtime_dirs, load_runtime_env, now_iso

logger = logging.getLogger(__name__)


def _parse_symbols(env: Dict[str, str]) -> List[str]:
    raw = env.get("SYMBOLS", "")
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def _resolve_snapshot_dir(env: Dict[str, str]) -> Path:
    base = Path(env.get("SNAPSHOT_DIR", "engine_runtime"))
    if not base.is_absolute():
        base = Path(__file__).resolve().parents[1] / base
    base.mkdir(parents=True, exist_ok=True)
    ensure_runtime_dirs(base)
    return base


def _collect_price_cache(adapter: AlpacaAdapter, symbols: List[str]) -> Dict[str, float]:
    cache: Dict[str, float] = {}
    for sym in symbols:
        px = adapter.fetch_latest_price(sym)
        if px is not None:
            cache[sym] = px
    return cache


def run_monitor(env_path: Path, interval_sec: int) -> None:
    env = load_runtime_env(env_path)
    limits = make_limits(env)
    symbols = _parse_symbols(env)
    snapshot_dir = _resolve_snapshot_dir(env)

    adapter = AlpacaAdapter(env)

    logger.info("monitor started | symbols=%s interval=%ss", ",".join(symbols), interval_sec)

    while True:
        try:
            account = adapter.fetch_account()
            positions = adapter.fetch_positions()

            price_cache = _collect_price_cache(adapter, symbols)
            for pos in positions:
                sym = pos.get("symbol")
                if sym and sym not in price_cache and pos.get("last_price") is not None:
                    price_cache[sym] = float(pos.get("last_price"))

            write_positions_snapshot(snapshot_dir / "positions.csv", build_positions_rows(positions, price_cache))
            write_equity_snapshot(snapshot_dir / "equity.csv", build_equity_row(account))

            hb_payload = {
                "engine": env.get("ENGINE_NAME", "USA_Hybrid_Clean_V1"),
                "mode": env.get("MODE", "monitor"),
                "symbols": symbols,
                "last_loop": now_iso(),
                "guardrail": guardrail_reason(
                    limits,
                    open_positions=len(positions),
                    orders_last_hour=0,
                    today_notional=sum(abs(p.get("market_value", 0)) for p in positions),
                    day_drawdown_pct=float(account.get("day_pnl_pct", 0)),
                ),
            }
            write_heartbeat(snapshot_dir / "heartbeat.json", hb_payload)
        except Exception as exc:  # pragma: no cover - runtime loop
            logger.exception("monitor loop failed: %s", exc)
            write_heartbeat(
                snapshot_dir / "heartbeat.json",
                {
                    "engine": env.get("ENGINE_NAME", "USA_Hybrid_Clean_V1"),
                    "mode": env.get("MODE", "monitor"),
                    "status": "error",
                    "error": str(exc),
                    "last_loop": now_iso(),
                },
            )

        time.sleep(max(1, interval_sec))


def main() -> None:
    parser = argparse.ArgumentParser(description="Intraday monitor: fetch account/positions snapshots")
    parser.add_argument("--env", type=Path, default=Path(__file__).resolve().parents[1] / "config" / "runtime.env")
    parser.add_argument("--interval", type=int, default=None, help="Polling interval seconds")
    args = parser.parse_args()

    env_data = load_runtime_env(args.env)
    interval = args.interval or int(env_data.get("INTERVAL_SEC", 60) or 60)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_monitor(args.env, interval)


if __name__ == "__main__":
    main()
