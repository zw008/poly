#!/usr/bin/env python3
"""Main entry point — run the Polymarket V5.1 live trading bot."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.config import (
    DRY_RUN,
    SCANNER_POLL_INTERVAL_SECONDS,
    load_credentials,
)
from src.live.client import ClobClient
from src.live.executor import OrderExecutor
from src.live.monitor import PositionMonitor
from src.live.risk import RiskManager
from src.live.scanner import fetch_active_markets, fetch_best_bid
from src.strategy import check_entry_eligible
from src.utils import hours_until

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            Path(__file__).parent / "logs" / f"live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        ),
    ],
)
logger = logging.getLogger(__name__)

# Graceful shutdown
_shutdown = threading.Event()


def _handle_signal(signum: int, frame: object) -> None:
    logger.info("Received signal %d — initiating graceful shutdown...", signum)
    _shutdown.set()


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket V5.1 Live Trading Bot")
    parser.add_argument("--capital", type=float, default=1_000.0, help="Initial capital in USD")
    parser.add_argument("--dry-run", action="store_true", default=None, help="Force dry-run mode")
    args = parser.parse_args()

    # Ensure logs directory exists
    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(exist_ok=True)

    # Load .env
    load_dotenv(Path(__file__).parent / ".env")

    dry_run = args.dry_run if args.dry_run is not None else DRY_RUN

    logger.info("=" * 60)
    logger.info("  POLYMARKET V5.1 — LIVE TRADING BOT")
    logger.info("  Mode: %s", "DRY RUN" if dry_run else "LIVE TRADING")
    logger.info("  Capital: $%.2f", args.capital)
    logger.info("=" * 60)

    if not dry_run:
        logger.warning("LIVE TRADING MODE — Real money at risk!")
        time.sleep(3)  # Give user time to Ctrl+C

    # Load credentials
    creds = load_credentials()
    client = ClobClient(creds, dry_run=dry_run)

    # Initialize components
    risk = RiskManager(initial_capital=args.capital)
    executor = OrderExecutor(client, risk, args.capital)
    monitor = PositionMonitor(executor, check_interval=30.0)

    # Signal handlers
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Start position monitor in background thread
    monitor_thread = threading.Thread(target=monitor.run_loop, daemon=True)
    monitor_thread.start()

    logger.info("Starting scanner loop (interval=%ds)...", SCANNER_POLL_INTERVAL_SECONDS)
    cycle = 0

    while not _shutdown.is_set():
        cycle += 1
        logger.info("--- Scan cycle %d ---", cycle)

        try:
            # Scan for active markets
            markets = fetch_active_markets(max_pages=3)
            logger.info("Found %d candidate markets", len(markets))

            # Check each market for entry
            entries = 0
            for market in markets:
                if _shutdown.is_set():
                    break

                bid = fetch_best_bid(market.token_id)
                if bid is None:
                    continue

                hours = hours_until(market.end_date)
                if hours <= 0:
                    continue

                tier = check_entry_eligible(
                    market,
                    bid,
                    hours,
                    executor.open_positions,
                    executor.cash,
                )
                if tier is None:
                    continue

                pos = executor.open_position(market, bid, tier)
                if pos is not None:
                    entries += 1

                time.sleep(0.5)  # Rate limit

            logger.info(
                "Cycle %d: %d new entries, %d open positions, %s",
                cycle,
                entries,
                len(executor.open_positions),
                risk.status_text(),
            )

        except Exception as exc:
            logger.error("Scanner error: %s", exc, exc_info=True)

        # Wait for next cycle or shutdown
        _shutdown.wait(timeout=SCANNER_POLL_INTERVAL_SECONDS)

    # Graceful shutdown
    logger.info("Shutting down...")
    logger.info("Cancelling all TP orders...")
    executor.cancel_all_tp_orders()

    logger.info(
        "Final: %d open positions, cash=$%.2f, %s",
        len(executor.open_positions),
        executor.cash,
        risk.status_text(),
    )
    logger.info("Shutdown complete. Open positions will settle at resolution.")


if __name__ == "__main__":
    main()
