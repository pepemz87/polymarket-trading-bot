"""
Polymarket API client wrapper.
"""
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from loguru import logger

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType, ApiCreds, MarketOrderArgs, RequestArgs
    from py_clob_client.headers.headers import create_level_2_headers
    from py_clob_client.utilities import order_to_json
    CLOB_CLIENT_AVAILABLE = True
except ImportError:
    logger.warning("py-clob-client not installed. Install with: pip install py-clob-client")
    CLOB_CLIENT_AVAILABLE = False

# Try to import curl_cffi for Cloudflare bypass
try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
    logger.info("curl_cffi available - Cloudflare bypass enabled")
except ImportError:
    CURL_CFFI_AVAILABLE = False
    logger.warning("curl_cffi not installed - POST requests may be blocked by Cloudflare")

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
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.private_key = private_key
        self.chain_id = chain_id

        self.client = None

        if CLOB_CLIENT_AVAILABLE and all([api_key, api_secret, api_passphrase, private_key]):
            try:
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

                # Monkey-patch the py-clob-client HTTP helpers to bypass Cloudflare
                if CURL_CFFI_AVAILABLE:
                    self._patch_http_helpers()

            except Exception as e:
                logger.error(f"Failed to initialize Polymarket client: {e}")
                self.client = None
        else:
            logger.warning("Polymarket client not fully configured (missing credentials or library)")

    def _patch_http_helpers(self):
        """
        Monkey-patch py-clob-client's HTTP helpers to use curl_cffi
        instead of httpx, bypassing Cloudflare's TLS fingerprint detection.
        """
        try:
            import py_clob_client.http_helpers.helpers as helpers

            original_request = helpers.request

            def patched_request(endpoint: str, method: str, headers=None, data=None):
                """Replace httpx with curl_cffi for all HTTP requests."""
                if headers is None:
                    headers = {}

                # Add standard headers
                headers["Accept"] = "*/*"
                headers["Connection"] = "keep-alive"
                headers["Content-Type"] = "application/json"

                try:
                    if method.upper() == "GET":
                        headers["Accept-Encoding"] = "gzip"
                        resp = curl_requests.get(
                            endpoint,
                            headers=headers,
                            timeout=30,
                            impersonate="chrome",
                        )
                    else:
                        if isinstance(data, str):
                            resp = curl_requests.post(
                                endpoint,
                                headers=headers,
                                data=data.encode("utf-8"),
                                timeout=30,
                                impersonate="chrome",
                            )
                        else:
                            resp = curl_requests.post(
                                endpoint,
                                headers=headers,
                                json=data,
                                timeout=30,
                                impersonate="chrome",
                            )

                    if resp.status_code != 200:
                        from py_clob_client.exceptions import PolyApiException
                        raise PolyApiException(resp)

                    try:
                        return resp.json()
                    except ValueError:
                        return resp.text

                except Exception as e:
                    if "PolyApiException" in type(e).__name__:
                        raise
                    logger.error(f"curl_cffi request error: {e}")
                    # Fallback to original httpx request
                    return original_request(endpoint, method, headers, data)

            # Apply the patch
            helpers.request = patched_request
            helpers.get = lambda endpoint, headers=None, data=None: patched_request(endpoint, "GET", headers, data)
            helpers.post = lambda endpoint, headers=None, data=None: patched_request(endpoint, "POST", headers, data)

            logger.info("HTTP helpers patched with curl_cffi (Cloudflare bypass active)")

        except Exception as e:
            logger.warning(f"Failed to patch HTTP helpers: {e}")

    def get_markets(
        self,
        active: bool = True,
        closed: bool = False,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        if not self.client:
            logger.warning("Polymarket client not initialized, returning empty list")
            return []

        try:
            markets = []
            logger.info(f"Fetched {len(markets)} markets from Polymarket")
            return markets

        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return []

    def get_market(self, market_id: str) -> Optional[MarketData]:
        if not self.client:
            return None

        try:
            logger.info(f"Fetching market: {market_id}")
            return None

        except Exception as e:
            logger.error(f"Error fetching market {market_id}: {e}")
            return None

    def get_orderbook(self, token_id: str) -> Dict[str, Any]:
        if not self.client:
            return {"bids": [], "asks": []}

        try:
            orderbook = self.client.get_order_book(token_id)
            return orderbook

        except Exception as e:
            logger.error(f"Error fetching orderbook: {e}")
            return {"bids": [], "asks": []}

    def get_price(self, token_id: str) -> Optional[float]:
        """Get current price for a token."""
        if not self.client:
            return None

        try:
            orderbook = self.client.get_order_book(token_id)

            bids = getattr(orderbook, 'bids', None) or []
            asks = getattr(orderbook, 'asks', None) or []

            if bids and asks:
                best_bid = float(bids[0].price if hasattr(bids[0], 'price') else bids[0]['price'])
                best_ask = float(asks[0].price if hasattr(asks[0], 'price') else asks[0]['price'])
                mid = (best_bid + best_ask) / 2
                logger.debug(
                    f"Orderbook for {token_id[:20]}...: "
                    f"bid={best_bid:.4f}, ask={best_ask:.4f}, mid={mid:.4f}, "
                    f"depth={len(bids)}b/{len(asks)}a"
                )
                return mid
            else:
                logger.warning(
                    f"Empty orderbook for {token_id[:20]}...: "
                    f"bids={len(bids)}, asks={len(asks)}"
                )
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
        """Place an order on Polymarket."""
        if not self.client:
            logger.error("Cannot place order: client not initialized")
            return None

        try:
            side_enum = "BUY" if side.upper() == "BUY" else "SELL"

            if order_type.lower() == "market":
                market_args = MarketOrderArgs(
                    token_id=token_id,
                    amount=size,
                    side=side_enum,
                )
                logger.info(
                    f"Placing market order: {side_enum} ${size:.2f} "
                    f"token={token_id[:20]}..."
                )
                order = self.client.create_market_order(market_args)
            else:
                # For limit orders, size is in shares (not USDC)
                # Convert USDC amount to shares: shares = usdc_amount / price
                if price and price > 0:
                    shares = round(size / price, 2)
                else:
                    shares = size
                order_args = OrderArgs(
                    token_id=token_id,
                    price=price,
                    size=shares,
                    side=side_enum,
                )
                logger.info(
                    f"Placing limit order: {side_enum} {shares} shares @ {price} "
                    f"(${size:.2f} USDC) token={token_id[:20]}..."
                )
                order = self.client.create_order(order_args)

            logger.info(f"Order created, posting...")

            # Post order - this uses the patched HTTP helpers if curl_cffi is available
            # Use GTC for limit orders (stays in orderbook), FOK for market orders (fill or kill)
            ot = OrderType.FOK if order_type.lower() == "market" else OrderType.GTC
            resp = self.client.post_order(order, orderType=ot)
            logger.info(f"Order response: {resp}")

            if isinstance(resp, dict):
                return resp.get("orderID") or resp.get("id") or str(resp)
            return str(resp)

        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
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
        markets = self.get_markets(active=True)

        filtered = []
        for market in markets:
            if sports_only:
                category = market.get("category", "").lower()
                if "sport" not in category:
                    continue

            if market.get("liquidity", 0) < min_liquidity:
                continue

            if query.lower() in market.get("question", "").lower():
                filtered.append(market)

        logger.info(f"Found {len(filtered)} markets matching criteria")
        return filtered
