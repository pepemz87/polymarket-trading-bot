"""
Database models for copy trading.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, Float, String, DateTime, Boolean, Text, JSON, Index
)
from src.models.database import Base


class TrackedWallet(Base):
    """A wallet being tracked for copy trading."""
    __tablename__ = 'tracked_wallets'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Wallet identification
    address = Column(String(42), nullable=False, unique=True, index=True)
    label = Column(String(100))  # Friendly name e.g. "Whale_Alpha"

    # Tracking settings
    is_active = Column(Boolean, default=True)
    copy_buys = Column(Boolean, default=True)
    copy_sells = Column(Boolean, default=True)

    # Sizing mode: 'proportional', 'fixed', 'percentage'
    sizing_mode = Column(String(20), default='proportional')
    # For fixed: exact USDC amount per trade
    fixed_size = Column(Float, default=10.0)
    # For proportional: fraction relative to tracked wallet's trade size
    proportional_factor = Column(Float, default=1.0)
    # For percentage: percentage of our bankroll per trade
    percentage_of_bankroll = Column(Float, default=0.05)

    # Filters
    min_trade_size = Column(Float, default=1.0)      # Ignore trades smaller than this (USDC)
    max_trade_size = Column(Float, default=10000.0)   # Cap copy at this size
    allowed_categories = Column(JSON, default=None)    # None = all categories
    blocked_markets = Column(JSON, default=None)       # Market IDs to skip

    # Delay before copying (seconds) - avoid front-running detection
    copy_delay_seconds = Column(Integer, default=5)

    # Performance tracking
    total_trades_copied = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)
    win_rate = Column(Float, default=0.0)

    # Timestamps
    added_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=None)

    def __repr__(self):
        return f"<TrackedWallet(address={self.address[:10]}..., label={self.label})>"


class CopiedTrade(Base):
    """Record of a trade copied from a tracked wallet."""
    __tablename__ = 'copied_trades'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Source information
    source_wallet = Column(String(42), nullable=False, index=True)
    source_tx_hash = Column(String(66), unique=True, index=True)
    source_trade_size = Column(Float)   # Original trade size in USDC
    source_price = Column(Float)        # Price the source got

    # Market information
    market_id = Column(String(100), nullable=False, index=True)
    condition_id = Column(String(100))
    token_id = Column(String(100))
    market_question = Column(Text)
    market_slug = Column(String(200))

    # Our copy trade details
    side = Column(String(10), nullable=False)     # 'buy' or 'sell'
    outcome = Column(String(10), nullable=False)  # 'yes' or 'no'
    size = Column(Float, nullable=False)           # Our position size in USDC
    entry_price = Column(Float)                    # Price we got
    exit_price = Column(Float)
    slippage = Column(Float)                       # entry_price - source_price

    # Status: 'pending', 'executed', 'partial', 'failed', 'skipped', 'closed'
    status = Column(String(20), nullable=False, default='pending')
    skip_reason = Column(Text)   # Why was this trade skipped
    error_message = Column(Text)

    # P&L tracking
    realized_pnl = Column(Float)
    unrealized_pnl = Column(Float)

    # Timestamps
    source_time = Column(DateTime, nullable=False)  # When source traded
    detected_at = Column(DateTime, default=datetime.utcnow)  # When we detected it
    executed_at = Column(DateTime)    # When we executed our copy
    closed_at = Column(DateTime)

    # Metadata
    is_paper_trade = Column(Boolean, default=True)
    order_id = Column(String(100))

    __table_args__ = (
        Index('ix_copied_trades_wallet_market', 'source_wallet', 'market_id'),
    )

    def __repr__(self):
        return (
            f"<CopiedTrade(id={self.id}, source={self.source_wallet[:10]}..., "
            f"side={self.side}, status={self.status})>"
        )


class WalletPerformance(Base):
    """Daily performance snapshot per tracked wallet."""
    __tablename__ = 'wallet_performance'

    id = Column(Integer, primary_key=True, autoincrement=True)

    wallet_address = Column(String(42), nullable=False, index=True)
    date = Column(DateTime, nullable=False)

    # Activity
    trades_detected = Column(Integer, default=0)
    trades_copied = Column(Integer, default=0)
    trades_skipped = Column(Integer, default=0)

    # P&L from copied trades
    realized_pnl = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)

    # Win/loss
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)

    # Volume
    total_volume_copied = Column(Float, default=0.0)

    # Source wallet stats (what *they* traded)
    source_total_volume = Column(Float, default=0.0)
    source_markets_traded = Column(Integer, default=0)

    __table_args__ = (
        Index('ix_wallet_perf_address_date', 'wallet_address', 'date', unique=True),
    )

    def __repr__(self):
        return f"<WalletPerformance(wallet={self.wallet_address[:10]}..., date={self.date})>"
