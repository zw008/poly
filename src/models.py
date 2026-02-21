"""Shared data models for backtest and live trading."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ExitReason(Enum):
    TAKE_PROFIT = "take_profit"
    SOFT_STOP = "soft_stop"
    HARD_STOP = "hard_stop"
    SETTLED_WIN = "settled_win"
    SETTLED_LOSS = "settled_loss"


@dataclass(frozen=True)
class PricePoint:
    timestamp: datetime
    price: float


@dataclass(frozen=True)
class Market:
    condition_id: str
    token_id: str
    question: str
    category: str
    volume: float
    end_date: datetime
    resolved_at: Optional[datetime]
    winning_outcome: Optional[str]
    slug: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class Position:
    market: Market
    tier_name: str
    entry_price: float
    entry_time: datetime
    shares: float
    investment: float
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[ExitReason] = None
    fees_paid: float = 0.0
    soft_stop_triggered_at: Optional[datetime] = None

    # Live trading order tracking
    entry_order_id: str = ""
    tp_order_id: str = ""
    exit_order_id: str = ""

    @property
    def is_open(self) -> bool:
        return self.exit_price is None

    @property
    def pnl(self) -> float:
        if self.exit_price is None:
            return 0.0
        return (self.exit_price - self.entry_price) * self.shares - self.fees_paid

    @property
    def pnl_pct(self) -> float:
        if self.investment == 0:
            return 0.0
        return self.pnl / self.investment

    @property
    def holding_hours(self) -> float:
        if self.exit_time is None or self.entry_time is None:
            return 0.0
        return (self.exit_time - self.entry_time).total_seconds() / 3600


@dataclass
class Portfolio:
    initial_capital: float
    cash: float = 0.0
    positions: list[Position] = field(default_factory=list)
    closed_positions: list[Position] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.cash == 0.0:
            self.cash = self.initial_capital

    @property
    def open_positions(self) -> list[Position]:
        return [p for p in self.positions if p.is_open]

    @property
    def total_exposure(self) -> float:
        return sum(p.investment for p in self.open_positions)

    @property
    def current_value(self) -> float:
        return self.cash + self.total_exposure

    def count_by_category(self, category: str) -> int:
        return sum(
            1 for p in self.open_positions
            if p.market.category.lower() == category.lower()
        )


# ---------------------------------------------------------------------------
# Live trading order models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OrderRequest:
    """Immutable order intent passed to executor."""
    token_id: str
    side: str  # "BUY" or "SELL"
    price: float
    size: float
    order_type: str = "GTC"  # GTC, GTD, FOK, FAK
    post_only: bool = True


@dataclass(frozen=True)
class OrderResult:
    """Immutable result from order placement."""
    order_id: str
    status: str  # LIVE, MATCHED, CANCELLED, FAILED, DRY_RUN
    filled_size: float = 0.0
    avg_fill_price: float = 0.0
