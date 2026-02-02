"""
Conservative trading strategy implementation.
"""
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from loguru import logger

from ..models.schemas import TradeSignal, TradeOrder, Position
from ..core.bankroll_manager import BankrollManager
from ..analysis.prediction_engine import PredictionEngine


class ConservativeStrategy:
    """Conservative trading strategy focused on consistent small gains."""
    
    def __init__(
        self,
        bankroll_manager: BankrollManager,
        prediction_engine: PredictionEngine,
        min_confidence: int = 70,
        min_edge: float = 0.05,
        min_liquidity: float = 10000,
        take_profit: float = 0.10,
        stop_loss: float = 0.15,
        close_before_event_hours: int = 1
    ):
        """
        Initialize conservative strategy.
        
        Args:
            bankroll_manager: Bankroll manager instance
            prediction_engine: Prediction engine instance
            min_confidence: Minimum LLM confidence to trade (0-100)
            min_edge: Minimum expected edge to trade
            min_liquidity: Minimum market liquidity
            take_profit: Take profit threshold (e.g., 0.10 = 10%)
            stop_loss: Stop loss threshold (e.g., 0.15 = 15%)
            close_before_event_hours: Close positions N hours before event
        """
        self.bankroll = bankroll_manager
        self.prediction = prediction_engine
        
        self.min_confidence = min_confidence
        self.min_edge = min_edge
        self.min_liquidity = min_liquidity
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.close_before_event_hours = close_before_event_hours
        
        logger.info(f"Conservative strategy initialized (min_confidence={min_confidence}%, min_edge={min_edge:.2%})")
    
    def evaluate_entry(
        self,
        signal: TradeSignal,
        liquidity: float,
        volume_24h: float
    ) -> tuple[bool, str]:
        """
        Evaluate if we should enter a trade.
        
        Args:
            signal: Trade signal from prediction engine
            liquidity: Market liquidity
            volume_24h: 24h volume
            
        Returns:
            Tuple of (should_enter, reason)
        """
        # Check if signal is to buy
        if signal.action != "buy":
            return False, f"Signal action is {signal.action}, not buy"
        
        # Check confidence
        if signal.confidence < self.min_confidence:
            return False, f"Confidence {signal.confidence}% < minimum {self.min_confidence}%"
        
        # Check edge
        if signal.expected_edge < self.min_edge:
            return False, f"Edge {signal.expected_edge:.2%} < minimum {self.min_edge:.2%}"
        
        # Check liquidity
        if liquidity < self.min_liquidity:
            return False, f"Liquidity ${liquidity:.0f} < minimum ${self.min_liquidity:.0f}"
        
        # Check if we can open position
        can_open, reason = self.bankroll.can_open_position(signal.recommended_size)
        if not can_open:
            return False, f"Cannot open position: {reason}"
        
        # All checks passed
        return True, "All entry criteria met"
    
    def create_order(
        self,
        signal: TradeSignal,
        market_question: str,
        is_paper_trade: bool = True
    ) -> TradeOrder:
        """
        Create a trade order from signal.
        
        Args:
            signal: Trade signal
            market_question: Market question
            is_paper_trade: Whether this is a paper trade
            
        Returns:
            TradeOrder object
        """
        order = TradeOrder(
            market_id=signal.market_id,
            side="buy",
            outcome=signal.side,
            size=signal.recommended_size,
            price=signal.entry_price,
            order_type="market",
            is_paper_trade=is_paper_trade,
            notes=f"Confidence: {signal.confidence}%, Edge: {signal.expected_edge:.2%}"
        )
        
        logger.info(f"Created order: {order.side} {order.outcome} ${order.size:.2f} @ {order.price:.3f}")
        
        return order
    
    def check_exit_conditions(
        self,
        position: Position,
        current_price: float,
        event_time: Optional[datetime] = None
    ) -> tuple[bool, str]:
        """
        Check if position should be closed.
        
        Args:
            position: Open position
            current_price: Current market price
            event_time: Event datetime
            
        Returns:
            Tuple of (should_exit, reason)
        """
        # Calculate P&L percentage
        if position.outcome.lower() == "yes":
            # For YES: profit when price goes up
            pnl_pct = (current_price - position.entry_price) / position.entry_price
        else:
            # For NO: profit when price goes down
            pnl_pct = (position.entry_price - current_price) / (1 - position.entry_price)
        
        # Check take profit
        if pnl_pct >= self.take_profit:
            return True, f"take_profit (P&L: {pnl_pct:.2%})"
        
        # Check stop loss
        if pnl_pct <= -self.stop_loss:
            return True, f"stop_loss (P&L: {pnl_pct:.2%})"
        
        # Check time until event
        if event_time:
            hours_until = (event_time - datetime.utcnow()).total_seconds() / 3600
            if hours_until <= self.close_before_event_hours:
                return True, f"event_close ({hours_until:.1f}h until event)"
        
        # No exit condition met
        return False, "holding"
    
    def manage_positions(
        self,
        get_current_price_func
    ) -> List[dict]:
        """
        Manage all open positions.
        
        Args:
            get_current_price_func: Function to get current price for a market
            
        Returns:
            List of actions taken
        """
        actions = []
        
        # Get all open positions
        positions = self.bankroll.get_open_positions()
        
        logger.info(f"Managing {len(positions)} open positions")
        
        for position in positions:
            # Get current price
            current_price = get_current_price_func(position.market_id, position.outcome)
            
            if current_price is None:
                logger.warning(f"Could not get price for {position.market_id}")
                continue
            
            # Update unrealized P&L
            self.bankroll.update_position_pnl(position.trade_id, current_price)
            
            # Check exit conditions
            should_exit, reason = self.check_exit_conditions(
                position,
                current_price,
                position.event_time
            )
            
            if should_exit:
                # Close position
                pnl = self.bankroll.close_position(
                    position.trade_id,
                    current_price,
                    reason
                )
                
                actions.append({
                    "action": "close",
                    "trade_id": position.trade_id,
                    "market": position.market_question,
                    "reason": reason,
                    "pnl": pnl
                })
                
                logger.info(f"Closed position {position.trade_id}: {reason}, P&L=${pnl:.2f}")
        
        return actions
    
    def get_strategy_stats(self) -> dict:
        """
        Get strategy statistics.
        
        Returns:
            Dictionary with strategy stats
        """
        return {
            "min_confidence": self.min_confidence,
            "min_edge": self.min_edge,
            "min_liquidity": self.min_liquidity,
            "take_profit": self.take_profit,
            "stop_loss": self.stop_loss,
            "close_before_event_hours": self.close_before_event_hours
        }
