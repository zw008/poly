"""Core backtest engine — V5.1 Tier A Only + Hard Stop 0.85 simulation."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from config import (
    BLACKLIST_KEYWORDS,
    MAKER_FEE_PCT,
    MAX_CONCURRENT_POSITIONS,
    MAX_SAME_CATEGORY,
    SLIPPAGE_TICKS,
    STOP_LOSS_REBOUND_MARGIN,
    STOP_LOSS_SLIPPAGE,
    SUPER_CATEGORIES,
    TAKE_PROFIT_PRICE,
    TAKER_FEE_PCT,
    TIERS,
    TierConfig,
)
from models import ExitReason, Market, Portfolio, Position, PricePoint

logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(self, initial_capital: float = 10_000.0) -> None:
        self.portfolio = Portfolio(initial_capital=initial_capital)
        self.all_trades: list[Position] = []

    # ------------------------------------------------------------------
    # Tier classification
    # ------------------------------------------------------------------

    def classify_tier(
        self, price: float, hours_to_resolution: float
    ) -> Optional[TierConfig]:
        """Return the tier config if the price/time qualifies, else None."""
        for tier in TIERS:
            if (
                tier.price_low <= price <= tier.price_high
                and 0 < hours_to_resolution <= tier.max_hours_to_resolution
            ):
                return tier
        return None

    # ------------------------------------------------------------------
    # Risk checks
    # ------------------------------------------------------------------

    def _passes_position_limit(self) -> bool:
        return len(self.portfolio.open_positions) < MAX_CONCURRENT_POSITIONS

    def _passes_category_check(self, market: Market) -> bool:
        """Max 5 concurrent positions in same category."""
        if self.portfolio.count_by_category(market.category) >= MAX_SAME_CATEGORY:
            return False
        # Also check super-category: max 5 in same super-cat
        for _name, keywords in SUPER_CATEGORIES.items():
            q_lower = market.question.lower()
            cat_lower = market.category.lower()
            tags_lower = " ".join(market.tags).lower()
            combined = f"{cat_lower} {tags_lower} {q_lower}"
            if any(kw in combined for kw in keywords):
                count = 0
                for p in self.portfolio.open_positions:
                    p_combined = (
                        f"{p.market.category.lower()} "
                        f"{' '.join(p.market.tags).lower()} "
                        f"{p.market.question.lower()}"
                    )
                    if any(kw in p_combined for kw in keywords):
                        count += 1
                if count >= MAX_SAME_CATEGORY:
                    return False
                break
        return True

    def _already_has_position(self, market: Market) -> bool:
        return any(
            p.market.token_id == market.token_id
            for p in self.portfolio.open_positions
        )

    def _has_enough_cash(self, tier: TierConfig) -> bool:
        return self.portfolio.cash >= tier.position_size_usd

    # ------------------------------------------------------------------
    # Trade execution
    # ------------------------------------------------------------------

    def _open_position(
        self,
        market: Market,
        price: float,
        tier: TierConfig,
        timestamp: datetime,
    ) -> None:
        """Open position: Maker Post-Only entry with tick-sniping."""
        investment = tier.position_size_usd
        # Tick-sniping: entry at price + 0.001 (we improve the bid)
        entry_price = min(price + SLIPPAGE_TICKS, tier.price_high)
        shares = investment / entry_price
        entry_fee = investment * MAKER_FEE_PCT  # 0%

        pos = Position(
            market=market,
            tier_name=tier.name,
            entry_price=entry_price,
            entry_time=timestamp,
            shares=shares,
            investment=investment,
            fees_paid=entry_fee,
        )

        self.portfolio.cash -= investment
        self.portfolio.positions.append(pos)

    def _close_position(
        self,
        pos: Position,
        exit_price: float,
        exit_time: datetime,
        reason: ExitReason,
        is_taker: bool = False,
    ) -> None:
        """Close position and return proceeds."""
        pos.exit_price = exit_price
        pos.exit_time = exit_time
        pos.exit_reason = reason

        exit_value = pos.shares * exit_price
        fee = exit_value * (TAKER_FEE_PCT if is_taker else MAKER_FEE_PCT)
        pos.fees_paid += fee

        proceeds = exit_value - fee
        self.portfolio.cash += proceeds
        self.portfolio.closed_positions.append(pos)
        self.portfolio.positions.remove(pos)
        self.all_trades.append(pos)

    # ------------------------------------------------------------------
    # Exit checks (L1 / L2 / TP)
    # ------------------------------------------------------------------

    def _check_take_profit(
        self, pos: Position, price: float, timestamp: datetime
    ) -> bool:
        """TP at 0.99 — Maker limit sell, 0% fee."""
        if price >= TAKE_PROFIT_PRICE:
            self._close_position(
                pos, TAKE_PROFIT_PRICE, timestamp, ExitReason.TAKE_PROFIT, is_taker=False
            )
            return True
        return False

    def _check_hard_stop(
        self, pos: Position, price: float, timestamp: datetime,
        next_price: Optional[float], tier: TierConfig,
    ) -> bool:
        """L2 hard stop with 1-candle confirmation (proxy for 30s confirm)."""
        if price >= tier.hard_stop_loss:
            # Above L2 — clear trigger
            pos.soft_stop_triggered_at = None
            return False

        # Price below L2 line
        if pos.soft_stop_triggered_at is None:
            # First breach — set trigger, wait for confirmation
            pos.soft_stop_triggered_at = timestamp
            return False

        # Already triggered — check if next candle recovers
        rebound_target = tier.hard_stop_loss + STOP_LOSS_REBOUND_MARGIN
        if next_price is not None and next_price >= rebound_target:
            pos.soft_stop_triggered_at = None
            return False

        # Confirmed L2: emergency taker exit with slippage
        exit_price = max(price - STOP_LOSS_SLIPPAGE, 0.01)
        self._close_position(
            pos, exit_price, timestamp, ExitReason.HARD_STOP, is_taker=True
        )
        return True

    # ------------------------------------------------------------------
    # Settlement
    # ------------------------------------------------------------------

    def _settle_position(self, pos: Position, market: Market) -> None:
        resolved_at = market.resolved_at or market.end_date
        winning = (market.winning_outcome or "").lower()
        if winning in ("yes", "y", "1", "true"):
            self._close_position(
                pos, 1.00, resolved_at, ExitReason.SETTLED_WIN, is_taker=False
            )
        else:
            self._close_position(
                pos, 0.00, resolved_at, ExitReason.SETTLED_LOSS, is_taker=False
            )

    # ------------------------------------------------------------------
    # Main scan loop
    # ------------------------------------------------------------------

    def scan_market(
        self,
        market: Market,
        prices: list[PricePoint],
    ) -> None:
        if not prices or not market.resolved_at:
            return

        position: Optional[Position] = None
        tier: Optional[TierConfig] = None

        for i, pp in enumerate(prices):
            hours_to_res = (market.resolved_at - pp.timestamp).total_seconds() / 3600
            if hours_to_res < 0:
                continue

            next_price = prices[i + 1].price if i + 1 < len(prices) else None

            # --- Exit checks ---
            if position is not None and position.is_open:
                assert tier is not None

                if self._check_hard_stop(position, pp.price, pp.timestamp, next_price, tier):
                    position = None
                    tier = None
                elif self._check_take_profit(position, pp.price, pp.timestamp):
                    position = None
                    tier = None
                else:
                    continue  # holding

            # --- Entry checks ---
            if self._already_has_position(market):
                continue

            candidate_tier = self.classify_tier(pp.price, hours_to_res)
            if candidate_tier is None:
                continue

            if not self._passes_position_limit():
                continue

            if not self._passes_category_check(market):
                continue

            if not self._has_enough_cash(candidate_tier):
                continue

            self._open_position(market, pp.price, candidate_tier, pp.timestamp)
            position = self.portfolio.positions[-1]
            tier = candidate_tier

        # End of price history: settle open positions
        if position is not None and position.is_open:
            self._settle_position(position, market)
            position = None

    def run(
        self,
        markets: list[Market],
        price_histories: dict[str, list[PricePoint]],
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
                    "Scanned %d / %d markets, %d trades so far, capital: $%.2f",
                    i + 1, total, len(self.all_trades), self.portfolio.current_value,
                )

        logger.info(
            "Backtest complete: scanned %d markets, %d trades executed",
            scanned, len(self.all_trades),
        )
