"""
Database models for the trading bot.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pathlib import Path

Base = declarative_base()


class Trade(Base):
    """Trade execution record."""
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Market information
    market_id = Column(String(100), nullable=False, index=True)
    market_question = Column(Text, nullable=False)
    market_slug = Column(String(200))
    sport = Column(String(50))
    
    # Trade details
    side = Column(String(10), nullable=False)  # 'buy' or 'sell'
    outcome = Column(String(10), nullable=False)  # 'yes' or 'no'
    size = Column(Float, nullable=False)  # Position size in USDC
    entry_price = Column(Float, nullable=False)  # Entry price (0-1)
    exit_price = Column(Float)  # Exit price (0-1)
    
    # Timestamps
    entry_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    exit_time = Column(DateTime)
    event_time = Column(DateTime)  # When the event actually happens
    
    # P&L
    realized_pnl = Column(Float)  # Realized profit/loss in USDC
    unrealized_pnl = Column(Float)  # Current unrealized P&L
    
    # Status
    status = Column(String(20), nullable=False, default='open')  # open, closed, cancelled
    close_reason = Column(String(50))  # take_profit, stop_loss, manual, event_close
    
    # Risk management
    kelly_fraction = Column(Float)
    confidence_score = Column(Integer)  # LLM confidence 0-100
    expected_edge = Column(Float)  # Expected value
    
    # Metadata
    is_paper_trade = Column(Boolean, default=True)
    notes = Column(Text)
    
    def __repr__(self):
        return f"<Trade(id={self.id}, market={self.market_slug}, side={self.side}, status={self.status})>"


class Prediction(Base):
    """LLM prediction record."""
    __tablename__ = 'predictions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Market information
    market_id = Column(String(100), nullable=False, index=True)
    market_question = Column(Text, nullable=False)
    
    # Prediction
    predicted_outcome = Column(String(10))  # 'yes' or 'no'
    confidence = Column(Integer, nullable=False)  # 0-100
    expected_probability = Column(Float)  # LLM's probability estimate
    
    # Market data at prediction time
    current_yes_price = Column(Float)
    current_no_price = Column(Float)
    liquidity = Column(Float)
    volume_24h = Column(Float)
    
    # LLM details
    llm_provider = Column(String(20))  # 'gemini' or 'groq'
    llm_model = Column(String(50))
    reasoning = Column(Text)  # LLM's reasoning
    
    # Data sources used
    data_sources = Column(JSON)  # List of data sources used
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Outcome tracking
    actual_outcome = Column(String(10))  # Actual result (filled after event)
    was_correct = Column(Boolean)
    
    def __repr__(self):
        return f"<Prediction(id={self.id}, market={self.market_id}, confidence={self.confidence})>"


class Market(Base):
    """Market data cache."""
    __tablename__ = 'markets'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Market identifiers
    market_id = Column(String(100), nullable=False, unique=True, index=True)
    question = Column(Text, nullable=False)
    slug = Column(String(200))
    
    # Market metadata
    sport = Column(String(50))
    category = Column(String(50))
    market_type = Column(String(50))
    
    # Market data
    yes_price = Column(Float)
    no_price = Column(Float)
    liquidity = Column(Float)
    volume_24h = Column(Float)
    
    # Event information
    event_time = Column(DateTime)
    end_date = Column(DateTime)
    
    # Status
    active = Column(Boolean, default=True)
    resolved = Column(Boolean, default=False)
    outcome = Column(String(10))  # Final outcome
    
    # Timestamps
    first_seen = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_updated = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Market(id={self.market_id}, question={self.question[:50]})>"


class Performance(Base):
    """Daily performance metrics."""
    __tablename__ = 'performance'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Date
    date = Column(DateTime, nullable=False, unique=True, index=True)
    
    # Bankroll
    starting_bankroll = Column(Float, nullable=False)
    ending_bankroll = Column(Float, nullable=False)
    peak_bankroll = Column(Float)
    
    # Trading metrics
    trades_opened = Column(Integer, default=0)
    trades_closed = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    
    # P&L
    realized_pnl = Column(Float, default=0)
    unrealized_pnl = Column(Float, default=0)
    total_pnl = Column(Float, default=0)
    
    # Returns
    daily_return = Column(Float)  # Percentage
    cumulative_return = Column(Float)  # Percentage from start
    
    # Risk metrics
    max_drawdown = Column(Float)
    sharpe_ratio = Column(Float)
    
    # Prediction accuracy
    predictions_made = Column(Integer, default=0)
    predictions_correct = Column(Integer, default=0)
    avg_confidence = Column(Float)
    
    def __repr__(self):
        return f"<Performance(date={self.date}, pnl={self.total_pnl})>"


class Database:
    """Database manager."""
    
    def __init__(self, database_url: str = "sqlite:///data/trades.db"):
        """
        Initialize database connection.
        
        Args:
            database_url: SQLAlchemy database URL
        """
        # Create data directory if it doesn't exist
        if database_url.startswith('sqlite:///'):
            db_path = Path(database_url.replace('sqlite:///', ''))
            db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Create tables
        Base.metadata.create_all(self.engine)
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()
    
    def close(self):
        """Close database connection."""
        self.engine.dispose()


# Global database instance
_db: Optional[Database] = None


def get_database(database_url: Optional[str] = None) -> Database:
    """
    Get or create the global database instance.
    
    Args:
        database_url: SQLAlchemy database URL
        
    Returns:
        Database instance
    """
    global _db
    if _db is None:
        if database_url is None:
            database_url = "sqlite:///data/trades.db"
        _db = Database(database_url)
    return _db
