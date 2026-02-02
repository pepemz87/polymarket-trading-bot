"""
Pydantic schemas for data validation.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


class MarketData(BaseModel):
    """Market data schema."""
    market_id: str
    question: str
    slug: Optional[str] = None
    sport: Optional[str] = None
    category: Optional[str] = None
    
    yes_price: float = Field(ge=0, le=1)
    no_price: float = Field(ge=0, le=1)
    liquidity: float = Field(ge=0)
    volume_24h: float = Field(ge=0)
    
    event_time: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    active: bool = True
    resolved: bool = False
    
    @validator('no_price', always=True)
    def validate_prices(cls, v, values):
        """Ensure yes_price + no_price ≈ 1."""
        if 'yes_price' in values:
            total = values['yes_price'] + v
            if not (0.98 <= total <= 1.02):  # Allow small margin for fees
                raise ValueError(f"yes_price + no_price must ≈ 1, got {total}")
        return v


class LLMPrediction(BaseModel):
    """LLM prediction schema."""
    predicted_outcome: str = Field(pattern='^(yes|no)$')
    confidence: int = Field(ge=0, le=100)
    expected_probability: float = Field(ge=0, le=1)
    reasoning: str
    
    # Market context
    market_id: str
    market_question: str
    current_yes_price: float
    current_no_price: float
    
    # Metadata
    llm_provider: str
    llm_model: str
    data_sources: List[str] = Field(default_factory=list)
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TradeSignal(BaseModel):
    """Trade signal schema."""
    market_id: str
    market_question: str
    
    # Signal
    action: str = Field(pattern='^(buy|sell|hold)$')
    side: Optional[str] = Field(None, pattern='^(yes|no)$')
    
    # Sizing
    recommended_size: float = Field(ge=0)
    kelly_fraction: float = Field(ge=0, le=1)
    
    # Analysis
    confidence: int = Field(ge=0, le=100)
    expected_edge: float
    expected_value: float
    
    # Risk
    entry_price: float = Field(ge=0, le=1)
    take_profit_price: Optional[float] = Field(None, ge=0, le=1)
    stop_loss_price: Optional[float] = Field(None, ge=0, le=1)
    
    # Metadata
    reasoning: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TradeOrder(BaseModel):
    """Trade order schema."""
    market_id: str
    side: str = Field(pattern='^(buy|sell)$')
    outcome: str = Field(pattern='^(yes|no)$')
    size: float = Field(gt=0)
    price: float = Field(ge=0, le=1)
    
    # Optional
    order_type: str = Field(default='market', pattern='^(market|limit)$')
    time_in_force: str = Field(default='GTC')  # Good Till Cancelled
    
    # Metadata
    is_paper_trade: bool = True
    notes: Optional[str] = None


class Position(BaseModel):
    """Open position schema."""
    trade_id: int
    market_id: str
    market_question: str
    
    side: str
    outcome: str
    size: float
    entry_price: float
    current_price: float
    
    entry_time: datetime
    event_time: Optional[datetime] = None
    
    unrealized_pnl: float
    unrealized_pnl_pct: float
    
    confidence: int
    expected_edge: float


class PerformanceMetrics(BaseModel):
    """Performance metrics schema."""
    date: datetime
    
    # Bankroll
    starting_bankroll: float
    ending_bankroll: float
    peak_bankroll: float
    
    # Trades
    trades_opened: int = 0
    trades_closed: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # P&L
    realized_pnl: float = 0
    unrealized_pnl: float = 0
    total_pnl: float = 0
    
    # Returns
    daily_return: float = 0
    cumulative_return: float = 0
    
    # Win rate
    win_rate: Optional[float] = None
    
    @validator('win_rate', always=True)
    def calculate_win_rate(cls, v, values):
        """Calculate win rate from trades."""
        if 'trades_closed' in values and values['trades_closed'] > 0:
            if 'winning_trades' in values:
                return values['winning_trades'] / values['trades_closed']
        return v


class BankrollStatus(BaseModel):
    """Current bankroll status."""
    total_bankroll: float
    available_capital: float
    allocated_capital: float
    
    open_positions: int
    total_exposure: float
    
    peak_bankroll: float
    current_drawdown: float
    
    is_trading_allowed: bool
    stop_loss_triggered: bool


class SystemStatus(BaseModel):
    """System status schema."""
    is_running: bool
    trading_mode: str  # 'paper' or 'live'
    
    last_market_scan: Optional[datetime] = None
    last_position_check: Optional[datetime] = None
    
    total_trades: int = 0
    open_positions: int = 0
    
    bankroll: float
    total_pnl: float
    
    errors_24h: int = 0
    last_error: Optional[str] = None
    
    api_status: Dict[str, bool] = Field(default_factory=dict)
