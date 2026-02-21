"""Price monitor — watches positions for stop-loss and take-profit conditions."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from src.config import TIERS
from src.models import ExitReason
from src.strategy import check_hard_stop, check_take_profit, classify_tier
from src.utils import hours_until
from src.live.executor import OrderExecutor
from src.live.scanner import fetch_current_price

logger = logging.getLogger(__name__)


class PositionMonitor:
    """Periodically check open positions for exit conditions."""

    def __init__(self, executor: OrderExecutor, check_interval: float = 30.0) -> None:
        self.executor = executor
        self.check_interval = check_interval

    def check_positions(self) -> None:
        """Check all open positions for exit conditions."""
        for pos in list(self.executor.open_positions):
            price = fetch_current_price(pos.market.token_id)
            if price is None:
                logger.debug("No price data for %s", pos.market.question[:30])
                continue

            # Find matching tier
            tier = None
            for t in TIERS:
                if t.name == pos.tier_name:
                    tier = t
                    break
            if tier is None:
                continue

            # Check take-profit (TP order might have filled already)
            if check_take_profit(price):
                from src.config import TAKE_PROFIT_PRICE

                self.executor.close_position(
                    pos, TAKE_PROFIT_PRICE, ExitReason.TAKE_PROFIT
                )
                continue

            # Check hard stop
            soft_triggered = pos.soft_stop_triggered_at is not None
            should_stop, new_trigger = check_hard_stop(
                price, tier, soft_triggered, None
            )

            if should_stop:
                self.executor.close_position(
                    pos, price, ExitReason.HARD_STOP, is_taker=True
                )
            elif new_trigger and not soft_triggered:
                pos.soft_stop_triggered_at = datetime.now(timezone.utc)
                logger.warning(
                    "Soft stop triggered for %s @ %.3f",
                    pos.market.question[:30],
                    price,
                )
            elif not new_trigger and soft_triggered:
                pos.soft_stop_triggered_at = None
                logger.info(
                    "Soft stop recovered for %s @ %.3f",
                    pos.market.question[:30],
                    price,
                )

    def run_loop(self) -> None:
        """Run monitoring loop (blocking). Call from thread or asyncio."""
        logger.info("Position monitor started (interval=%.0fs)", self.check_interval)
        while True:
            try:
                self.check_positions()
            except Exception as exc:
                logger.error("Monitor error: %s", exc, exc_info=True)
            time.sleep(self.check_interval)
