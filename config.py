"""Strategy V5.1 — Tier A Only + Hard Stop 0.85 (Best Performing)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TierConfig:
    name: str
    price_low: float
    price_high: float
    max_hours_to_resolution: int
    position_size_usd: float  # fixed USD per trade
    soft_stop_loss: float     # L1 warning line
    hard_stop_loss: float     # L2 hard stop


# --- V5.1 Optimized: Tier A Only ---
# Fast-settling (<12h), wide entry 0.94-0.99, hard stop 0.85
TIER_A = TierConfig(
    name="TierA",
    price_low=0.940,
    price_high=0.990,
    max_hours_to_resolution=12,
    position_size_usd=50.0,
    soft_stop_loss=0.88,    # L1: cancel TP orders
    hard_stop_loss=0.85,    # L2: hard stop with taker exit
)

TIERS = [TIER_A]


# --- Exit parameters ---
TAKE_PROFIT_PRICE = 0.99
STOP_LOSS_REBOUND_MARGIN = 0.01  # must rebound this much above L2 to cancel
HARD_STOP_CONFIRM_HOURS = 1     # proxy for 30s confirm (1h candle granularity)

# --- Fee model (Maker-Only entry + TP; Taker only on stop-loss) ---
TAKER_FEE_PCT = 0.005   # 0.5% taker fee (emergency stop)
MAKER_FEE_PCT = 0.0     # 0% on Post-Only Limit orders
SLIPPAGE_TICKS = 0.001   # tick-sniping: bid+0.001 entry
STOP_LOSS_SLIPPAGE = 0.01  # slippage on emergency taker exit

# --- Portfolio limits ---
MAX_TOTAL_EXPOSURE_USD = 0  # 0 = no global cap (managed by per-category)
MAX_SAME_CATEGORY = 5       # max concurrent positions in one category
MAX_CONCURRENT_POSITIONS = 50  # absolute max open positions

# --- Blacklist keywords ---
BLACKLIST_KEYWORDS = [
    "dispute", "uma", "opinion",
    "oscar", "grammy", "emmy", "golden globe",
    "x poll", "twitter poll", "tweet", "twitter",
    "gymnastics score", "diving score", "figure skating",
    "sec sue", "indict", "court ruling",
    "first ever", "first time",
]

# --- Super-category mapping (for category isolation) ---
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

# --- Data fetch settings ---
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"
DATA_API_BASE = "https://data-api.polymarket.com"
MIN_MARKET_VOLUME = 5_000
PRICE_FIDELITY_MINUTES = 60
FETCH_DELAY_SECONDS = 0.1
