"""Market scanner — polls Gamma API for active markets matching strategy criteria."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from src.config import (
    CLOB_API_BASE,
    FETCH_DELAY_SECONDS,
    GAMMA_API_BASE,
    MIN_MARKET_VOLUME,
    SCANNER_POLL_INTERVAL_SECONDS,
)
from src.models import Market
from src.strategy import is_blacklisted
from src.utils import parse_datetime

logger = logging.getLogger(__name__)


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


def fetch_active_markets(max_pages: int = 5) -> list[Market]:
    """Fetch active (not yet resolved) binary YES/NO markets from Gamma API."""
    all_raw: list[dict] = []
    offset = 0
    limit = 100

    for page in range(max_pages):
        url = (
            f"{GAMMA_API_BASE}/markets"
            f"?closed=false&active=true&limit={limit}&offset={offset}"
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
        offset += limit
        time.sleep(FETCH_DELAY_SECONDS)

    return _filter_markets(all_raw)


def _filter_markets(raw_list: list[dict]) -> list[Market]:
    """Filter raw market data to binary YES/NO markets with sufficient volume."""
    markets: list[Market] = []
    for raw in raw_list:
        outcomes = _parse_json_field(raw.get("outcomes"))
        if len(outcomes) != 2:
            continue
        if not any(str(o).lower() == "yes" for o in outcomes):
            continue

        volume = float(raw.get("volumeNum") or raw.get("volume") or 0)
        if volume < MIN_MARKET_VOLUME:
            continue

        # Must NOT be closed
        if raw.get("closed"):
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

        clob_ids = _parse_json_field(raw.get("clobTokenIds"))
        if not clob_ids:
            continue
        yes_token_id = str(clob_ids[0])

        end_date = parse_datetime(raw.get("endDate"))
        if not end_date:
            continue

        markets.append(Market(
            condition_id=raw.get("conditionId") or str(raw.get("id") or ""),
            token_id=yes_token_id,
            question=question,
            category=category if isinstance(category, str) else "other",
            volume=volume,
            end_date=end_date,
            resolved_at=None,
            winning_outcome=None,
            slug=raw.get("slug") or "",
            tags=tags,
        ))

    logger.info("Scanner found %d active binary markets", len(markets))
    return markets


def fetch_current_price(token_id: str) -> Optional[float]:
    """Fetch the current mid-price for a YES token from CLOB API."""
    url = f"{CLOB_API_BASE}/book?token_id={token_id}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        logger.warning("Price fetch error for %s: %s", token_id[:8], exc)
        return None

    bids = data.get("bids", [])
    asks = data.get("asks", [])

    best_bid = float(bids[0]["price"]) if bids else None
    best_ask = float(asks[0]["price"]) if asks else None

    if best_bid is not None and best_ask is not None:
        return (best_bid + best_ask) / 2
    if best_bid is not None:
        return best_bid
    if best_ask is not None:
        return best_ask
    return None


def fetch_best_bid(token_id: str) -> Optional[float]:
    """Fetch best bid price for a YES token."""
    url = f"{CLOB_API_BASE}/book?token_id={token_id}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        logger.warning("Order book error for %s: %s", token_id[:8], exc)
        return None

    bids = data.get("bids", [])
    return float(bids[0]["price"]) if bids else None
