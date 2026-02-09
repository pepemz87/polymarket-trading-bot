"""
Copy Trading Bot - Main orchestrator for the copy trading system.

Coordinates wallet tracking, trade evaluation, execution, and analytics.
"""
import time
import schedule
from datetime import datetime
from typing import Optional, List
from loguru import logger

from src.utils.config import get_config, Config
from src.utils.logger import setup_logger
from src.models.database import get_database, Base
from src.core.polymarket_client import PolymarketClient
from src.core.paper_trading import PaperTradingSimulator
from src.core.bankroll_manager import BankrollManager

from .models import TrackedWallet, CopiedTrade, WalletPerformance
from .wallet_tracker import WalletTracker
from .trade_copier import TradeCopier
from .analytics import CopyTradingAnalytics
from .schemas import CopyTradingStatus, WalletDiscovery


class CopyTradingBot:
    """
    Main copy trading bot orchestrator.

    Modes:
    - Paper trading (default): simulates all trades
    - Live trading: executes real trades on Polymarket

    Workflow:
    1. Initialize components (wallet tracker, trade copier, analytics)
    2. Scan tracked wallets for new activity
    3. Evaluate each activity against risk filters
    4. Execute approved copies
    5. Monitor open positions
    6. Generate performance reports
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        env_path: Optional[str] = None,
    ):
        # Load configuration
        self.config = get_config(config_path, env_path)
        self.logger = setup_logger(self.config.log_level)

        logger.info("=" * 60)
        logger.info("POLYMARKET COPY TRADING BOT STARTING")
        logger.info("=" * 60)

        # Copy trading specific config from YAML
        self._ct_config = self.config.get("copy_trading", {}) or {}

        # Initialize database (registers new tables too)
        self.db = get_database(self.config.database_url)
        # Create copy trading tables
        Base.metadata.create_all(self.db.engine)
        self.db_session = self.db.get_session()

        # Initialize trading client
        if self.config.is_paper_trading():
            logger.info("Running in PAPER TRADING mode")
            self.trading_client = PaperTradingSimulator(
                db_session=self.db_session,
                slippage=self.config.paper_trading.get("slippage", 0.002),
                fill_delay=self.config.paper_trading.get("fill_delay", 2.0),
            )
        else:
            logger.warning("Running in LIVE TRADING mode - real money at risk!")
            self.trading_client = PolymarketClient(
                api_key=self.config.polymarket_api_key,
                api_secret=self.config.polymarket_api_secret,
                api_passphrase=self.config.polymarket_api_passphrase,
                private_key=self.config.polymarket_private_key,
            )

        # Bankroll manager
        initial_bankroll = self._ct_config.get(
            "initial_bankroll",
            self.config.get("trading.initial_bankroll", 100),
        )
        max_positions = self._ct_config.get("max_positions", 20)
        portfolio_stop_loss = self._ct_config.get(
            "portfolio_stop_loss",
            self.config.get("trading.portfolio_stop_loss", 0.20),
        )
        self.bankroll_manager = BankrollManager(
            db_session=self.db_session,
            initial_bankroll=initial_bankroll,
            max_positions=max_positions,
            portfolio_stop_loss=portfolio_stop_loss,
        )

        # Wallet tracker
        scan_interval = self._ct_config.get("scan_interval_seconds", 30)
        max_trade_age = self._ct_config.get("max_trade_age_seconds", 300)
        self.wallet_tracker = WalletTracker(
            db_session=self.db_session,
            polymarket_api_key=self.config.polymarket_api_key,
            scan_interval_seconds=scan_interval,
            max_trade_age_seconds=max_trade_age,
        )

        # Trade copier
        self.trade_copier = TradeCopier(
            db_session=self.db_session,
            bankroll_manager=self.bankroll_manager,
            trading_client=self.trading_client,
            is_paper_trading=self.config.is_paper_trading(),
            max_slippage=self._ct_config.get("max_slippage", 0.03),
            max_total_exposure=self._ct_config.get("max_total_exposure", 0.80),
            max_single_market_exposure=self._ct_config.get(
                "max_single_market_exposure", 0.25
            ),
            max_open_positions=max_positions,
        )

        # Analytics
        self.analytics = CopyTradingAnalytics(self.db_session)

        # Clean up stale pending trades from previous crashes
        self._cleanup_stale_records()

        # Bot state
        self.is_running = False
        self.start_time: Optional[datetime] = None
        self._last_scan: Optional[datetime] = None
        self._scan_count = 0

        logger.info(
            f"Copy Trading Bot initialized: "
            f"bankroll=${initial_bankroll}, max_positions={max_positions}, "
            f"scan_interval={scan_interval}s, mode={'paper' if self.config.is_paper_trading() else 'live'}"
        )

    def _cleanup_stale_records(self):
        """Clean up stale pending trades and orphaned records from previous runs."""
        try:
            # Mark stale pending trades as failed
            stale_pending = (
                self.db_session.query(CopiedTrade)
                .filter(CopiedTrade.status == "pending")
                .all()
            )
            if stale_pending:
                for trade in stale_pending:
                    trade.status = "failed"
                    trade.error_message = "Stale pending from previous run"
                self.db_session.commit()
                logger.info(f"Cleaned up {len(stale_pending)} stale pending trades")
        except Exception as e:
            logger.warning(f"Error cleaning up stale records: {e}")
            try:
                self.db_session.rollback()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Wallet management (convenience wrappers)
    # ------------------------------------------------------------------

    def add_wallet(self, address: str, label: Optional[str] = None, **kwargs) -> TrackedWallet:
        """Add a wallet to track. See WalletTracker.add_wallet for all options."""
        return self.wallet_tracker.add_wallet(address, label=label, **kwargs)

    def remove_wallet(self, address: str) -> bool:
        """Stop tracking a wallet."""
        return self.wallet_tracker.remove_wallet(address)

    def list_wallets(self) -> list:
        """List all tracked wallets with stats."""
        return self.analytics.get_all_wallet_stats()

    def discover_traders(self, **kwargs) -> List[WalletDiscovery]:
        """Discover profitable traders from the Polymarket leaderboard."""
        return self.wallet_tracker.discover_top_traders(**kwargs)

    # ------------------------------------------------------------------
    # Core scan loop
    # ------------------------------------------------------------------

    def scan_and_copy(self):
        """
        Main scan cycle:
        1. Scan all wallets for new trades
        2. Evaluate each trade
        3. Execute approved copies
        """
        self._scan_count += 1
        logger.info(f"--- Scan #{self._scan_count} ---")

        try:
            # Get current bankroll
            bankroll = self.bankroll_manager.get_current_bankroll()
            status = self.bankroll_manager.get_status()
            logger.info(
                f"Bankroll: ${bankroll:.2f} "
                f"(available: ${status.available_capital:.2f}, "
                f"positions: {status.open_positions})"
            )

            if not status.is_trading_allowed:
                logger.warning(
                    f"Trading paused: stop_loss={status.stop_loss_triggered}, "
                    f"positions={status.open_positions}"
                )
                return

            # Scan for new activity
            activities = self.wallet_tracker.scan_all_wallets()
            if not activities:
                logger.debug("No new activity detected")
                self._last_scan = datetime.utcnow()
                return

            logger.info(f"Found {len(activities)} new trade activities")

            # Process each activity
            copied = 0
            skipped = 0
            for activity in activities:
                wallet = self.wallet_tracker.get_wallet(activity.wallet_address)
                if not wallet or not wallet.is_active:
                    continue

                # Evaluate
                decision = self.trade_copier.evaluate_copy(
                    wallet=wallet,
                    activity=activity,
                    current_bankroll=bankroll,
                )

                if decision.should_copy:
                    result = self.trade_copier.execute_copy(decision, wallet)
                    if result.success:
                        copied += 1
                        action = (
                            f"{decision.copy_side.upper()} {decision.copy_outcome.upper()}"
                        )
                        logger.info(
                            f"Copied trade from {wallet.label or wallet.address[:10]}...: "
                            f"{action} ${decision.copy_size:.2f}"
                        )
                    elif result.error and "already recorded" in result.error:
                        # Normal dedup - trade was processed in a previous scan
                        logger.debug(f"Duplicate trade skipped: {result.error}")
                    else:
                        logger.warning(f"Copy failed: {result.error}")
                else:
                    self.trade_copier.record_skipped_trade(decision)
                    skipped += 1
                    logger.debug(f"Skipped: {decision.reason}")

            self._last_scan = datetime.utcnow()
            logger.info(
                f"Scan complete: {copied} copied, {skipped} skipped "
                f"out of {len(activities)} activities"
            )

        except Exception as e:
            logger.error(f"Error in scan_and_copy: {e}")
            try:
                self.db_session.rollback()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def check_positions(self):
        """Check and manage open copied positions."""
        logger.info("Checking open positions...")
        try:
            open_positions = self.trade_copier.get_open_positions()
            if not open_positions:
                logger.debug("No open positions")
                return

            logger.info(f"Open positions: {len(open_positions)}")

            # Update unrealized P&L for each position
            for trade in open_positions:
                try:
                    # Try to get current price
                    if trade.token_id and hasattr(self.trading_client, "get_price"):
                        current_price = self.trading_client.get_price(trade.token_id)
                        if current_price is not None:
                            # Update unrealized P&L
                            if trade.outcome.lower() == "yes":
                                shares = trade.size / trade.entry_price
                                trade.unrealized_pnl = shares * current_price - trade.size
                            else:
                                entry_cost = 1 - trade.entry_price
                                shares = trade.size / entry_cost
                                trade.unrealized_pnl = (
                                    shares * (1 - current_price) - trade.size
                                )

                            # Check take-profit / stop-loss
                            pnl_pct = (trade.unrealized_pnl or 0) / trade.size if trade.size > 0 else 0
                            tp = self._ct_config.get("take_profit", 0.15)
                            sl = self._ct_config.get("stop_loss", 0.20)

                            if pnl_pct >= tp:
                                self.trade_copier.close_position(
                                    trade.id, current_price, reason="take_profit"
                                )
                            elif pnl_pct <= -sl:
                                self.trade_copier.close_position(
                                    trade.id, current_price, reason="stop_loss"
                                )
                except Exception as e:
                    logger.warning(f"Error checking position {trade.id}: {e}")

            self.db_session.commit()

        except Exception as e:
            logger.error(f"Error checking positions: {e}")
            try:
                self.db_session.rollback()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Running modes
    # ------------------------------------------------------------------

    def run_once(self):
        """Run a single scan cycle."""
        logger.info("Running single scan cycle...")
        self.start_time = datetime.utcnow()
        self.scan_and_copy()
        self.check_positions()
        self.analytics.save_daily_snapshot()
        logger.info("Single cycle complete")

    def run_continuous(self):
        """Run the bot continuously with scheduled scans."""
        scan_interval = self._ct_config.get("scan_interval_seconds", 30)
        position_check_interval = self._ct_config.get(
            "position_check_interval_minutes", 5
        )
        snapshot_interval = self._ct_config.get(
            "snapshot_interval_minutes", 60
        )

        logger.info(
            f"Starting continuous mode: scan every {scan_interval}s, "
            f"position check every {position_check_interval}m, "
            f"snapshots every {snapshot_interval}m"
        )

        # Schedule tasks
        schedule.every(scan_interval).seconds.do(self.scan_and_copy)
        schedule.every(position_check_interval).minutes.do(self.check_positions)
        schedule.every(snapshot_interval).minutes.do(self.analytics.save_daily_snapshot)

        # Initial run
        self.start_time = datetime.utcnow()
        self.is_running = True
        self.scan_and_copy()

        try:
            while self.is_running:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user (Ctrl+C)")
            self.stop()

    def stop(self):
        """Stop the bot gracefully."""
        logger.info("Stopping copy trading bot...")
        self.is_running = False
        self.analytics.save_daily_snapshot()
        self.db_session.close()
        logger.info("Copy trading bot stopped")

    # ------------------------------------------------------------------
    # Status and reporting
    # ------------------------------------------------------------------

    def get_status(self) -> CopyTradingStatus:
        """Get current system status."""
        bankroll = self.bankroll_manager.get_current_bankroll()
        available = self.bankroll_manager.get_available_capital()
        return self.analytics.get_system_status(
            is_running=self.is_running,
            mode="paper" if self.config.is_paper_trading() else "live",
            bankroll=bankroll,
            available_capital=available,
            start_time=self.start_time,
            last_scan=self._last_scan,
        )

    def print_status(self):
        """Print a formatted status report to the logger."""
        status = self.get_status()
        logger.info("=" * 50)
        logger.info("COPY TRADING STATUS")
        logger.info("=" * 50)
        logger.info(f"Mode:            {status.mode}")
        logger.info(f"Running:         {status.is_running}")
        logger.info(f"Wallets:         {status.active_wallets}/{status.total_wallets_tracked}")
        logger.info(f"Open Positions:  {status.open_positions}")
        logger.info(f"Total Exposure:  ${status.total_exposure:.2f}")
        logger.info(f"Bankroll:        ${status.bankroll:.2f}")
        logger.info(f"Available:       ${status.available_capital:.2f}")
        logger.info(f"Total P&L:       ${status.total_pnl:.2f}")
        logger.info(f"Win Rate:        {status.overall_win_rate:.1%}")
        logger.info(f"Trades Copied:   {status.total_trades_copied}")
        logger.info(f"Trades Skipped:  {status.total_trades_skipped}")

        if status.top_wallets:
            logger.info("-" * 50)
            logger.info("TOP WALLETS:")
            for w in status.top_wallets:
                logger.info(
                    f"  {w.label or w.address[:12]}... | "
                    f"P&L: ${w.total_pnl:.2f} | "
                    f"WR: {w.win_rate:.0%} | "
                    f"Trades: {w.total_trades_copied}"
                )
        logger.info("=" * 50)
