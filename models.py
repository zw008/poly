"""Data models for the backtest system."""

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
    token_id: str  # YES token
    question: str
    category: str
    volume: float
    end_date: datetime
    resolved_at: Optional[datetime]
    winning_outcome: Optional[str]  # "Yes" / "No" / None
    slug: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class Position:
    market: Market
    tier_name: str
    entry_price: float
    entry_time: datetime
    shares: float  # dollar amount invested / entry_price
    investment: float  # dollar amount invested
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[ExitReason] = None
    fees_paid: float = 0.0
    soft_stop_triggered_at: Optional[datetime] = None

    @property
    def is_open(self) -> bool:
        return self.exit_price is None

    @property
    def pnl(self) -> float:
        if self.exit_price is None:
            return 0.0
        gross = (self.exit_price - self.entry_price) * self.shares
        return gross - self.fees_paid

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
    def exposure_pct(self) -> float:
        current_capital = self.cash + self.total_exposure
        if current_capital <= 0:
            return 1.0
        return self.total_exposure / current_capital

    @property
    def current_value(self) -> float:
        return self.cash + self.total_exposure

    def count_by_category(self, category: str) -> int:
        return sum(
            1 for p in self.open_positions
            if p.market.category.lower() == category.lower()
        )

    def exposure_by_category(self, category: str) -> float:
        return sum(
            p.investment for p in self.open_positions
            if p.market.category.lower() == category.lower()
        )

    def exposure_by_super_category(self, super_cat_keywords: list[str]) -> float:
        total = 0.0
        for p in self.open_positions:
            cat_lower = p.market.category.lower()
            tags_lower = " ".join(p.market.tags).lower()
            combined = f"{cat_lower} {tags_lower}"
            if any(kw in combined for kw in super_cat_keywords):
                total += p.investment
        return total
