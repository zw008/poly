"""Risk management — circuit breaker and exposure tracking."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.config import (
    CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES,
    CIRCUIT_BREAKER_MAX_LOSS_PCT,
    CIRCUIT_BREAKER_MAX_LOSS_USD,
)

logger = logging.getLogger(__name__)


@dataclass
class RiskManager:
    """Track PnL and trigger circuit breaker when thresholds are exceeded."""

    initial_capital: float
    realized_pnl: float = 0.0
    consecutive_losses: int = 0
    total_trades: int = 0
    tripped: bool = False
    tripped_at: datetime | None = None
    _trade_log: list[float] = field(default_factory=list)

    def record_trade(self, pnl: float) -> None:
        """Record a completed trade and check circuit breaker conditions."""
        self.realized_pnl += pnl
        self.total_trades += 1
        self._trade_log.append(pnl)

        if pnl <= 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        if self._should_trip():
            self.tripped = True
            self.tripped_at = datetime.now(timezone.utc)
            logger.warning(
                "CIRCUIT BREAKER TRIPPED — pnl=$%.2f, consecutive_losses=%d",
                self.realized_pnl,
                self.consecutive_losses,
            )

    def _should_trip(self) -> bool:
        """Check if any circuit breaker condition is met."""
        if self.tripped:
            return True

        # Absolute loss threshold
        if self.realized_pnl <= -CIRCUIT_BREAKER_MAX_LOSS_USD:
            logger.warning(
                "Circuit breaker: loss $%.2f exceeds max $%.2f",
                abs(self.realized_pnl),
                CIRCUIT_BREAKER_MAX_LOSS_USD,
            )
            return True

        # Percentage loss threshold
        if self.initial_capital > 0:
            loss_pct = abs(self.realized_pnl) / self.initial_capital
            if self.realized_pnl < 0 and loss_pct >= CIRCUIT_BREAKER_MAX_LOSS_PCT:
                logger.warning(
                    "Circuit breaker: loss %.1f%% exceeds max %.1f%%",
                    loss_pct * 100,
                    CIRCUIT_BREAKER_MAX_LOSS_PCT * 100,
                )
                return True

        # Consecutive losses
        if self.consecutive_losses >= CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES:
            logger.warning(
                "Circuit breaker: %d consecutive losses exceeds max %d",
                self.consecutive_losses,
                CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES,
            )
            return True

        return False

    @property
    def can_open_position(self) -> bool:
        """Whether it's safe to open new positions."""
        return not self.tripped

    def status_text(self) -> str:
        """Human-readable risk status."""
        status = "TRIPPED" if self.tripped else "OK"
        return (
            f"Risk[{status}] pnl=${self.realized_pnl:+.2f} "
            f"trades={self.total_trades} "
            f"consec_losses={self.consecutive_losses}"
        )

    def reset(self) -> None:
        """Reset circuit breaker (manual intervention)."""
        self.tripped = False
        self.tripped_at = None
        self.consecutive_losses = 0
        logger.info("Circuit breaker reset manually")
