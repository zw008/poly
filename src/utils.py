"""Shared utilities: logging setup, datetime parsing, formatting."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
) -> None:
    """Configure logging to console + optional file."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


_DATETIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S+00",
    "%Y-%m-%d %H:%M:%S+00:00",
    "%Y-%m-%dT%H:%M:%S+00:00",
    "%Y-%m-%d",
)


def parse_datetime(s: Optional[str]) -> Optional[datetime]:
    """Parse a datetime string in various Polymarket formats."""
    if not s:
        return None
    s_clean = s.strip()
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(s_clean, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def hours_until(target: datetime) -> float:
    """Return hours from now until target datetime."""
    now = datetime.now(timezone.utc)
    return (target - now).total_seconds() / 3600


def format_usd(amount: float) -> str:
    """Format dollar amount: $1,234.56."""
    return f"${amount:,.2f}"
