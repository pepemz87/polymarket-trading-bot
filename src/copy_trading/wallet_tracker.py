"""
Wallet Tracker - Monitors target wallets on Polymarket for new trades.

Uses the Polymarket Gamma API and CLOB API to detect new positions
and trade activity from tracked wallets.
"""
import time
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Set
from sqlalchemy.orm import Session
from loguru import logger

from .models import TrackedWallet, CopiedTrade
from .schemas import WalletActivity, WalletDiscovery

# Polymarket API endpoints
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"
STRAPI_API_BASE = "https://strapi-matic.polymarket.com"


class WalletTracker:
    """
    Monitors Polymarket wallets for new trade activity.

    Detection methods:
    1. Gamma API - query user positions and trade history
    2. CLOB API - query order fills for specific addresses
    3. Polling interval - configurable scan frequency
    """

    def __init__(
        self,
        db_session: Session,
        polymarket_api_key: Optional[str] = None,
        scan_interval_seconds: int = 30,
        max_retries: int = 3,
    ):
        self.db = db_session
        self.api_key = polymarket_api_key
        self.scan_interval = scan_interval_seconds
        self.max_retries = max_retries

        # Track already-seen transactions to avoid duplicate processing
        self._seen_tx_hashes: Set[str] = set()
        self._last_scan_time: Optional[datetime] = None

        # Load previously seen transactions from DB
        self._load_seen_transactions()

        # HTTP session with retry headers
        self._http = requests.Session()
        self._http.headers.update({
            "Accept": "application/json",
            "User-Agent": "PolymarketCopyBot/1.0",
        })
        if self.api_key:
            self._http.headers["Authorization"] = f"Bearer {self.api_key}"

        logger.info(
            f"WalletTracker initialized (scan_interval={scan_interval_seconds}s)"
        )

    def _load_seen_transactions(self):
        """Load already-processed transaction hashes from DB."""
        try:
            recent = (
                self.db.query(CopiedTrade.source_tx_hash)
                .filter(CopiedTrade.source_tx_hash.isnot(None))
                .order_by(CopiedTrade.detected_at.desc())
                .limit(5000)
                .all()
            )
            self._seen_tx_hashes = {row[0] for row in recent}
            logger.info(f"Loaded {len(self._seen_tx_hashes)} seen transaction hashes")
        except Exception as e:
            logger.error(f"Error loading seen transactions: {e}")

    # ------------------------------------------------------------------
    # Wallet management
    # ------------------------------------------------------------------

    def add_wallet(
        self,
        address: str,
        label: Optional[str] = None,
        sizing_mode: str = "proportional",
        fixed_size: float = 10.0,
        proportional_factor: float = 1.0,
        percentage_of_bankroll: float = 0.05,
        copy_delay_seconds: int = 5,
        min_trade_size: float = 1.0,
        max_trade_size: float = 10000.0,
    ) -> TrackedWallet:
        """Add a wallet to track."""
        address = address.lower().strip()

        existing = (
            self.db.query(TrackedWallet)
            .filter(TrackedWallet.address == address)
            .first()
        )
        if existing:
            existing.is_active = True
            existing.label = label or existing.label
            existing.sizing_mode = sizing_mode
            existing.fixed_size = fixed_size
            existing.proportional_factor = proportional_factor
            existing.percentage_of_bankroll = percentage_of_bankroll
            existing.copy_delay_seconds = copy_delay_seconds
            self.db.commit()
            logger.info(f"Wallet {address[:10]}... reactivated with updated settings")
            return existing

        wallet = TrackedWallet(
            address=address,
            label=label,
            sizing_mode=sizing_mode,
            fixed_size=fixed_size,
            proportional_factor=proportional_factor,
            percentage_of_bankroll=percentage_of_bankroll,
            copy_delay_seconds=copy_delay_seconds,
            min_trade_size=min_trade_size,
            max_trade_size=max_trade_size,
        )
        self.db.add(wallet)
        self.db.commit()
        logger.info(f"Now tracking wallet: {address[:10]}... ({label or 'no label'})")
        return wallet

    def remove_wallet(self, address: str) -> bool:
        """Deactivate a tracked wallet."""
        address = address.lower().strip()
        wallet = (
            self.db.query(TrackedWallet)
            .filter(TrackedWallet.address == address)
            .first()
        )
        if wallet:
            wallet.is_active = False
            self.db.commit()
            logger.info(f"Wallet {address[:10]}... deactivated")
            return True
        return False

    def get_active_wallets(self) -> List[TrackedWallet]:
        """Get all active tracked wallets."""
        return (
            self.db.query(TrackedWallet)
            .filter(TrackedWallet.is_active == True)
            .all()
        )

    def get_wallet(self, address: str) -> Optional[TrackedWallet]:
        """Get a tracked wallet by address."""
        return (
            self.db.query(TrackedWallet)
            .filter(TrackedWallet.address == address.lower().strip())
            .first()
        )

    # ------------------------------------------------------------------
    # Trade detection via Gamma API
    # ------------------------------------------------------------------

    def _api_get(self, url: str, params: Optional[Dict] = None) -> Optional[Any]:
        """Make a GET request with retries."""
        for attempt in range(self.max_retries):
            try:
                resp = self._http.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    logger.warning(
                        f"API {resp.status_code} for {url}: {resp.text[:200]}"
                    )
                    return None
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error (attempt {attempt+1}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
        return None

    def get_wallet_positions(self, address: str) -> List[Dict[str, Any]]:
        """
        Fetch current positions for a wallet via Gamma API.

        Returns list of position dicts with keys like:
        market, outcome, size, avgPrice, currentPrice, etc.
        """
        url = f"{GAMMA_API_BASE}/positions"
        params = {"user": address.lower(), "sizeThreshold": 0}
        data = self._api_get(url, params)
        if data and isinstance(data, list):
            return data
        return []

    def get_wallet_trade_history(
        self,
        address: str,
        limit: int = 50,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent trade history for a wallet.

        Uses the Gamma API activity endpoint to get fills.
        """
        url = f"{GAMMA_API_BASE}/activity"
        params = {
            "user": address.lower(),
            "limit": limit,
            "type": "TRADE",
        }
        if since:
            params["startDate"] = since.isoformat()

        data = self._api_get(url, params)
        if data and isinstance(data, list):
            return data
        return []

    def get_wallet_orders(self, address: str) -> List[Dict[str, Any]]:
        """Fetch open orders for a wallet via CLOB API."""
        url = f"{CLOB_API_BASE}/orders"
        params = {"maker": address.lower(), "status": "live"}
        data = self._api_get(url, params)
        if data and isinstance(data, list):
            return data
        return []

    # ------------------------------------------------------------------
    # Core scanning loop
    # ------------------------------------------------------------------

    def scan_all_wallets(self) -> List[WalletActivity]:
        """
        Scan all active wallets for new trade activity.

        Returns:
            List of new WalletActivity objects not yet seen.
        """
        active_wallets = self.get_active_wallets()
        if not active_wallets:
            logger.debug("No active wallets to scan")
            return []

        all_activities: List[WalletActivity] = []

        for wallet in active_wallets:
            try:
                activities = self._scan_wallet(wallet)
                all_activities.extend(activities)
            except Exception as e:
                logger.error(
                    f"Error scanning wallet {wallet.address[:10]}...: {e}",
                    exc_info=True,
                )

        self._last_scan_time = datetime.utcnow()
        if all_activities:
            logger.info(
                f"Scan complete: {len(all_activities)} new activities across "
                f"{len(active_wallets)} wallets"
            )

        return all_activities

    def _scan_wallet(self, wallet: TrackedWallet) -> List[WalletActivity]:
        """Scan a single wallet for new activity."""
        since = wallet.last_activity or (datetime.utcnow() - timedelta(hours=24))
        raw_trades = self.get_wallet_trade_history(
            wallet.address, limit=50, since=since
        )

        new_activities: List[WalletActivity] = []

        for raw in raw_trades:
            try:
                activity = self._parse_raw_activity(wallet.address, raw)
                if activity is None:
                    continue
                if activity.tx_hash in self._seen_tx_hashes:
                    continue

                self._seen_tx_hashes.add(activity.tx_hash)
                new_activities.append(activity)
            except Exception as e:
                logger.warning(f"Error parsing activity: {e}")

        # Update last_activity timestamp
        if new_activities:
            wallet.last_activity = datetime.utcnow()
            self.db.commit()

        return new_activities

    def _parse_raw_activity(
        self, wallet_address: str, raw: Dict[str, Any]
    ) -> Optional[WalletActivity]:
        """
        Parse raw API response into a WalletActivity.

        The Gamma API returns objects like:
        {
            "id": "...",
            "type": "TRADE",
            "conditionId": "0x...",
            "tokenId": "...",
            "side": "BUY",
            "outcome": "Yes",
            "size": "50.0",
            "price": "0.65",
            "timestamp": "2026-01-15T10:30:00Z",
            "transactionHash": "0x...",
            "market": { "id": "...", "question": "...", "slug": "..." }
        }
        """
        tx_hash = raw.get("transactionHash") or raw.get("id") or raw.get("hash")
        if not tx_hash:
            return None

        side_raw = (raw.get("side") or "").upper()
        if side_raw not in ("BUY", "SELL"):
            return None

        outcome_raw = (raw.get("outcome") or "").lower()
        if outcome_raw not in ("yes", "no"):
            return None

        try:
            size = float(raw.get("size", 0))
        except (TypeError, ValueError):
            return None
        if size <= 0:
            return None

        try:
            price = float(raw.get("price", 0))
        except (TypeError, ValueError):
            price = 0.0

        # Parse timestamp
        ts_str = raw.get("timestamp") or raw.get("createdAt")
        if ts_str:
            try:
                timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                timestamp = timestamp.replace(tzinfo=None)
            except (ValueError, AttributeError):
                timestamp = datetime.utcnow()
        else:
            timestamp = datetime.utcnow()

        market_info = raw.get("market") or {}

        return WalletActivity(
            wallet_address=wallet_address,
            tx_hash=tx_hash,
            market_id=market_info.get("id") or raw.get("conditionId") or raw.get("marketId", ""),
            condition_id=raw.get("conditionId"),
            token_id=raw.get("tokenId"),
            market_question=market_info.get("question"),
            market_slug=market_info.get("slug"),
            side=side_raw.lower(),
            outcome=outcome_raw,
            size=size,
            price=price,
            timestamp=timestamp,
            block_number=raw.get("blockNumber"),
        )

    # ------------------------------------------------------------------
    # Wallet discovery - find profitable traders
    # ------------------------------------------------------------------

    def discover_top_traders(
        self,
        min_volume: float = 10000,
        min_markets: int = 5,
        limit: int = 20,
    ) -> List[WalletDiscovery]:
        """
        Discover profitable wallets via Gamma API leaderboard.

        Args:
            min_volume: Minimum total volume traded
            min_markets: Minimum number of markets traded
            limit: Maximum wallets to return

        Returns:
            List of WalletDiscovery objects sorted by profit
        """
        url = f"{GAMMA_API_BASE}/leaderboard"
        params = {"limit": limit, "window": "all"}
        data = self._api_get(url, params)

        if not data or not isinstance(data, list):
            logger.warning("Could not fetch leaderboard data")
            return []

        discoveries: List[WalletDiscovery] = []
        for i, entry in enumerate(data):
            try:
                volume = float(entry.get("volume", 0))
                markets = int(entry.get("marketsTraded", 0))
                if volume < min_volume or markets < min_markets:
                    continue

                profit = float(entry.get("profit", 0) or entry.get("pnl", 0))
                address = entry.get("address") or entry.get("user", "")
                if not address:
                    continue

                discoveries.append(WalletDiscovery(
                    address=address.lower(),
                    profit_total=profit,
                    volume_total=volume,
                    markets_traded=markets,
                    win_rate=float(entry.get("winRate", 0)),
                    avg_position_size=float(entry.get("avgPositionSize", 0)),
                    rank=i + 1,
                    source="gamma_api",
                ))
            except (ValueError, TypeError) as e:
                logger.debug(f"Skipping leaderboard entry: {e}")

        # Sort by profit descending
        discoveries.sort(key=lambda x: x.profit_total, reverse=True)
        logger.info(f"Discovered {len(discoveries)} profitable traders")
        return discoveries

    def discover_market_whales(
        self,
        market_id: str,
        min_position_size: float = 1000,
    ) -> List[WalletDiscovery]:
        """
        Find wallets with large positions in a specific market.

        Args:
            market_id: Polymarket condition ID
            min_position_size: Minimum position size in USDC

        Returns:
            List of WalletDiscovery objects
        """
        url = f"{GAMMA_API_BASE}/positions"
        params = {"market": market_id, "sizeThreshold": min_position_size}
        data = self._api_get(url, params)

        if not data or not isinstance(data, list):
            return []

        discoveries: List[WalletDiscovery] = []
        for entry in data:
            address = entry.get("user") or entry.get("address", "")
            if not address:
                continue
            try:
                size = float(entry.get("size", 0))
            except (ValueError, TypeError):
                size = 0

            discoveries.append(WalletDiscovery(
                address=address.lower(),
                volume_total=size,
                markets_traded=1,
                avg_position_size=size,
                source="gamma_api",
            ))

        discoveries.sort(key=lambda x: x.volume_total, reverse=True)
        return discoveries
