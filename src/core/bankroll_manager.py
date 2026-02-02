"""
Bankroll management system.
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from loguru import logger

from ..models.database import Trade, Performance
from ..models.schemas import BankrollStatus, Position


class BankrollManager:
    """Manages bankroll and position limits."""
    
    def __init__(
        self,
        db_session: Session,
        initial_bankroll: float,
        max_positions: int = 5,
        portfolio_stop_loss: float = 0.20
    ):
        """
        Initialize bankroll manager.
        
        Args:
            db_session: Database session
            initial_bankroll: Starting bankroll in USDC
            max_positions: Maximum concurrent positions
            portfolio_stop_loss: Stop trading if down this much from peak
        """
        self.db = db_session
        self.initial_bankroll = initial_bankroll
        self.max_positions = max_positions
        self.portfolio_stop_loss = portfolio_stop_loss
        
        self._peak_bankroll = initial_bankroll
        self._stop_loss_triggered = False
        
        logger.info(f"Bankroll manager initialized: ${initial_bankroll:.2f}")
    
    def get_current_bankroll(self) -> float:
        """
        Calculate current bankroll including open positions.
        
        Returns:
            Current total bankroll in USDC
        """
        # Get all open trades
        open_trades = self.db.query(Trade).filter(Trade.status == 'open').all()
        
        # Calculate total allocated capital
        allocated = sum(trade.size for trade in open_trades)
        
        # Calculate unrealized P&L
        unrealized_pnl = sum(trade.unrealized_pnl or 0 for trade in open_trades)
        
        # Get realized P&L from closed trades
        closed_trades = self.db.query(Trade).filter(Trade.status == 'closed').all()
        realized_pnl = sum(trade.realized_pnl or 0 for trade in closed_trades)
        
        # Current bankroll = initial + realized P&L + unrealized P&L
        current_bankroll = self.initial_bankroll + realized_pnl + unrealized_pnl
        
        # Update peak
        if current_bankroll > self._peak_bankroll:
            self._peak_bankroll = current_bankroll
        
        return current_bankroll
    
    def get_available_capital(self) -> float:
        """
        Get available capital for new positions.
        
        Returns:
            Available capital in USDC
        """
        current_bankroll = self.get_current_bankroll()
        
        # Get allocated capital in open positions
        open_trades = self.db.query(Trade).filter(Trade.status == 'open').all()
        allocated = sum(trade.size for trade in open_trades)
        
        available = current_bankroll - allocated
        return max(0, available)
    
    def get_status(self) -> BankrollStatus:
        """
        Get current bankroll status.
        
        Returns:
            BankrollStatus object
        """
        current_bankroll = self.get_current_bankroll()
        available = self.get_available_capital()
        
        open_trades = self.db.query(Trade).filter(Trade.status == 'open').all()
        allocated = sum(trade.size for trade in open_trades)
        
        # Calculate drawdown from peak
        drawdown = (self._peak_bankroll - current_bankroll) / self._peak_bankroll
        
        # Check if stop loss triggered
        if drawdown >= self.portfolio_stop_loss:
            self._stop_loss_triggered = True
            logger.warning(f"Portfolio stop loss triggered! Drawdown: {drawdown:.2%}")
        
        # Check if trading is allowed
        is_trading_allowed = (
            not self._stop_loss_triggered and
            len(open_trades) < self.max_positions and
            available > 0
        )
        
        return BankrollStatus(
            total_bankroll=round(current_bankroll, 2),
            available_capital=round(available, 2),
            allocated_capital=round(allocated, 2),
            open_positions=len(open_trades),
            total_exposure=round(allocated, 2),
            peak_bankroll=round(self._peak_bankroll, 2),
            current_drawdown=round(drawdown, 4),
            is_trading_allowed=is_trading_allowed,
            stop_loss_triggered=self._stop_loss_triggered
        )
    
    def can_open_position(self, size: float) -> tuple[bool, str]:
        """
        Check if a new position can be opened.
        
        Args:
            size: Proposed position size in USDC
            
        Returns:
            Tuple of (can_open, reason)
        """
        status = self.get_status()
        
        if status.stop_loss_triggered:
            return False, "Portfolio stop loss triggered"
        
        if status.open_positions >= self.max_positions:
            return False, f"Maximum positions ({self.max_positions}) reached"
        
        if size > status.available_capital:
            return False, f"Insufficient capital (available: ${status.available_capital:.2f})"
        
        if size <= 0:
            return False, "Position size must be positive"
        
        return True, "OK"
    
    def update_position_pnl(self, trade_id: int, current_price: float):
        """
        Update unrealized P&L for an open position.
        
        Args:
            trade_id: Trade ID
            current_price: Current market price
        """
        trade = self.db.query(Trade).filter(Trade.id == trade_id).first()
        
        if not trade or trade.status != 'open':
            logger.warning(f"Trade {trade_id} not found or not open")
            return
        
        # Calculate unrealized P&L
        # For YES: P&L = size * (current_price - entry_price) / entry_price
        # For NO: P&L = size * (entry_price - current_price) / (1 - entry_price)
        
        if trade.outcome.lower() == 'yes':
            # Bought YES shares at entry_price
            # Each share worth current_price now
            # Paid: size * entry_price
            # Value: size * current_price
            shares = trade.size / trade.entry_price
            current_value = shares * current_price
            unrealized_pnl = current_value - trade.size
        else:
            # Bought NO shares at (1 - entry_price)
            # Each share worth (1 - current_price) now
            cost_per_share = 1 - trade.entry_price
            shares = trade.size / cost_per_share
            current_value = shares * (1 - current_price)
            unrealized_pnl = current_value - trade.size
        
        trade.unrealized_pnl = unrealized_pnl
        self.db.commit()
        
        logger.debug(f"Updated P&L for trade {trade_id}: ${unrealized_pnl:.2f}")
    
    def close_position(
        self,
        trade_id: int,
        exit_price: float,
        reason: str = "manual"
    ) -> float:
        """
        Close a position and calculate realized P&L.
        
        Args:
            trade_id: Trade ID
            exit_price: Exit price
            reason: Close reason
            
        Returns:
            Realized P&L
        """
        trade = self.db.query(Trade).filter(Trade.id == trade_id).first()
        
        if not trade or trade.status != 'open':
            logger.warning(f"Trade {trade_id} not found or not open")
            return 0
        
        # Calculate realized P&L (same logic as unrealized)
        if trade.outcome.lower() == 'yes':
            shares = trade.size / trade.entry_price
            exit_value = shares * exit_price
            realized_pnl = exit_value - trade.size
        else:
            cost_per_share = 1 - trade.entry_price
            shares = trade.size / cost_per_share
            exit_value = shares * (1 - exit_price)
            realized_pnl = exit_value - trade.size
        
        # Update trade
        trade.exit_price = exit_price
        trade.exit_time = datetime.utcnow()
        trade.realized_pnl = realized_pnl
        trade.status = 'closed'
        trade.close_reason = reason
        
        self.db.commit()
        
        logger.info(f"Closed trade {trade_id}: P&L=${realized_pnl:.2f}, reason={reason}")
        
        return realized_pnl
    
    def get_open_positions(self) -> List[Position]:
        """
        Get all open positions.
        
        Returns:
            List of Position objects
        """
        open_trades = self.db.query(Trade).filter(Trade.status == 'open').all()
        
        positions = []
        for trade in open_trades:
            # Calculate current unrealized P&L percentage
            if trade.unrealized_pnl and trade.size > 0:
                pnl_pct = trade.unrealized_pnl / trade.size
            else:
                pnl_pct = 0
            
            position = Position(
                trade_id=trade.id,
                market_id=trade.market_id,
                market_question=trade.market_question,
                side=trade.side,
                outcome=trade.outcome,
                size=trade.size,
                entry_price=trade.entry_price,
                current_price=trade.entry_price,  # Will be updated separately
                entry_time=trade.entry_time,
                event_time=trade.event_time,
                unrealized_pnl=trade.unrealized_pnl or 0,
                unrealized_pnl_pct=pnl_pct,
                confidence=trade.confidence_score or 0,
                expected_edge=trade.expected_edge or 0
            )
            positions.append(position)
        
        return positions
    
    def reset_stop_loss(self):
        """Reset the stop loss trigger (use with caution!)."""
        self._stop_loss_triggered = False
        logger.warning("Portfolio stop loss has been reset")
