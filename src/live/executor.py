"""Order executor — manages order lifecycle for entry, take-profit, and stop-loss."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from src.config import MAKER_FEE_PCT, TAKE_PROFIT_PRICE, TierConfig
from src.models import ExitReason, Market, OrderRequest, OrderResult, Position
from src.strategy import compute_entry_price, compute_stop_exit_price
from src.live.client import ClobClient
from src.live.risk import RiskManager

logger = logging.getLogger(__name__)


class OrderExecutor:
    """Manages the full order lifecycle for positions."""

    def __init__(
        self,
        client: ClobClient,
        risk_manager: RiskManager,
        initial_capital: float,
    ) -> None:
        self.client = client
        self.risk = risk_manager
        self.cash = initial_capital
        self.positions: list[Position] = []
        self.closed_positions: list[Position] = []

    @property
    def open_positions(self) -> list[Position]:
        return [p for p in self.positions if p.is_open]

    def open_position(
        self,
        market: Market,
        bid_price: float,
        tier: TierConfig,
    ) -> Optional[Position]:
        """Open a new position: place BUY order + TP SELL order."""
        if not self.risk.can_open_position:
            logger.warning("Circuit breaker active — skipping entry for %s", market.question[:40])
            return None

        if self.cash < tier.position_size_usd:
            logger.info("Insufficient cash ($%.2f) for position size $%.2f", self.cash, tier.position_size_usd)
            return None

        entry_price = compute_entry_price(bid_price, tier.price_high)
        shares = tier.position_size_usd / entry_price

        # Place BUY order
        buy_order = self.client.place_order(OrderRequest(
            token_id=market.token_id,
            side="BUY",
            price=entry_price,
            size=shares,
            order_type="GTC",
            post_only=True,
        ))

        if buy_order.status in ("FAILED",):
            logger.warning("Buy order failed for %s", market.question[:40])
            return None

        now = datetime.now(timezone.utc)
        pos = Position(
            market=market,
            tier_name=tier.name,
            entry_price=entry_price,
            entry_time=now,
            shares=shares,
            investment=tier.position_size_usd,
            fees_paid=tier.position_size_usd * MAKER_FEE_PCT,
            entry_order_id=buy_order.order_id,
        )

        # Place take-profit SELL order
        tp_order = self.client.place_order(OrderRequest(
            token_id=market.token_id,
            side="SELL",
            price=TAKE_PROFIT_PRICE,
            size=shares,
            order_type="GTC",
            post_only=True,
        ))
        pos.tp_order_id = tp_order.order_id

        self.cash -= tier.position_size_usd
        self.positions.append(pos)

        logger.info(
            "OPENED: %s @ %.3f, shares=%.2f, TP order=%s",
            market.question[:40],
            entry_price,
            shares,
            tp_order.order_id,
        )
        return pos

    def close_position(
        self,
        pos: Position,
        exit_price: float,
        reason: ExitReason,
        is_taker: bool = False,
    ) -> None:
        """Close a position: cancel TP order, place market SELL if needed."""
        # Cancel existing TP order
        if pos.tp_order_id:
            self.client.cancel_order(pos.tp_order_id)

        if reason in (ExitReason.HARD_STOP,):
            # Emergency taker exit
            stop_price = compute_stop_exit_price(exit_price)
            self.client.place_order(OrderRequest(
                token_id=pos.market.token_id,
                side="SELL",
                price=stop_price,
                size=pos.shares,
                order_type="FOK",
                post_only=False,
            ))
            exit_price = stop_price

        now = datetime.now(timezone.utc)
        pos.exit_price = exit_price
        pos.exit_time = now
        pos.exit_reason = reason

        from src.config import TAKER_FEE_PCT

        exit_value = pos.shares * exit_price
        fee = exit_value * (TAKER_FEE_PCT if is_taker else MAKER_FEE_PCT)
        pos.fees_paid += fee

        self.cash += exit_value - fee
        self.positions.remove(pos)
        self.closed_positions.append(pos)

        # Record PnL in risk manager
        self.risk.record_trade(pos.pnl)

        logger.info(
            "CLOSED [%s]: %s @ %.3f, pnl=$%.2f (%+.2f%%)",
            reason.value,
            pos.market.question[:40],
            exit_price,
            pos.pnl,
            pos.pnl_pct * 100,
        )

    def cancel_all_tp_orders(self) -> None:
        """Cancel all take-profit orders (for graceful shutdown)."""
        for pos in self.open_positions:
            if pos.tp_order_id:
                self.client.cancel_order(pos.tp_order_id)
                logger.info("Cancelled TP for %s", pos.market.question[:30])
