"""
Clawbot — Weather Trading Bot Configuration
All tunable parameters in one place.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# WALLET / API CREDENTIALS  (read from .env)
# ============================================================
POLY_PRIVATE_KEY      = os.getenv("POLY_PRIVATE_KEY", "")
POLY_WALLET_ADDRESS   = os.getenv("POLY_WALLET_ADDRESS", "")
POLY_API_KEY          = os.getenv("POLY_API_KEY", "")
POLY_API_SECRET       = os.getenv("POLY_API_SECRET", "")
POLY_API_PASSPHRASE   = os.getenv("POLY_API_PASSPHRASE", "")

# ============================================================
# CLOB ENDPOINTS
# ============================================================
CLOB_HOST             = "https://clob.polymarket.com"
GAMMA_HOST            = "https://gamma-api.polymarket.com"
CHAIN_ID              = 137          # Polygon mainnet

# ============================================================
# PAPER TRADING  (set to False only after validating live)
# ============================================================
PAPER_TRADING         = True         # NEVER disable without testing first

# ============================================================
# CAPITAL & POSITION LIMITS
# ============================================================
TOTAL_CAPITAL_USDC    = 100.0        # Total USDC deployed to the bot
MAX_TRADE_SIZE_USDC   = 10.0         # Hard cap per single trade
MAX_OPEN_POSITIONS    = 5            # Max concurrent open positions
MAX_DAILY_LOSS_USDC   = 20.0         # Daily stop-loss; bot halts if hit

# ============================================================
# SIGNAL FILTERS
# ============================================================
MIN_EDGE_DEGREES      = 2            # Minimum °C mispricing to act on
MIN_VOLUME_24H        = 5000         # Minimum 24h market volume ($)
MIN_YES_PRICE         = 0.05         # Skip if YES < 5¢ (too risky)
MAX_YES_PRICE         = 0.45         # Skip if YES > 45¢ (already priced)
ONLY_STRONG_SIGNALS   = True         # Require ensemble_agrees == True
MAX_SIGNAL_AGE_HOURS  = 1.0          # Ignore signals older than this

# ============================================================
# ORDER EXECUTION
# ============================================================
USE_LIMIT_ORDERS      = True         # Limit > market to avoid slippage
LIMIT_ORDER_SLIPPAGE  = 0.02         # Bid this many cents above best ask
LIMIT_ORDER_TIMEOUT   = 1800         # Cancel unfilled limit after 30 min

# ============================================================
# SCHEDULING
# ============================================================
SCAN_SIGNALS_EVERY    = 300          # Poll weather_signals.json every 5 min

# ============================================================
# KELLY CRITERION
# ============================================================
KELLY_FRACTION        = 0.25         # Use 25% of full Kelly (conservative)

# ============================================================
# FILES
# ============================================================
SIGNALS_FILE          = "weather_signals.json"
LOG_FILE              = "trade_log.csv"
POSITIONS_FILE        = "open_positions.json"
