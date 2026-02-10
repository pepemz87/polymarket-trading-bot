"""
Polymarket API client wrapper.
"""
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from loguru import logger

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import (
        OrderArgs, OrderType, ApiCreds, MarketOrderArgs, RequestArgs,
        PartialCreateOrderOptions,
    )
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

        if not CLOB_CLIENT_AVAILABLE:
            logger.warning("Polymarket client not available (py-clob-client not installed)")
            return

        if not private_key:
            logger.warning("Polymarket client not configured (missing private key)")
            return

        try:
            # If we have all 4 credentials, use them directly
            if all([api_key, api_secret, api_passphrase]):
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
                logger.info("Polymarket CLOB client initialized with provided credentials")
            else:
                # Auto-derive API credentials from private key alone
                logger.info("API key/secret/passphrase not provided, deriving from private key...")
                self.client = ClobClient(
                    "https://clob.polymarket.com",
                    key=private_key,
                    chain_id=chain_id,
                )

                # Monkey-patch HTTP before deriving (needs network calls)
                if CURL_CFFI_AVAILABLE:
                    self._patch_http_helpers()

                creds = self.client.create_or_derive_api_creds()
                if creds:
                    self.api_key = creds.api_key
                    self.api_secret = creds.api_secret
                    self.api_passphrase = creds.api_passphrase

                    # Re-initialize with full credentials
                    self.client = ClobClient(
                        "https://clob.polymarket.com",
                        key=private_key,
                        chain_id=chain_id,
                        creds=creds,
                    )
                    logger.info("Polymarket CLOB client initialized with derived credentials")
                else:
                    logger.error("Failed to derive API credentials from private key")
                    self.client = None
                    return

            # Monkey-patch the py-clob-client HTTP helpers to bypass Cloudflare
            if CURL_CFFI_AVAILABLE:
                self._patch_http_helpers()

        except Exception as e:
            logger.error(f"Failed to initialize Polymarket client: {e}", exc_info=True)
            self.client = None

    def _patch_http_helpers(self):
        """
        Monkey-patch py-clob-client's HTTP helpers to use curl_cffi
        instead of httpx, bypassing Cloudflare's TLS fingerprint detection.
        """
        try:
            import py_clob_client.http_helpers.helpers as helpers

            original_request = helpers.request

            # WARP SOCKS5 proxy for Cloudflare bypass
            warp_proxy = "socks5h://127.0.0.1:40000"

            # Browser-like headers to pass Cloudflare WAF
            browser_headers = {
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
                "Content-Type": "application/json",
                "Origin": "https://polymarket.com",
                "Referer": "https://polymarket.com/",
                "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
            }

            def patched_request(endpoint: str, method: str, headers=None, data=None):
                """Replace httpx with curl_cffi for all HTTP requests via WARP proxy."""
                if headers is None:
                    headers = {}

                # Merge browser headers (don't overwrite auth headers from py-clob-client)
                merged = {**browser_headers, **headers}

                try:
                    if method.upper() == "GET":
                        resp = curl_requests.get(
                            endpoint,
                            headers=merged,
                            timeout=30,
                            impersonate="chrome",
                            proxy=warp_proxy,
                        )
                    else:
                        if isinstance(data, str):
                            resp = curl_requests.post(
                                endpoint,
                                headers=merged,
                                data=data.encode("utf-8"),
                                timeout=30,
                                impersonate="chrome",
                                proxy=warp_proxy,
                            )
                        else:
                            resp = curl_requests.post(
                                endpoint,
                                headers=merged,
                                json=data,
                                timeout=30,
                                impersonate="chrome",
                                proxy=warp_proxy,
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

            logger.info("HTTP helpers patched with curl_cffi + WARP proxy (Cloudflare bypass active)")

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
        order_type: str = "market",
        tick_size: str = "0.01",
        neg_risk: bool = False,
    ) -> Optional[str]:
        """
        Place an order on Polymarket.

        Args:
            token_id: The conditional token ID
            side: "buy" or "sell"
            size: Amount in USDC (for buys) or shares (for sells)
            price: Limit price (required for limit orders)
            order_type: "market" or "limit"
            tick_size: Price tick size for the market ("0.1", "0.01", "0.001", "0.0001")
            neg_risk: Whether the market uses negative risk framework
        """
        if not self.client:
            logger.error("Cannot place order: client not initialized")
            return None

        try:
            side_enum = "BUY" if side.upper() == "BUY" else "SELL"

            # Build order options with tick_size and neg_risk
            order_options = PartialCreateOrderOptions(
                tick_size=tick_size,
                neg_risk=neg_risk,
            )

            if order_type.lower() == "market":
                market_args = MarketOrderArgs(
                    token_id=token_id,
                    amount=size,
                    side=side_enum,
                )
                logger.info(
                    f"Placing market order: {side_enum} ${size:.2f} "
                    f"token={token_id[:20]}... "
                    f"(tick_size={tick_size}, neg_risk={neg_risk})"
                )
                order = self.client.create_market_order(market_args, options=order_options)
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
                    f"(${size:.2f} USDC) token={token_id[:20]}... "
                    f"(tick_size={tick_size}, neg_risk={neg_risk})"
                )
                order = self.client.create_order(order_args, options=order_options)

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
            error_detail = str(e)
            # Try to extract more detail from PolyApiException
            if hasattr(e, 'error_msg'):
                error_detail = f"status={getattr(e, 'status_code', '?')}, body={e.error_msg}"
            elif hasattr(e, 'response'):
                try:
                    error_detail = f"status={e.response.status_code}, body={e.response.text[:500]}"
                except Exception:
                    pass
            logger.error(
                f"Error placing order: {error_detail} "
                f"(token={token_id[:20]}..., side={side}, size={size}, price={price}, "
                f"tick_size={tick_size}, neg_risk={neg_risk})",
                exc_info=True,
            )
            return None

    def get_market_info(self, token_id: str) -> Dict[str, Any]:
        """
        Get market info for a token, including tick_size and neg_risk.

        Uses CLOB API first (has minimum_tick_size, neg_risk, tokens),
        then falls back to Gamma API (has orderPriceMinTickSize, negRisk
        on event, and clobTokenIds/outcomes mapping).

        Returns dict with keys: tick_size, neg_risk, condition_id, tokens, etc.
        Falls back to safe defaults if all API calls fail.
        """
        defaults = {"tick_size": "0.01", "neg_risk": False, "tokens": []}
        if not self.client:
            return defaults

        # Try CLOB API first
        try:
            url = f"https://clob.polymarket.com/markets/{token_id}"
            if CURL_CFFI_AVAILABLE:
                resp = curl_requests.get(
                    url,
                    timeout=10,
                    impersonate="chrome",
                    proxy="socks5h://127.0.0.1:40000",
                )
            else:
                import requests as _requests
                resp = _requests.get(url, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                tick_size = data.get("minimum_tick_size", "0.01")
                neg_risk = data.get("neg_risk", False)
                tokens = data.get("tokens", [])
                condition_id = data.get("condition_id", "")
                logger.debug(
                    f"Market info for {token_id[:20]}...: "
                    f"tick_size={tick_size}, neg_risk={neg_risk}, "
                    f"tokens={len(tokens)}"
                )
                return {
                    "tick_size": str(tick_size),
                    "neg_risk": bool(neg_risk),
                    "tokens": tokens,
                    "condition_id": condition_id,
                }
        except Exception as e:
            logger.debug(f"CLOB market info failed for {token_id[:20]}...: {e}")

        # Fallback: Gamma API (has orderPriceMinTickSize and event-level negRisk)
        try:
            url = f"https://gamma-api.polymarket.com/markets?clob_token_ids={token_id}"
            if CURL_CFFI_AVAILABLE:
                resp = curl_requests.get(
                    url,
                    timeout=10,
                    impersonate="chrome",
                    proxy="socks5h://127.0.0.1:40000",
                )
            else:
                import requests as _requests
                resp = _requests.get(url, timeout=10)

            if resp.status_code == 200:
                markets = resp.json()
                if markets and isinstance(markets, list) and len(markets) > 0:
                    mkt = markets[0]
                    tick_size = mkt.get("orderPriceMinTickSize", 0.01)
                    # negRisk is on the event, not market; check events array
                    neg_risk = False
                    events = mkt.get("events", [])
                    if events and isinstance(events, list):
                        neg_risk = events[0].get("negRisk", False)

                    # Build tokens list from clobTokenIds + outcomes
                    tokens = self._parse_gamma_tokens(mkt)

                    logger.debug(
                        f"Gamma market info for {token_id[:20]}...: "
                        f"tick_size={tick_size}, neg_risk={neg_risk}, "
                        f"tokens={len(tokens)}"
                    )
                    return {
                        "tick_size": str(tick_size),
                        "neg_risk": bool(neg_risk),
                        "tokens": tokens,
                        "condition_id": mkt.get("conditionId", ""),
                    }
        except Exception as e:
            logger.debug(f"Gamma market info failed for {token_id[:20]}...: {e}")

        return defaults

    def _parse_gamma_tokens(self, market_data: Dict) -> List[Dict]:
        """
        Parse Gamma API market data to extract token_id ↔ outcome mapping.

        Gamma API returns clobTokenIds and outcomes as JSON strings:
          clobTokenIds: '["token_yes", "token_no"]'
          outcomes: '["Yes", "No"]'
        These map 1:1 by index.
        """
        tokens = []
        try:
            clob_ids_raw = market_data.get("clobTokenIds", "[]")
            outcomes_raw = market_data.get("outcomes", "[]")

            clob_ids = json.loads(clob_ids_raw) if isinstance(clob_ids_raw, str) else clob_ids_raw
            outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw

            if isinstance(clob_ids, list) and isinstance(outcomes, list):
                for i, token_id in enumerate(clob_ids):
                    outcome = outcomes[i] if i < len(outcomes) else f"outcome_{i}"
                    tokens.append({
                        "token_id": str(token_id),
                        "outcome": str(outcome),
                    })
        except (json.JSONDecodeError, TypeError, IndexError) as e:
            logger.debug(f"Error parsing Gamma tokens: {e}")

        return tokens

    def get_opposite_token_id(
        self, condition_id: str, current_outcome: str
    ) -> Optional[str]:
        """
        Get the token_id for the opposite outcome in a market.

        On Polymarket, each market has YES and NO tokens. Given one outcome,
        this returns the token_id for the other.

        Uses Gamma API (condition_ids query with clobTokenIds/outcomes mapping)
        as primary source, CLOB API as fallback.

        Args:
            condition_id: The market's condition ID
            current_outcome: 'yes' or 'no'

        Returns:
            token_id of the opposite outcome, or None if not found
        """
        if not self.client:
            return None

        opposite = "no" if current_outcome.lower() == "yes" else "yes"

        # Try Gamma API first - most reliable for clobTokenIds ↔ outcomes mapping
        try:
            url = f"https://gamma-api.polymarket.com/markets?condition_ids={condition_id}"
            if CURL_CFFI_AVAILABLE:
                resp = curl_requests.get(
                    url,
                    timeout=10,
                    impersonate="chrome",
                    proxy="socks5h://127.0.0.1:40000",
                )
            else:
                import requests as _requests
                resp = _requests.get(url, timeout=10)

            if resp.status_code == 200:
                markets = resp.json()
                if markets and isinstance(markets, list) and len(markets) > 0:
                    tokens = self._parse_gamma_tokens(markets[0])
                    for token in tokens:
                        if token.get("outcome", "").lower() == opposite:
                            opp_id = token.get("token_id")
                            logger.info(
                                f"Resolved opposite token (Gamma): "
                                f"{current_outcome.upper()} → {opposite.upper()} = "
                                f"{opp_id[:20] if opp_id else 'None'}..."
                            )
                            return opp_id
        except Exception as e:
            logger.debug(f"Gamma opposite token lookup failed: {e}")

        # Fallback: CLOB API
        try:
            url = f"https://clob.polymarket.com/markets/{condition_id}"
            if CURL_CFFI_AVAILABLE:
                resp = curl_requests.get(
                    url,
                    timeout=10,
                    impersonate="chrome",
                    proxy="socks5h://127.0.0.1:40000",
                )
            else:
                import requests as _requests
                resp = _requests.get(url, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                tokens = data.get("tokens", [])
                for token in tokens:
                    if token.get("outcome", "").lower() == opposite:
                        opp_id = token.get("token_id")
                        logger.info(
                            f"Resolved opposite token (CLOB): "
                            f"{current_outcome.upper()} → {opposite.upper()} = "
                            f"{opp_id[:20] if opp_id else 'None'}..."
                        )
                        return opp_id
        except Exception as e:
            logger.warning(f"Could not resolve opposite token_id: {e}")

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
