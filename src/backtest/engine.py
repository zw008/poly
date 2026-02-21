"""Backtest engine — simulates strategy execution on historical data."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from src.config import MAKER_FEE_PCT, TAKER_FEE_PCT, TierConfig
from src.models import ExitReason, Market, Portfolio, Position, PricePoint
from src import strategy

logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(self, initial_capital: float = 10_000.0) -> None:
        self.portfolio = Portfolio(initial_capital=initial_capital)
        self.all_trades: list[Position] = []

    def _open_position(
        self, market: Market, price: float, tier: TierConfig, timestamp: datetime,
    ) -> None:
        entry_price = strategy.compute_entry_price(price, tier.price_high)
        investment = tier.position_size_usd
        shares = investment / entry_price

        pos = Position(
            market=market,
            tier_name=tier.name,
            entry_price=entry_price,
            entry_time=timestamp,
            shares=shares,
            investment=investment,
            fees_paid=investment * MAKER_FEE_PCT,
        )
        self.portfolio.cash -= investment
        self.portfolio.positions.append(pos)

    def _close_position(
        self, pos: Position, exit_price: float, exit_time: datetime,
        reason: ExitReason, is_taker: bool = False,
    ) -> None:
        pos.exit_price = exit_price
        pos.exit_time = exit_time
        pos.exit_reason = reason

        exit_value = pos.shares * exit_price
        fee = exit_value * (TAKER_FEE_PCT if is_taker else MAKER_FEE_PCT)
        pos.fees_paid += fee

        self.portfolio.cash += exit_value - fee
        self.portfolio.closed_positions.append(pos)
        self.portfolio.positions.remove(pos)
        self.all_trades.append(pos)

    def _settle_position(self, pos: Position, market: Market) -> None:
        resolved_at = market.resolved_at or market.end_date
        winning = (market.winning_outcome or "").lower()
        if winning in ("yes", "y", "1", "true"):
            self._close_position(pos, 1.00, resolved_at, ExitReason.SETTLED_WIN)
        else:
            self._close_position(pos, 0.00, resolved_at, ExitReason.SETTLED_LOSS)

    def scan_market(self, market: Market, prices: list[PricePoint]) -> None:
        if not prices or not market.resolved_at:
            return

        position: Optional[Position] = None
        tier: Optional[TierConfig] = None

        for i, pp in enumerate(prices):
            hours_to_res = (market.resolved_at - pp.timestamp).total_seconds() / 3600
            if hours_to_res < 0:
                continue

            next_price = prices[i + 1].price if i + 1 < len(prices) else None

            # Exit checks
            if position is not None and position.is_open:
                assert tier is not None
                should_stop, new_trigger = strategy.check_hard_stop(
                    pp.price, tier,
                    position.soft_stop_triggered_at is not None,
                    next_price,
                )
                if should_stop:
                    exit_price = strategy.compute_stop_exit_price(pp.price)
                    self._close_position(
                        position, exit_price, pp.timestamp, ExitReason.HARD_STOP, is_taker=True
                    )
                    position = None
                    tier = None
                elif strategy.check_take_profit(pp.price):
                    from src.config import TAKE_PROFIT_PRICE
                    self._close_position(
                        position, TAKE_PROFIT_PRICE, pp.timestamp, ExitReason.TAKE_PROFIT
                    )
                    position = None
                    tier = None
                else:
                    # Update soft stop trigger state
                    position.soft_stop_triggered_at = pp.timestamp if new_trigger else None
                    continue

            # Entry checks — use shared strategy logic
            candidate_tier = strategy.check_entry_eligible(
                market, pp.price, hours_to_res,
                self.portfolio.open_positions, self.portfolio.cash,
            )
            if candidate_tier is None:
                continue

            self._open_position(market, pp.price, candidate_tier, pp.timestamp)
            position = self.portfolio.positions[-1]
            tier = candidate_tier

        # Settle remaining open position
        if position is not None and position.is_open:
            self._settle_position(position, market)

    def run(
        self, markets: list[Market], price_histories: dict[str, list[PricePoint]],
    ) -> None:
        total = len(markets)
        scanned = 0
        for i, market in enumerate(markets):
            prices = price_histories.get(market.token_id)
            if not prices:
                continue
            self.scan_market(market, prices)
            scanned += 1
            if (i + 1) % 200 == 0:
                logger.info(
                    "Scanned %d / %d markets, %d trades, capital: $%.2f",
                    i + 1, total, len(self.all_trades), self.portfolio.current_value,
                )
        logger.info("Backtest complete: %d markets scanned, %d trades", scanned, len(self.all_trades))
