"""
Polymarket API client wrapper.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from loguru import logger

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType, ApiCreds
    CLOB_CLIENT_AVAILABLE = True
except ImportError:
    logger.warning("py-clob-client not installed. Install with: pip install py-clob-client")
    CLOB_CLIENT_AVAILABLE = False

from ..models.schemas import MarketData


class PolymarketClient:
    """Wrapper for Polymarket CLOB API."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        api_passphrase: Optional[str] = None,
        private_key: Optional[str] = None,
        chain_id: int = 137  # Polygon mainnet
    ):
        """
        Initialize Polymarket client.
        
        Args:
            api_key: Polymarket API key
            api_secret: Polymarket API secret
            api_passphrase: Polymarket API passphrase
            private_key: Wallet private key
            chain_id: Chain ID (137 for Polygon mainnet, 80001 for Mumbai testnet)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.private_key = private_key
        self.chain_id = chain_id
        
        self.client = None
        
        if CLOB_CLIENT_AVAILABLE and all([api_key, api_secret, api_passphrase, private_key]):
            try:
                # Initialize CLOB client with API credentials
                creds = ApiCreds(
                    api_key=api_key,
                    api_secret=api_secret,
                    api_passphrase=api_passphrase,
                )
                self.client = ClobClient(
                    "https://clob.polymarket.com",
                    key=private_key,
                    chain_id=chain_id,
                    creds=creds,
                )
                logger.info("Polymarket CLOB client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Polymarket client: {e}")
                self.client = None
        else:
            logger.warning("Polymarket client not fully configured (missing credentials or library)")
    
    def get_markets(
        self,
        active: bool = True,
        closed: bool = False,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get markets from Polymarket.
        
        Args:
            active: Include active markets
            closed: Include closed markets
            limit: Maximum number of markets to return
            
        Returns:
            List of market dictionaries
        """
        if not self.client:
            logger.warning("Polymarket client not initialized, returning empty list")
            return []
        
        try:
            # Use Gamma API to get markets
            # Note: This is a simplified version. Real implementation would use proper API calls
            markets = []
            
            # For now, return empty list as placeholder
            # In production, this would call: self.client.get_markets()
            logger.info(f"Fetched {len(markets)} markets from Polymarket")
            return markets
            
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return []
    
    def get_market(self, market_id: str) -> Optional[MarketData]:
        """
        Get specific market data.
        
        Args:
            market_id: Market ID or condition ID
            
        Returns:
            MarketData object or None
        """
        if not self.client:
            logger.warning("Polymarket client not initialized")
            return None
        
        try:
            # Fetch market data
            # Placeholder for actual API call
            logger.info(f"Fetching market: {market_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching market {market_id}: {e}")
            return None
    
    def get_orderbook(self, token_id: str) -> Dict[str, Any]:
        """
        Get orderbook for a token.
        
        Args:
            token_id: Token ID
            
        Returns:
            Orderbook data
        """
        if not self.client:
            return {"bids": [], "asks": []}
        
        try:
            # Get orderbook
            orderbook = self.client.get_order_book(token_id)
            return orderbook
            
        except Exception as e:
            logger.error(f"Error fetching orderbook: {e}")
            return {"bids": [], "asks": []}
    
    def get_price(self, token_id: str) -> Optional[float]:
        """
        Get current price for a token.

        Args:
            token_id: Token ID

        Returns:
            Current price or None
        """
        if not self.client:
            return None

        try:
            orderbook = self.client.get_order_book(token_id)

            # OrderBookSummary object - access attributes, not dict keys
            bids = getattr(orderbook, 'bids', None) or []
            asks = getattr(orderbook, 'asks', None) or []

            if bids and asks:
                best_bid = float(bids[0].price if hasattr(bids[0], 'price') else bids[0]['price'])
                best_ask = float(asks[0].price if hasattr(asks[0], 'price') else asks[0]['price'])
                return (best_bid + best_ask) / 2
        except Exception as e:
            logger.warning(f"Error getting price for {token_id[:20]}...: {e}")

        return None
    
    def place_order(
        self,
        token_id: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        order_type: str = "market"
    ) -> Optional[str]:
        """
        Place an order.
        
        Args:
            token_id: Token ID
            side: 'buy' or 'sell'
            size: Order size
            price: Limit price (for limit orders)
            order_type: 'market' or 'limit'
            
        Returns:
            Order ID or None
        """
        if not self.client:
            logger.error("Cannot place order: client not initialized")
            return None
        
        try:
            # Create order
            if order_type.lower() == "market":
                # Market order
                order = self.client.create_market_order(
                    token_id=token_id,
                    side=side.upper(),
                    size=size
                )
            else:
                # Limit order
                order = self.client.create_order(
                    token_id=token_id,
                    side=side.upper(),
                    size=size,
                    price=price
                )
            
            logger.info(f"Order placed: {order}")
            return order.get("id")
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID
            
        Returns:
            True if successful
        """
        if not self.client:
            return False
        
        try:
            self.client.cancel_order(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False
    
    def get_balance(self) -> Dict[str, float]:
        """
        Get account balance.
        
        Returns:
            Dictionary with balances
        """
        if not self.client:
            return {"USDC": 0}
        
        try:
            balance = self.client.get_balance()
            return balance
            
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return {"USDC": 0}
    
    def search_markets(
        self,
        query: str,
        sports_only: bool = True,
        min_liquidity: float = 10000
    ) -> List[Dict[str, Any]]:
        """
        Search for markets matching criteria.
        
        Args:
            query: Search query
            sports_only: Filter for sports markets only
            min_liquidity: Minimum liquidity threshold
            
        Returns:
            List of matching markets
        """
        markets = self.get_markets(active=True)
        
        filtered = []
        for market in markets:
            # Apply filters
            if sports_only:
                category = market.get("category", "").lower()
                if "sport" not in category:
                    continue
            
            if market.get("liquidity", 0) < min_liquidity:
                continue
            
            # Simple text search
            if query.lower() in market.get("question", "").lower():
                filtered.append(market)
        
        logger.info(f"Found {len(filtered)} markets matching criteria")
        return filtered
