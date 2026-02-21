"""Strategy V5.1 parameters + live trading configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Strategy parameters (shared by backtest and live)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TierConfig:
    name: str
    price_low: float
    price_high: float
    max_hours_to_resolution: int
    position_size_usd: float
    soft_stop_loss: float
    hard_stop_loss: float


TIER_A = TierConfig(
    name="TierA",
    price_low=0.940,
    price_high=0.990,
    max_hours_to_resolution=12,
    position_size_usd=50.0,
    soft_stop_loss=0.88,
    hard_stop_loss=0.85,
)

TIERS = [TIER_A]

TAKE_PROFIT_PRICE = 0.99
STOP_LOSS_REBOUND_MARGIN = 0.01
HARD_STOP_CONFIRM_HOURS = 1

TAKER_FEE_PCT = 0.005
MAKER_FEE_PCT = 0.0
SLIPPAGE_TICKS = 0.001
STOP_LOSS_SLIPPAGE = 0.01

MAX_SAME_CATEGORY = 5
MAX_CONCURRENT_POSITIONS = 50

BLACKLIST_KEYWORDS = [
    "dispute", "uma", "opinion",
    "oscar", "grammy", "emmy", "golden globe",
    "x poll", "twitter poll", "tweet", "twitter",
    "gymnastics score", "diving score", "figure skating",
    "sec sue", "indict", "court ruling",
    "first ever", "first time",
]

SUPER_CATEGORIES = {
    "sports": ["sports", "nba", "nfl", "mlb", "nhl", "soccer", "football",
               "tennis", "mma", "ufc", "cricket", "f1", "racing", "boxing",
               "baseball", "basketball", "hockey", "golf", "olympics",
               "game", "match", "beat", "win", "score", "points"],
    "politics": ["politics", "election", "congress", "senate", "president",
                 "governor", "legislation", "government", "vote", "ballot",
                 "trump", "biden", "republican", "democrat", "party"],
    "crypto": ["crypto", "bitcoin", "ethereum", "solana", "defi", "token",
               "blockchain", "nft", "btc", "eth", "xrp", "price of"],
    "entertainment": ["entertainment", "movie", "tv", "music", "celebrity", "award"],
    "economy": ["economy", "fed", "inflation", "gdp", "interest rate",
                "unemployment", "cpi", "stock market", "recession"],
}

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"
DATA_API_BASE = "https://data-api.polymarket.com"
CHAIN_ID = 137  # Polygon

# Data fetch settings
MIN_MARKET_VOLUME = 5_000
PRICE_FIDELITY_MINUTES = 60
FETCH_DELAY_SECONDS = 0.1

# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

WEBSOCKET_MARKET_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
WEBSOCKET_USER_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
HEARTBEAT_INTERVAL_SECONDS = 10

# ---------------------------------------------------------------------------
# Live trading settings
# ---------------------------------------------------------------------------

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
SCANNER_POLL_INTERVAL_SECONDS = 60

# Circuit breaker
CIRCUIT_BREAKER_MAX_LOSS_USD = float(os.getenv("CIRCUIT_BREAKER_MAX_LOSS_USD", "500"))
CIRCUIT_BREAKER_MAX_LOSS_PCT = float(os.getenv("CIRCUIT_BREAKER_MAX_LOSS_PCT", "0.10"))
CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES = 10

# ---------------------------------------------------------------------------
# Credentials (live mode only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LiveCredentials:
    private_key: str
    api_key: str
    api_secret: str
    api_passphrase: str


def load_credentials() -> LiveCredentials:
    """Load trading credentials from environment variables.

    Raises EnvironmentError if any required variable is missing.
    Call dotenv.load_dotenv() before this function.
    """
    required = {
        "POLY_PRIVATE_KEY": os.getenv("POLY_PRIVATE_KEY"),
        "POLY_API_KEY": os.getenv("POLY_API_KEY"),
        "POLY_API_SECRET": os.getenv("POLY_API_SECRET"),
        "POLY_API_PASSPHRASE": os.getenv("POLY_API_PASSPHRASE"),
    }

    missing = [k for k, v in required.items() if not v]
    if missing:
        raise EnvironmentError(
            f"Missing required credentials in .env: {', '.join(missing)}\n"
            f"Run: python scripts/setup_credentials.py"
        )

    return LiveCredentials(
        private_key=required["POLY_PRIVATE_KEY"],  # type: ignore[arg-type]
        api_key=required["POLY_API_KEY"],  # type: ignore[arg-type]
        api_secret=required["POLY_API_SECRET"],  # type: ignore[arg-type]
        api_passphrase=required["POLY_API_PASSPHRASE"],  # type: ignore[arg-type]
    )
