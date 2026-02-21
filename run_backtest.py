#!/usr/bin/env python3
"""Main entry point — run the Polymarket V5.1 Tail-End Arb backtest."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.backtest.analytics import PerformanceAnalyzer, plot_equity_curve
from src.backtest.engine import BacktestEngine
from src.backtest.data_fetcher import fetch_all_price_histories, fetch_resolved_markets

OUTPUT_DIR = Path(__file__).parent / "output"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket V5.0 Production Tail-End Arb Backtest")
    parser.add_argument("--capital", type=float, default=10_000.0, help="Initial capital in USD")
    parser.add_argument("--pages", type=int, default=100, help="Max pages to fetch from Gamma API")
    parser.add_argument("--refresh", action="store_true", help="Force re-fetch data from APIs")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    # --- Step 1: Fetch markets ---
    logger.info("Step 1: Fetching resolved markets...")
    markets = fetch_resolved_markets(max_pages=args.pages, force_refresh=args.refresh)
    if not markets:
        logger.error("No markets fetched. Check API connectivity.")
        sys.exit(1)
    logger.info("Got %d resolved binary markets", len(markets))

    # --- Step 2: Fetch price histories ---
    logger.info("Step 2: Fetching price histories...")
    price_histories = fetch_all_price_histories(markets, force_refresh=args.refresh)
    logger.info("Got price data for %d markets", len(price_histories))

    # --- Step 3: Run backtest ---
    logger.info("Step 3: Running backtest with $%.2f initial capital...", args.capital)
    engine = BacktestEngine(initial_capital=args.capital)
    engine.run(markets, price_histories)

    # --- Build equity curve from trade events ---
    # Track portfolio value after each trade
    if engine.all_trades:
        sorted_trades = sorted(engine.all_trades, key=lambda t: t.exit_time or t.entry_time)
        running_capital = args.capital
        engine.portfolio.equity_curve.append(
            (sorted_trades[0].entry_time, args.capital)
        )
        for trade in sorted_trades:
            running_capital += trade.pnl
            ts = trade.exit_time or trade.entry_time
            engine.portfolio.equity_curve.append((ts, running_capital))

    # --- Step 4: Analyze ---
    logger.info("Step 4: Generating report...")
    analyzer = PerformanceAnalyzer(
        portfolio=engine.portfolio,
        all_trades=engine.all_trades,
        initial_capital=args.capital,
    )

    report = analyzer.summary_text()
    print("\n" + report)

    # Save report
    report_path = OUTPUT_DIR / "report.txt"
    report_path.write_text(report)
    logger.info("Report saved to %s", report_path)

    # Plot equity curve
    if engine.portfolio.equity_curve:
        plot_path = str(OUTPUT_DIR / "equity_curve.png")
        plot_equity_curve(engine.portfolio.equity_curve, plot_path)

    logger.info("Done.")


if __name__ == "__main__":
    main()
