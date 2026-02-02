"""
Prediction engine that orchestrates data collection and LLM analysis.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from loguru import logger

from .llm_analyzer import LLMAnalyzer
from .data_collector import DataCollector
from ..models.database import Prediction
from ..models.schemas import LLMPrediction, TradeSignal
from ..core.kelly_criterion import calculate_edge


class PredictionEngine:
    """Orchestrates prediction workflow."""
    
    def __init__(
        self,
        llm_analyzer: LLMAnalyzer,
        data_collector: DataCollector,
        db_session: Session
    ):
        """
        Initialize prediction engine.
        
        Args:
            llm_analyzer: LLM analyzer instance
            data_collector: Data collector instance
            db_session: Database session
        """
        self.llm = llm_analyzer
        self.data = data_collector
        self.db = db_session
        
        logger.info("Prediction engine initialized")
    
    def generate_prediction(
        self,
        market_id: str,
        market_question: str,
        yes_price: float,
        no_price: float,
        sport: Optional[str] = None,
        liquidity: Optional[float] = None,
        volume_24h: Optional[float] = None
    ) -> Optional[LLMPrediction]:
        """
        Generate prediction for a market.
        
        Args:
            market_id: Market ID
            market_question: Market question
            yes_price: Current YES price
            no_price: Current NO price
            sport: Sport category
            liquidity: Market liquidity
            volume_24h: 24h volume
            
        Returns:
            LLMPrediction or None
        """
        logger.info(f"Generating prediction for: {market_question}")
        
        # Extract teams from question
        teams = self.data.extract_teams_from_question(market_question)
        
        # Collect context data
        context = self.data.collect_all_data(
            market_question=market_question,
            sport=sport,
            teams=teams
        )
        
        # Get LLM prediction
        prediction = self.llm.analyze_market(
            market_question=market_question,
            market_id=market_id,
            current_yes_price=yes_price,
            current_no_price=no_price,
            context_data=context
        )
        
        if not prediction:
            logger.warning("Failed to generate prediction")
            return None
        
        # Save prediction to database
        self._save_prediction(prediction, liquidity, volume_24h)
        
        return prediction
    
    def generate_trade_signal(
        self,
        prediction: LLMPrediction,
        bankroll: float,
        kelly_fraction: float = 0.25,
        max_bet_fraction: float = 0.05
    ) -> Optional[TradeSignal]:
        """
        Generate trade signal from prediction.
        
        Args:
            prediction: LLM prediction
            bankroll: Current bankroll
            kelly_fraction: Kelly fraction to use
            max_bet_fraction: Maximum bet fraction
            
        Returns:
            TradeSignal or None
        """
        # Calculate edge
        edge = calculate_edge(
            estimated_probability=prediction.expected_probability,
            market_price=prediction.current_yes_price,
            side=prediction.predicted_outcome
        )
        
        # Check if we have positive edge
        if edge <= 0:
            logger.info(f"No edge: {edge:.4f}")
            return self._no_trade_signal(prediction, edge, "No positive edge")
        
        # Determine side
        if prediction.predicted_outcome.lower() == "yes":
            side = "yes"
            entry_price = prediction.current_yes_price
        else:
            side = "no"
            entry_price = prediction.current_no_price
        
        # Calculate Kelly bet size
        from ..core.kelly_criterion import KellyCriterion
        kelly = KellyCriterion(kelly_fraction=kelly_fraction, max_bet_fraction=max_bet_fraction)
        
        bet_calc = kelly.calculate_from_edge(
            bankroll=bankroll,
            edge=edge,
            win_probability=prediction.expected_probability
        )
        
        if not bet_calc["should_bet"]:
            logger.info(f"Kelly says no bet: {bet_calc['reason']}")
            return self._no_trade_signal(prediction, edge, bet_calc["reason"])
        
        # Calculate take profit and stop loss prices
        if side == "yes":
            take_profit_price = min(0.99, entry_price * 1.10)  # 10% profit
            stop_loss_price = max(0.01, entry_price * 0.85)    # 15% loss
        else:
            take_profit_price = max(0.01, entry_price * 0.90)
            stop_loss_price = min(0.99, entry_price * 1.15)
        
        # Create trade signal
        signal = TradeSignal(
            market_id=prediction.market_id,
            market_question=prediction.market_question,
            action="buy",
            side=side,
            recommended_size=bet_calc["bet_size"],
            kelly_fraction=bet_calc["bet_fraction"],
            confidence=prediction.confidence,
            expected_edge=edge,
            expected_value=bet_calc["expected_value"],
            entry_price=entry_price,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            reasoning=prediction.reasoning,
            timestamp=datetime.utcnow()
        )
        
        logger.info(f"Trade signal generated: {signal.action} {signal.side} ${signal.recommended_size:.2f}")
        
        return signal
    
    def _save_prediction(
        self,
        prediction: LLMPrediction,
        liquidity: Optional[float],
        volume_24h: Optional[float]
    ):
        """Save prediction to database."""
        db_prediction = Prediction(
            market_id=prediction.market_id,
            market_question=prediction.market_question,
            predicted_outcome=prediction.predicted_outcome,
            confidence=prediction.confidence,
            expected_probability=prediction.expected_probability,
            current_yes_price=prediction.current_yes_price,
            current_no_price=prediction.current_no_price,
            liquidity=liquidity,
            volume_24h=volume_24h,
            llm_provider=prediction.llm_provider,
            llm_model=prediction.llm_model,
            reasoning=prediction.reasoning,
            data_sources=prediction.data_sources,
            created_at=prediction.timestamp
        )
        
        self.db.add(db_prediction)
        self.db.commit()
        
        logger.debug(f"Prediction saved to database: {prediction.market_id}")
    
    @staticmethod
    def _no_trade_signal(
        prediction: LLMPrediction,
        edge: float,
        reason: str
    ) -> TradeSignal:
        """Create a no-trade signal."""
        return TradeSignal(
            market_id=prediction.market_id,
            market_question=prediction.market_question,
            action="hold",
            side=None,
            recommended_size=0,
            kelly_fraction=0,
            confidence=prediction.confidence,
            expected_edge=edge,
            expected_value=0,
            entry_price=prediction.current_yes_price,
            take_profit_price=None,
            stop_loss_price=None,
            reasoning=f"{reason}. LLM reasoning: {prediction.reasoning}",
            timestamp=datetime.utcnow()
        )
