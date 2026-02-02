"""
Market scanner to find trading opportunities.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger

from ..core.polymarket_client import PolymarketClient
from ..models.schemas import MarketData


class MarketScanner:
    """Scans Polymarket for trading opportunities."""
    
    def __init__(
        self,
        polymarket_client: PolymarketClient,
        min_liquidity: float = 10000,
        min_volume_24h: float = 5000,
        sports_filter: Optional[List[str]] = None
    ):
        """
        Initialize market scanner.
        
        Args:
            polymarket_client: Polymarket API client
            min_liquidity: Minimum liquidity threshold
            min_volume_24h: Minimum 24h volume
            sports_filter: List of sports to include
        """
        self.client = polymarket_client
        self.min_liquidity = min_liquidity
        self.min_volume_24h = min_volume_24h
        self.sports_filter = sports_filter or [
            "football", "soccer", "basketball", "tennis",
            "baseball", "american-football"
        ]
        
        logger.info(f"Market scanner initialized (min_liquidity=${min_liquidity})")
    
    def scan_markets(
        self,
        min_hours_until_event: int = 24,
        max_hours_until_event: int = 72,
        max_markets: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Scan for markets matching criteria.
        
        Args:
            min_hours_until_event: Minimum hours until event starts
            max_hours_until_event: Maximum hours until event starts
            max_markets: Maximum markets to return
            
        Returns:
            List of market dictionaries
        """
        logger.info("Scanning markets for opportunities...")
        
        # Get all active markets
        all_markets = self.client.get_markets(active=True, limit=200)
        
        # Filter markets
        filtered_markets = []
        
        for market in all_markets:
            # Check if it's a sports market
            if not self._is_sports_market(market):
                continue
            
            # Check liquidity
            if market.get("liquidity", 0) < self.min_liquidity:
                continue
            
            # Check volume
            if market.get("volume_24h", 0) < self.min_volume_24h:
                continue
            
            # Check event timing
            event_time = market.get("event_time")
            if event_time:
                hours_until = self._hours_until_event(event_time)
                if not (min_hours_until_event <= hours_until <= max_hours_until_event):
                    continue
            
            # Calculate opportunity score
            score = self._calculate_opportunity_score(market)
            market["opportunity_score"] = score
            
            filtered_markets.append(market)
        
        # Sort by opportunity score
        filtered_markets.sort(key=lambda x: x.get("opportunity_score", 0), reverse=True)
        
        # Limit results
        result = filtered_markets[:max_markets]
        
        logger.info(f"Found {len(result)} markets matching criteria")
        return result
    
    def _is_sports_market(self, market: Dict[str, Any]) -> bool:
        """Check if market is a sports market."""
        category = market.get("category", "").lower()
        question = market.get("question", "").lower()
        
        # Check category
        if any(sport in category for sport in self.sports_filter):
            return True
        
        # Check question for sports keywords
        sports_keywords = [
            "win", "score", "game", "match", "championship",
            "playoff", "league", "tournament", "vs", "against"
        ]
        
        if any(keyword in question for keyword in sports_keywords):
            return True
        
        return False
    
    def _hours_until_event(self, event_time: Any) -> float:
        """Calculate hours until event."""
        if isinstance(event_time, str):
            event_dt = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
        elif isinstance(event_time, datetime):
            event_dt = event_time
        else:
            return float('inf')
        
        now = datetime.utcnow()
        delta = event_dt - now
        
        return delta.total_seconds() / 3600
    
    def _calculate_opportunity_score(self, market: Dict[str, Any]) -> float:
        """
        Calculate opportunity score for a market.
        
        Higher score = better opportunity.
        
        Args:
            market: Market data
            
        Returns:
            Opportunity score
        """
        score = 0.0
        
        # Liquidity score (higher is better)
        liquidity = market.get("liquidity", 0)
        if liquidity > 50000:
            score += 3
        elif liquidity > 25000:
            score += 2
        elif liquidity > 10000:
            score += 1
        
        # Volume score (higher is better)
        volume = market.get("volume_24h", 0)
        if volume > 20000:
            score += 3
        elif volume > 10000:
            score += 2
        elif volume > 5000:
            score += 1
        
        # Price score (closer to 0.5 = more uncertain = more opportunity)
        yes_price = market.get("yes_price", 0.5)
        price_uncertainty = 1 - abs(yes_price - 0.5) * 2  # 0 to 1, higher = more uncertain
        score += price_uncertainty * 2
        
        # Time score (prefer events 24-48 hours out)
        event_time = market.get("event_time")
        if event_time:
            hours = self._hours_until_event(event_time)
            if 24 <= hours <= 48:
                score += 2
            elif 12 <= hours <= 72:
                score += 1
        
        return score
    
    def get_market_details(self, market_id: str) -> Optional[MarketData]:
        """
        Get detailed market information.
        
        Args:
            market_id: Market ID
            
        Returns:
            MarketData object or None
        """
        return self.client.get_market(market_id)
