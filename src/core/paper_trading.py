"""
Paper trading simulator for testing strategies without real money.
"""
import time
import random
from datetime import datetime
from typing import Optional, Dict
from sqlalchemy.orm import Session
from loguru import logger

from ..models.database import Trade
from ..models.schemas import TradeOrder


class PaperTradingSimulator:
    """Simulates trade execution for paper trading."""
    
    def __init__(
        self,
        db_session: Session,
        slippage: float = 0.002,
        fill_delay: float = 2.0
    ):
        """
        Initialize paper trading simulator.
        
        Args:
            db_session: Database session
            slippage: Simulated slippage as a fraction (e.g., 0.002 = 0.2%)
            fill_delay: Simulated order fill delay in seconds
        """
        self.db = db_session
        self.slippage = slippage
        self.fill_delay = fill_delay
        
        logger.info(f"Paper trading simulator initialized (slippage={slippage:.2%}, delay={fill_delay}s)")
    
    def place_order(
        self,
        order: TradeOrder,
        market_question: str,
        sport: Optional[str] = None,
        event_time: Optional[datetime] = None,
        confidence: Optional[int] = None,
        expected_edge: Optional[float] = None
    ) -> Optional[int]:
        """
        Simulate placing an order.
        
        Args:
            order: TradeOrder object
            market_question: Market question text
            sport: Sport category
            event_time: Event datetime
            confidence: LLM confidence score
            expected_edge: Expected edge
            
        Returns:
            Trade ID if successful, None otherwise
        """
        logger.info(f"Simulating order: {order.side} {order.outcome} ${order.size:.2f} @ {order.price:.3f}")
        
        # Simulate network delay
        time.sleep(self.fill_delay)
        
        # Apply slippage
        fill_price = self._apply_slippage(order.price, order.side)
        
        # Create trade record
        trade = Trade(
            market_id=order.market_id,
            market_question=market_question,
            market_slug=order.market_id,  # In real implementation, get from API
            sport=sport,
            side=order.side,
            outcome=order.outcome,
            size=order.size,
            entry_price=fill_price,
            entry_time=datetime.utcnow(),
            event_time=event_time,
            status='open',
            is_paper_trade=True,
            confidence_score=confidence,
            expected_edge=expected_edge,
            kelly_fraction=None,  # Set externally
            notes=order.notes
        )
        
        self.db.add(trade)
        self.db.commit()
        self.db.refresh(trade)
        
        logger.info(f"Paper trade executed: ID={trade.id}, fill_price={fill_price:.3f}")
        
        return trade.id
    
    def _apply_slippage(self, price: float, side: str) -> float:
        """
        Apply simulated slippage to price.
        
        Args:
            price: Original price
            side: 'buy' or 'sell'
            
        Returns:
            Price with slippage applied
        """
        # Add random slippage (unfavorable to trader)
        slippage_amount = random.uniform(0, self.slippage)
        
        if side.lower() == 'buy':
            # Buying: price goes up (worse for us)
            fill_price = price * (1 + slippage_amount)
        else:
            # Selling: price goes down (worse for us)
            fill_price = price * (1 - slippage_amount)
        
        # Ensure price stays in valid range [0, 1]
        fill_price = max(0.01, min(0.99, fill_price))
        
        return fill_price
    
    def get_current_price(self, market_id: str, outcome: str) -> float:
        """
        Get current market price (simulated).
        
        In paper trading, we'll use the entry price with some random movement.
        In production, this would call the actual Polymarket API.
        
        Args:
            market_id: Market ID
            outcome: 'yes' or 'no'
            
        Returns:
            Current price
        """
        # Find the most recent trade for this market
        trade = self.db.query(Trade).filter(
            Trade.market_id == market_id,
            Trade.outcome == outcome
        ).order_by(Trade.entry_time.desc()).first()
        
        if trade:
            # Simulate price movement (±5% random walk)
            price_change = random.uniform(-0.05, 0.05)
            new_price = trade.entry_price * (1 + price_change)
            new_price = max(0.01, min(0.99, new_price))
            return new_price
        
        # Default to 0.5 if no trade history
        return 0.5
    
    def cancel_order(self, trade_id: int) -> bool:
        """
        Cancel an open order.
        
        Args:
            trade_id: Trade ID
            
        Returns:
            True if cancelled successfully
        """
        trade = self.db.query(Trade).filter(Trade.id == trade_id).first()
        
        if not trade or trade.status != 'open':
            logger.warning(f"Cannot cancel trade {trade_id}: not found or not open")
            return False
        
        trade.status = 'cancelled'
        trade.exit_time = datetime.utcnow()
        trade.close_reason = 'cancelled'
        
        self.db.commit()
        
        logger.info(f"Paper trade {trade_id} cancelled")
        return True
    
    def get_balance(self) -> Dict[str, float]:
        """
        Get simulated account balance.
        
        Returns:
            Dictionary with balance information
        """
        # In paper trading, we track balance through bankroll manager
        # This is a placeholder for API compatibility
        return {
            "USDC": 0,  # Will be calculated by bankroll manager
            "available": 0
        }
    
    def get_positions(self) -> list:
        """
        Get open positions.
        
        Returns:
            List of open positions
        """
        open_trades = self.db.query(Trade).filter(
            Trade.status == 'open',
            Trade.is_paper_trade == True
        ).all()
        
        return [
            {
                "trade_id": trade.id,
                "market_id": trade.market_id,
                "side": trade.side,
                "outcome": trade.outcome,
                "size": trade.size,
                "entry_price": trade.entry_price,
                "entry_time": trade.entry_time
            }
            for trade in open_trades
        ]
