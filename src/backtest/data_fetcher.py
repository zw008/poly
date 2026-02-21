"""Fetch historical data from Polymarket APIs with local caching."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from src.config import (
    CLOB_API_BASE,
    FETCH_DELAY_SECONDS,
    GAMMA_API_BASE,
    MIN_MARKET_VOLUME,
    PRICE_FIDELITY_MINUTES,
)
from src.models import Market, PricePoint
from src.strategy import is_blacklisted
from src.utils import parse_datetime

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
MARKETS_CACHE = DATA_DIR / "markets.json"
PRICES_DIR = DATA_DIR / "prices"


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    PRICES_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Gamma API — resolved binary markets
# ---------------------------------------------------------------------------

def fetch_resolved_markets(
    max_pages: int = 20,
    force_refresh: bool = False,
) -> list[Market]:
    """Fetch resolved binary markets from Gamma API with caching."""
    _ensure_dirs()

    if MARKETS_CACHE.exists() and not force_refresh:
        logger.info("Loading cached markets from %s", MARKETS_CACHE)
        with open(MARKETS_CACHE) as f:
            raw_markets = json.load(f)
        return _parse_markets(raw_markets)

    logger.info("Fetching resolved markets from Gamma API...")
    all_raw: list[dict] = []
    offset = 0
    limit = 100

    for page in range(max_pages):
        url = (
            f"{GAMMA_API_BASE}/markets"
            f"?closed=true&limit={limit}&offset={offset}"
            f"&order=endDate&ascending=false"
        )
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            batch = resp.json()
        except (requests.RequestException, json.JSONDecodeError) as exc:
            logger.warning("Gamma API error at offset %d: %s", offset, exc)
            break

        if not batch:
            break

        all_raw.extend(batch)
        logger.info("  page %d: fetched %d markets (total %d)", page + 1, len(batch), len(all_raw))
        offset += limit
        time.sleep(FETCH_DELAY_SECONDS * 5)  # respect rate limit for /markets

    # Cache raw data
    with open(MARKETS_CACHE, "w") as f:
        json.dump(all_raw, f)
    logger.info("Cached %d raw markets to %s", len(all_raw), MARKETS_CACHE)

    return _parse_markets(all_raw)


def _parse_json_field(val: object) -> list:
    """Parse a field that may be a JSON string or already a list."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def _infer_winning_outcome(outcomes: list[str], outcome_prices: list[str]) -> str:
    """Infer winning outcome from outcomePrices when winningOutcome is absent."""
    if len(outcomes) != 2 or len(outcome_prices) != 2:
        return ""
    try:
        p0 = float(outcome_prices[0])
        p1 = float(outcome_prices[1])
    except (ValueError, TypeError):
        return ""
    # Resolved market: one price is ~1.0 and the other ~0.0
    if p0 > 0.99:
        return outcomes[0]
    if p1 > 0.99:
        return outcomes[1]
    return ""


def _parse_markets(raw_list: list[dict]) -> list[Market]:
    markets: list[Market] = []
    for raw in raw_list:
        # Only binary markets with clear resolution
        outcomes = _parse_json_field(raw.get("outcomes"))
        if len(outcomes) != 2:
            continue
        if not any(str(o).lower() == "yes" for o in outcomes):
            continue

        volume = float(raw.get("volumeNum") or raw.get("volume") or 0)
        if volume < MIN_MARKET_VOLUME:
            continue

        # Must be closed
        if not raw.get("closed"):
            continue

        question = raw.get("question") or ""
        tags_raw = raw.get("tags") or []
        if isinstance(tags_raw, str):
            try:
                tags_raw = json.loads(tags_raw)
            except (json.JSONDecodeError, ValueError):
                tags_raw = []
        if not isinstance(tags_raw, list):
            tags_raw = []
        tags = [t.get("label", "") if isinstance(t, dict) else str(t) for t in tags_raw]
        category = tags[0] if tags else raw.get("groupItemTitle") or "other"

        if is_blacklisted(question, tags):
            continue

        # Get clob token IDs — YES token is first
        clob_ids = _parse_json_field(raw.get("clobTokenIds"))
        if not clob_ids:
            continue
        yes_token_id = str(clob_ids[0])  # first token is YES

        # Parse winning outcome
        winning = raw.get("winningOutcome") or raw.get("outcome") or ""
        if not winning:
            outcome_prices = _parse_json_field(raw.get("outcomePrices"))
            winning = _infer_winning_outcome(
                [str(o) for o in outcomes], [str(p) for p in outcome_prices]
            )
        if not winning:
            continue  # Can't determine resolution

        end_date = parse_datetime(raw.get("endDate"))
        resolved_at = parse_datetime(
            raw.get("resolvedAt") or raw.get("closedTime")
        )

        if not end_date or not resolved_at:
            continue

        markets.append(Market(
            condition_id=raw.get("conditionId") or str(raw.get("id") or ""),
            token_id=yes_token_id,
            question=question,
            category=category if isinstance(category, str) else "other",
            volume=volume,
            end_date=end_date,
            resolved_at=resolved_at,
            winning_outcome=winning,
            slug=raw.get("slug") or "",
            tags=tags,
        ))

    logger.info("Parsed %d valid binary markets", len(markets))
    return markets


# ---------------------------------------------------------------------------
# CLOB API — price history per token
# ---------------------------------------------------------------------------

def fetch_price_history(
    token_id: str,
    force_refresh: bool = False,
) -> list[PricePoint]:
    """Fetch hourly price history for a token from CLOB API."""
    _ensure_dirs()
    cache_file = PRICES_DIR / f"{token_id}.json"

    if cache_file.exists() and not force_refresh:
        with open(cache_file) as f:
            raw = json.load(f)
        return _parse_price_history(raw)

    url = (
        f"{CLOB_API_BASE}/prices-history"
        f"?market={token_id}&interval=max&fidelity={PRICE_FIDELITY_MINUTES}"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        logger.warning("CLOB price history error for %s: %s", token_id, exc)
        return []

    history = data.get("history") or data if isinstance(data, list) else []
    if isinstance(data, dict) and "history" in data:
        history = data["history"]

    with open(cache_file, "w") as f:
        json.dump(history, f)

    time.sleep(FETCH_DELAY_SECONDS)
    return _parse_price_history(history)


def _parse_price_history(raw: list[dict]) -> list[PricePoint]:
    points: list[PricePoint] = []
    for item in raw:
        t = item.get("t")
        p = item.get("p")
        if t is None or p is None:
            continue
        try:
            ts = datetime.fromtimestamp(int(t), tz=timezone.utc)
            price = float(p)
            points.append(PricePoint(timestamp=ts, price=price))
        except (ValueError, OSError):
            continue
    points.sort(key=lambda x: x.timestamp)
    return points


# ---------------------------------------------------------------------------
# Convenience: batch fetch
# ---------------------------------------------------------------------------

def fetch_all_price_histories(
    markets: list[Market],
    force_refresh: bool = False,
) -> dict[str, list[PricePoint]]:
    """Fetch price histories for all markets, with progress."""
    result: dict[str, list[PricePoint]] = {}
    total = len(markets)
    for i, mkt in enumerate(markets):
        if (i + 1) % 50 == 0 or i == 0:
            logger.info("Fetching prices: %d / %d", i + 1, total)
        history = fetch_price_history(mkt.token_id, force_refresh=force_refresh)
        if history:
            result[mkt.token_id] = history
    logger.info("Fetched price histories for %d / %d markets", len(result), total)
    return result
