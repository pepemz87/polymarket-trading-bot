"""
Kelly Criterion implementation for optimal bet sizing.
"""
from typing import Optional
from loguru import logger


class KellyCriterion:
    """
    Kelly Criterion calculator for optimal position sizing.
    
    The Kelly Criterion formula: f* = (bp - q) / b
    Where:
        f* = fraction of bankroll to wager
        b = net odds received (decimal odds - 1)
        p = probability of winning
        q = probability of losing (1 - p)
    """
    
    def __init__(self, kelly_fraction: float = 0.25, max_bet_fraction: float = 0.05):
        """
        Initialize Kelly Criterion calculator.
        
        Args:
            kelly_fraction: Fraction of full Kelly to use (e.g., 0.25 for quarter Kelly)
            max_bet_fraction: Maximum fraction of bankroll to risk per bet
        """
        self.kelly_fraction = kelly_fraction
        self.max_bet_fraction = max_bet_fraction
        
        logger.info(f"Kelly Criterion initialized: fraction={kelly_fraction}, max={max_bet_fraction}")
    
    def calculate_bet_size(
        self,
        bankroll: float,
        win_probability: float,
        current_price: float,
        side: str = "yes"
    ) -> dict:
        """
        Calculate optimal bet size using Kelly Criterion.
        
        Args:
            bankroll: Current bankroll in USDC
            win_probability: Estimated probability of winning (0-1)
            current_price: Current market price (0-1)
            side: 'yes' or 'no'
            
        Returns:
            Dictionary with bet sizing information
        """
        # Validate inputs
        if not 0 < win_probability < 1:
            logger.warning(f"Invalid win probability: {win_probability}")
            return self._no_bet_result("Invalid win probability")
        
        if not 0 < current_price < 1:
            logger.warning(f"Invalid current price: {current_price}")
            return self._no_bet_result("Invalid current price")
        
        if bankroll <= 0:
            logger.warning(f"Invalid bankroll: {bankroll}")
            return self._no_bet_result("Invalid bankroll")
        
        # Calculate odds
        # For prediction markets: if buying YES at price p, you pay p to win 1
        # Net odds b = (1 - p) / p = (1/p) - 1
        if side.lower() == "yes":
            # Buying YES: pay current_price, win 1 if YES
            b = (1 / current_price) - 1
            p = win_probability
        else:
            # Buying NO: pay (1 - current_price), win 1 if NO
            b = (1 / (1 - current_price)) - 1
            p = 1 - win_probability
        
        q = 1 - p
        
        # Calculate Kelly fraction: f* = (bp - q) / b
        if b <= 0:
            logger.warning(f"Invalid odds: b={b}")
            return self._no_bet_result("Invalid odds")
        
        kelly_f = (b * p - q) / b
        
        # Apply fractional Kelly
        adjusted_kelly = kelly_f * self.kelly_fraction
        
        # Check if we have an edge
        if kelly_f <= 0:
            logger.info(f"No edge detected: kelly_f={kelly_f:.4f}")
            return self._no_bet_result("No positive edge")
        
        # Cap at maximum bet fraction
        final_fraction = min(adjusted_kelly, self.max_bet_fraction)
        
        # Calculate bet size in USDC
        bet_size = bankroll * final_fraction
        
        # Calculate expected value
        expected_value = (p * b - q) * bet_size
        
        # Calculate edge (expected value as percentage of bet)
        edge = (p * b - q) / 1 if b > 0 else 0
        
        result = {
            "should_bet": True,
            "bet_size": round(bet_size, 2),
            "bet_fraction": round(final_fraction, 4),
            "full_kelly": round(kelly_f, 4),
            "adjusted_kelly": round(adjusted_kelly, 4),
            "expected_value": round(expected_value, 2),
            "edge": round(edge, 4),
            "win_probability": round(p, 4),
            "odds": round(b, 4),
            "reason": f"Kelly: {kelly_f:.2%}, Adjusted: {adjusted_kelly:.2%}, Capped: {final_fraction:.2%}"
        }
        
        logger.info(f"Kelly calculation: {result}")
        return result
    
    def calculate_from_edge(
        self,
        bankroll: float,
        edge: float,
        win_probability: float
    ) -> dict:
        """
        Calculate bet size from edge and win probability.
        
        Args:
            bankroll: Current bankroll
            edge: Expected edge (expected value / bet)
            win_probability: Probability of winning
            
        Returns:
            Dictionary with bet sizing information
        """
        if edge <= 0:
            return self._no_bet_result("No positive edge")
        
        if not 0 < win_probability < 1:
            return self._no_bet_result("Invalid win probability")
        
        # From edge formula: edge = (p * b - q) / 1
        # And Kelly: f* = (bp - q) / b = edge
        # So full Kelly = edge
        kelly_f = edge
        
        # Apply fractional Kelly
        adjusted_kelly = kelly_f * self.kelly_fraction
        
        # Cap at maximum
        final_fraction = min(adjusted_kelly, self.max_bet_fraction)
        
        # Calculate bet size
        bet_size = bankroll * final_fraction
        expected_value = edge * bet_size
        
        result = {
            "should_bet": True,
            "bet_size": round(bet_size, 2),
            "bet_fraction": round(final_fraction, 4),
            "full_kelly": round(kelly_f, 4),
            "adjusted_kelly": round(adjusted_kelly, 4),
            "expected_value": round(expected_value, 2),
            "edge": round(edge, 4),
            "win_probability": round(win_probability, 4),
            "reason": f"Edge: {edge:.2%}, Kelly: {adjusted_kelly:.2%}, Final: {final_fraction:.2%}"
        }
        
        logger.info(f"Kelly from edge: {result}")
        return result
    
    @staticmethod
    def _no_bet_result(reason: str) -> dict:
        """Return a no-bet result."""
        return {
            "should_bet": False,
            "bet_size": 0,
            "bet_fraction": 0,
            "full_kelly": 0,
            "adjusted_kelly": 0,
            "expected_value": 0,
            "edge": 0,
            "win_probability": 0,
            "odds": 0,
            "reason": reason
        }
    
    def validate_bet_size(self, bet_size: float, bankroll: float) -> tuple[bool, str]:
        """
        Validate that a bet size is within acceptable limits.
        
        Args:
            bet_size: Proposed bet size
            bankroll: Current bankroll
            
        Returns:
            Tuple of (is_valid, reason)
        """
        if bet_size <= 0:
            return False, "Bet size must be positive"
        
        if bet_size > bankroll:
            return False, "Bet size exceeds bankroll"
        
        fraction = bet_size / bankroll
        if fraction > self.max_bet_fraction:
            return False, f"Bet size exceeds max fraction ({self.max_bet_fraction:.1%})"
        
        return True, "Valid bet size"


def calculate_implied_probability(price: float) -> float:
    """
    Calculate implied probability from market price.
    
    Args:
        price: Market price (0-1)
        
    Returns:
        Implied probability
    """
    if not 0 < price < 1:
        raise ValueError(f"Price must be between 0 and 1, got {price}")
    
    return price


def calculate_edge(
    estimated_probability: float,
    market_price: float,
    side: str = "yes"
) -> float:
    """
    Calculate edge (expected value).
    
    Args:
        estimated_probability: Your estimated probability of YES outcome
        market_price: Current market price for YES
        side: 'yes' or 'no'
        
    Returns:
        Edge as a fraction
    """
    if side.lower() == "yes":
        # Buying YES
        # EV = p * (1 - price) - (1 - p) * price
        # Simplified: EV = p - price
        edge = estimated_probability - market_price
    else:
        # Buying NO
        # EV = (1 - p) * (1 - (1 - price)) - p * (1 - price)
        # Simplified: EV = (1 - p) - (1 - price) = price - p
        edge = market_price - estimated_probability
    
    return edge
