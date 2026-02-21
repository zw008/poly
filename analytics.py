"""Performance analytics and reporting for backtest results."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from models import ExitReason, Portfolio, Position

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    def __init__(
        self,
        portfolio: Portfolio,
        all_trades: list[Position],
        initial_capital: float,
    ) -> None:
        self.portfolio = portfolio
        self.trades = all_trades
        self.initial_capital = initial_capital

    # ------------------------------------------------------------------
    # Core metrics
    # ------------------------------------------------------------------

    @property
    def final_value(self) -> float:
        return self.portfolio.current_value

    @property
    def total_return(self) -> float:
        if self.initial_capital == 0:
            return 0.0
        return (self.final_value - self.initial_capital) / self.initial_capital

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def winning_trades(self) -> list[Position]:
        return [t for t in self.trades if t.pnl > 0]

    @property
    def losing_trades(self) -> list[Position]:
        return [t for t in self.trades if t.pnl <= 0]

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return len(self.winning_trades) / len(self.trades)

    @property
    def avg_win(self) -> float:
        wins = self.winning_trades
        if not wins:
            return 0.0
        return np.mean([t.pnl for t in wins])

    @property
    def avg_loss(self) -> float:
        losses = self.losing_trades
        if not losses:
            return 0.0
        return np.mean([t.pnl for t in losses])

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.pnl for t in self.winning_trades)
        gross_loss = abs(sum(t.pnl for t in self.losing_trades))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    @property
    def avg_holding_hours(self) -> float:
        if not self.trades:
            return 0.0
        return np.mean([t.holding_hours for t in self.trades])

    @property
    def total_fees(self) -> float:
        return sum(t.fees_paid for t in self.trades)

    # ------------------------------------------------------------------
    # Equity curve metrics
    # ------------------------------------------------------------------

    def _daily_returns(self) -> list[float]:
        """Compute daily returns from the equity curve."""
        curve = self.portfolio.equity_curve
        if len(curve) < 2:
            return []
        values = [v for _, v in curve]
        returns = []
        for i in range(1, len(values)):
            if values[i - 1] > 0:
                returns.append((values[i] - values[i - 1]) / values[i - 1])
        return returns

    @property
    def max_drawdown(self) -> float:
        """Maximum drawdown as a fraction."""
        curve = self.portfolio.equity_curve
        if not curve:
            # Fall back to trade-level approximation
            return self._trade_level_max_drawdown()
        values = [v for _, v in curve]
        peak = values[0]
        max_dd = 0.0
        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    def _trade_level_max_drawdown(self) -> float:
        """Approximate max drawdown from trade sequence."""
        if not self.trades:
            return 0.0
        capital = self.initial_capital
        peak = capital
        max_dd = 0.0
        for t in sorted(self.trades, key=lambda x: x.exit_time or x.entry_time):
            capital += t.pnl
            if capital > peak:
                peak = capital
            dd = (peak - capital) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    def annualized_return(self, days: Optional[int] = None) -> float:
        if days is None:
            if self.trades:
                times = [t.entry_time for t in self.trades] + [
                    t.exit_time for t in self.trades if t.exit_time
                ]
                span = (max(times) - min(times)).days
                days = max(span, 1)
            else:
                days = 365
        if days == 0:
            return 0.0
        return (1 + self.total_return) ** (365 / days) - 1

    def sharpe_ratio(self, risk_free_rate: float = 0.05) -> float:
        daily_returns = self._daily_returns()
        if len(daily_returns) < 2:
            return 0.0
        daily_rf = risk_free_rate / 365
        excess = [r - daily_rf for r in daily_returns]
        std = np.std(excess, ddof=1)
        if std == 0:
            return 0.0
        return float(np.sqrt(365) * np.mean(excess) / std)

    def sortino_ratio(self, risk_free_rate: float = 0.05) -> float:
        daily_returns = self._daily_returns()
        if len(daily_returns) < 2:
            return 0.0
        daily_rf = risk_free_rate / 365
        excess = [r - daily_rf for r in daily_returns]
        downside = [r for r in excess if r < 0]
        if not downside:
            return float("inf") if np.mean(excess) > 0 else 0.0
        downside_std = np.std(downside, ddof=1)
        if downside_std == 0:
            return 0.0
        return float(np.sqrt(365) * np.mean(excess) / downside_std)

    # ------------------------------------------------------------------
    # Breakdown by tier / category / exit reason
    # ------------------------------------------------------------------

    def by_tier(self) -> dict[str, dict]:
        groups: dict[str, list[Position]] = defaultdict(list)
        for t in self.trades:
            groups[t.tier_name].append(t)
        return {name: self._group_stats(trades) for name, trades in sorted(groups.items())}

    def by_category(self) -> dict[str, dict]:
        groups: dict[str, list[Position]] = defaultdict(list)
        for t in self.trades:
            groups[t.market.category].append(t)
        return {name: self._group_stats(trades) for name, trades in sorted(groups.items())}

    def by_exit_reason(self) -> dict[str, dict]:
        groups: dict[str, list[Position]] = defaultdict(list)
        for t in self.trades:
            reason = t.exit_reason.value if t.exit_reason else "unknown"
            groups[reason].append(t)
        return {name: self._group_stats(trades) for name, trades in sorted(groups.items())}

    def _group_stats(self, trades: list[Position]) -> dict:
        if not trades:
            return {"count": 0}
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        pnls = [t.pnl for t in trades]
        return {
            "count": len(trades),
            "win_rate": len(wins) / len(trades) if trades else 0.0,
            "total_pnl": sum(pnls),
            "avg_pnl": float(np.mean(pnls)),
            "avg_pnl_pct": float(np.mean([t.pnl_pct for t in trades])),
            "avg_holding_hours": float(np.mean([t.holding_hours for t in trades])),
            "total_fees": sum(t.fees_paid for t in trades),
        }

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def summary_text(self) -> str:
        lines = [
            "=" * 60,
            "  POLYMARKET V5.1 — BACKTEST REPORT",
            "=" * 60,
            "",
            "--- Portfolio Summary ---",
            f"  Initial Capital:    ${self.initial_capital:,.2f}",
            f"  Final Value:        ${self.final_value:,.2f}",
            f"  Total Return:       {self.total_return:+.2%}",
            f"  Annualized Return:  {self.annualized_return():+.2%}",
            f"  Max Drawdown:       {self.max_drawdown:.2%}",
            f"  Sharpe Ratio:       {self.sharpe_ratio():.2f}",
            f"  Sortino Ratio:      {self.sortino_ratio():.2f}",
            "",
            "--- Trade Summary ---",
            f"  Total Trades:       {self.total_trades}",
            f"  Win Rate:           {self.win_rate:.2%}",
            f"  Avg Win:            ${self.avg_win:,.2f}",
            f"  Avg Loss:           ${self.avg_loss:,.2f}",
            f"  Profit Factor:      {self.profit_factor:.2f}",
            f"  Avg Holding:        {self.avg_holding_hours:.1f} hours",
            f"  Total Fees Paid:    ${self.total_fees:,.2f}",
            "",
        ]

        # Tier breakdown
        tier_data = self.by_tier()
        if tier_data:
            lines.append("--- By Tier ---")
            for name, stats in tier_data.items():
                lines.append(
                    f"  {name:8s}  trades={stats['count']:4d}  "
                    f"winrate={stats['win_rate']:.1%}  "
                    f"pnl=${stats['total_pnl']:+,.2f}  "
                    f"avg_pnl={stats['avg_pnl_pct']:+.2%}  "
                    f"avg_hold={stats['avg_holding_hours']:.1f}h"
                )
            lines.append("")

        # Exit reason breakdown
        exit_data = self.by_exit_reason()
        if exit_data:
            lines.append("--- By Exit Reason ---")
            for reason, stats in exit_data.items():
                lines.append(
                    f"  {reason:15s}  count={stats['count']:4d}  "
                    f"pnl=${stats['total_pnl']:+,.2f}"
                )
            lines.append("")

        # Top categories
        cat_data = self.by_category()
        if cat_data:
            lines.append("--- Top Categories (by trade count) ---")
            sorted_cats = sorted(cat_data.items(), key=lambda x: x[1]["count"], reverse=True)
            for name, stats in sorted_cats[:10]:
                lines.append(
                    f"  {name:20s}  trades={stats['count']:4d}  "
                    f"winrate={stats['win_rate']:.1%}  "
                    f"pnl=${stats['total_pnl']:+,.2f}"
                )
            lines.append("")

        # Sample trades
        if self.trades:
            lines.append("--- Sample Trades (last 10) ---")
            recent = sorted(self.trades, key=lambda t: t.exit_time or t.entry_time)[-10:]
            for t in recent:
                reason = t.exit_reason.value if t.exit_reason else "?"
                lines.append(
                    f"  [{t.tier_name}] {t.market.question[:50]:50s}  "
                    f"entry={t.entry_price:.3f}  exit={t.exit_price:.3f}  "
                    f"pnl={t.pnl_pct:+.2%}  reason={reason}"
                )
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)


def plot_equity_curve(
    equity_curve: list[tuple[datetime, float]],
    output_path: str,
) -> None:
    """Plot and save the equity curve."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    if not equity_curve:
        logger.warning("No equity curve data to plot")
        return

    dates = [d for d, _ in equity_curve]
    values = [v for _, v in equity_curve]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1])
    fig.suptitle("Polymarket Tail-End Arb V5.1 — Equity Curve", fontsize=14, fontweight="bold")

    # Equity curve
    ax1.plot(dates, values, color="#2196F3", linewidth=1.5, label="Portfolio Value")
    ax1.fill_between(dates, values[0], values, alpha=0.1, color="#2196F3")
    ax1.set_ylabel("Portfolio Value ($)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Drawdown
    peak = values[0]
    drawdowns = []
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0
        drawdowns.append(-dd)
    ax2.fill_between(dates, 0, drawdowns, color="#F44336", alpha=0.4, label="Drawdown")
    ax2.set_ylabel("Drawdown")
    ax2.set_xlabel("Date")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Equity curve saved to %s", output_path)
