"""
Pydantic schemas for copy trading data validation.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class WalletActivity(BaseModel):
    """A single trade activity detected from a tracked wallet."""
    wallet_address: str
    tx_hash: str
    market_id: str
    condition_id: Optional[str] = None
    token_id: Optional[str] = None
    market_question: Optional[str] = None
    market_slug: Optional[str] = None

    side: str = Field(pattern='^(buy|sell)$')
    outcome: str = Field(pattern='^(yes|no)$')
    size: float = Field(gt=0)
    price: float = Field(ge=0, le=1)

    timestamp: datetime
    block_number: Optional[int] = None


class CopyDecision(BaseModel):
    """Decision on whether and how to copy a trade."""
    should_copy: bool
    reason: str

    # If copying, these are populated
    copy_size: Optional[float] = None
    copy_side: Optional[str] = None
    copy_outcome: Optional[str] = None
    target_price: Optional[float] = None

    # Source info
    source_wallet: str
    source_activity: WalletActivity

    # Risk checks
    passes_size_filter: bool = True
    passes_category_filter: bool = True
    passes_market_filter: bool = True
    passes_bankroll_check: bool = True
    passes_exposure_check: bool = True


class CopyTradeResult(BaseModel):
    """Result of executing a copy trade."""
    success: bool
    order_id: Optional[str] = None
    executed_price: Optional[float] = None
    executed_size: Optional[float] = None
    slippage: Optional[float] = None
    error: Optional[str] = None

    source_wallet: str
    source_tx_hash: str
    market_id: str


class TrackedWalletStats(BaseModel):
    """Statistics for a tracked wallet."""
    address: str
    label: Optional[str] = None
    is_active: bool

    total_trades_detected: int = 0
    total_trades_copied: int = 0
    total_trades_skipped: int = 0

    total_pnl: float = 0.0
    win_rate: float = 0.0
    avg_trade_size: float = 0.0
    total_volume: float = 0.0

    last_activity: Optional[datetime] = None
    tracking_since: Optional[datetime] = None

    # Recent performance
    pnl_24h: float = 0.0
    pnl_7d: float = 0.0
    trades_24h: int = 0


class CopyTradingStatus(BaseModel):
    """Overall copy trading system status."""
    is_running: bool = False
    mode: str = "paper"  # 'paper' or 'live'

    # Wallets
    total_wallets_tracked: int = 0
    active_wallets: int = 0

    # Positions
    open_positions: int = 0
    total_exposure: float = 0.0

    # Performance
    total_pnl: float = 0.0
    total_trades_copied: int = 0
    total_trades_skipped: int = 0
    overall_win_rate: float = 0.0

    # Bankroll
    bankroll: float = 0.0
    available_capital: float = 0.0

    # Timing
    last_scan: Optional[datetime] = None
    uptime_seconds: int = 0

    # Top wallets
    top_wallets: List[TrackedWalletStats] = Field(default_factory=list)


class WalletDiscovery(BaseModel):
    """A wallet discovered through leaderboard or on-chain analysis."""
    address: str
    profit_total: float = 0.0
    volume_total: float = 0.0
    markets_traded: int = 0
    win_rate: float = 0.0
    avg_position_size: float = 0.0
    last_active: Optional[datetime] = None
    rank: Optional[int] = None
    source: str = "gamma_api"  # 'gamma_api', 'on_chain', 'manual'
