"""Pure strategy logic — shared by backtest and live trading.

All functions are pure (no side effects, no I/O, no state mutation).
This ensures backtest and live use identical decision logic.
"""

from __future__ import annotations

from typing import Optional

from src.config import (
    BLACKLIST_KEYWORDS,
    MAX_CONCURRENT_POSITIONS,
    MAX_SAME_CATEGORY,
    SLIPPAGE_TICKS,
    STOP_LOSS_REBOUND_MARGIN,
    STOP_LOSS_SLIPPAGE,
    SUPER_CATEGORIES,
    TAKE_PROFIT_PRICE,
    TIERS,
    TierConfig,
)
from src.models import Market, Position


def classify_tier(
    price: float, hours_to_resolution: float
) -> Optional[TierConfig]:
    """Return the matching tier config, or None."""
    for tier in TIERS:
        if (
            tier.price_low <= price <= tier.price_high
            and 0 < hours_to_resolution <= tier.max_hours_to_resolution
        ):
            return tier
    return None


def check_entry_eligible(
    market: Market,
    price: float,
    hours_to_resolution: float,
    open_positions: list[Position],
    available_cash: float,
) -> Optional[TierConfig]:
    """Check all entry conditions. Return tier if eligible, None otherwise."""
    # Tier match
    tier = classify_tier(price, hours_to_resolution)
    if tier is None:
        return None

    # Position limit
    if len(open_positions) >= MAX_CONCURRENT_POSITIONS:
        return None

    # Duplicate check
    if any(p.market.token_id == market.token_id for p in open_positions):
        return None

    # Cash check
    if available_cash < tier.position_size_usd:
        return None

    # Category check
    cat_count = sum(
        1 for p in open_positions
        if p.market.category.lower() == market.category.lower()
    )
    if cat_count >= MAX_SAME_CATEGORY:
        return None

    # Super-category check
    for _name, keywords in SUPER_CATEGORIES.items():
        combined = f"{market.category.lower()} {' '.join(market.tags).lower()} {market.question.lower()}"
        if any(kw in combined for kw in keywords):
            count = 0
            for p in open_positions:
                p_combined = (
                    f"{p.market.category.lower()} "
                    f"{' '.join(p.market.tags).lower()} "
                    f"{p.market.question.lower()}"
                )
                if any(kw in p_combined for kw in keywords):
                    count += 1
            if count >= MAX_SAME_CATEGORY:
                return None
            break

    return tier


def check_take_profit(price: float) -> bool:
    """Return True if price >= TP threshold."""
    return price >= TAKE_PROFIT_PRICE


def check_hard_stop(
    price: float,
    tier: TierConfig,
    soft_stop_triggered: bool,
    next_price: Optional[float] = None,
) -> tuple[bool, bool]:
    """Check hard stop condition.

    Returns (should_exit, new_soft_stop_triggered).
    """
    if price >= tier.hard_stop_loss:
        return False, False

    # Price below L2
    if not soft_stop_triggered:
        return False, True  # First breach, wait for confirmation

    # Already triggered — check recovery
    rebound_target = tier.hard_stop_loss + STOP_LOSS_REBOUND_MARGIN
    if next_price is not None and next_price >= rebound_target:
        return False, False  # Recovered

    # Confirmed stop
    return True, True


def compute_entry_price(market_price: float, price_high: float) -> float:
    """Tick-sniping: bid + 0.001, capped at tier ceiling."""
    return min(market_price + SLIPPAGE_TICKS, price_high)


def compute_stop_exit_price(price: float) -> float:
    """Emergency taker exit price with slippage."""
    return max(price - STOP_LOSS_SLIPPAGE, 0.01)


def is_blacklisted(question: str, tags: list[str]) -> bool:
    """Check if market matches any blacklist keywords."""
    combined = f"{question} {' '.join(tags)}".lower()
    return any(kw in combined for kw in BLACKLIST_KEYWORDS)
