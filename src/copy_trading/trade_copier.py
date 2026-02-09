"""
Trade Copier - Executes copy trades based on detected wallet activity.

Handles:
- Sizing calculation (proportional, fixed, percentage)
- Risk filtering (size limits, exposure limits, category filters)
- Order execution (paper or live)
- Slippage tracking
- Copy delay enforcement
"""
import time
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from loguru import logger

from .models import TrackedWallet, CopiedTrade
from .schemas import WalletActivity, CopyDecision, CopyTradeResult
from src.core.bankroll_manager import BankrollManager


class TradeCopier:
    """
    Decides whether to copy a trade and executes it.

    Flow:
    1. Receive WalletActivity from WalletTracker
    2. Run risk filters (size, exposure, category, market blacklist)
    3. Calculate copy size based on wallet's sizing_mode
    4. Enforce copy delay
    5. Execute trade (paper or live)
    6. Record result in DB
    """

    def __init__(
        self,
        db_session: Session,
        bankroll_manager: BankrollManager,
        trading_client,  # PaperTradingSimulator or PolymarketClient
        is_paper_trading: bool = True,
        max_slippage: float = 0.03,
        max_total_exposure: float = 0.80,
        max_single_market_exposure: float = 0.25,
        max_open_positions: int = 20,
    ):
        self.db = db_session
        self.bankroll_manager = bankroll_manager
        self.trading_client = trading_client
        self.is_paper_trading = is_paper_trading

        # Risk parameters
        self.max_slippage = max_slippage
        self.max_total_exposure = max_total_exposure
        self.max_single_market_exposure = max_single_market_exposure
        self.max_open_positions = max_open_positions

        logger.info(
            f"TradeCopier initialized (paper={is_paper_trading}, "
            f"max_slippage={max_slippage}, max_exposure={max_total_exposure})"
        )

    # ------------------------------------------------------------------
    # Decision making
    # ------------------------------------------------------------------

    def evaluate_copy(
        self,
        wallet: TrackedWallet,
        activity: WalletActivity,
        current_bankroll: float,
    ) -> CopyDecision:
        """
        Decide whether to copy a trade and determine sizing.

        Args:
            wallet: The tracked wallet config
            activity: The detected trade activity
            current_bankroll: Our current bankroll in USDC

        Returns:
            CopyDecision with the verdict and reasoning
        """
        # Check if we should copy this side (buy/sell)
        if activity.side == "buy" and not wallet.copy_buys:
            return self._skip(wallet, activity, "copy_buys disabled for this wallet")
        if activity.side == "sell" and not wallet.copy_sells:
            return self._skip(wallet, activity, "copy_sells disabled for this wallet")

        # Size filter
        if activity.size < wallet.min_trade_size:
            return self._skip(
                wallet, activity,
                f"Trade size ${activity.size:.2f} below minimum ${wallet.min_trade_size:.2f}",
                passes_size_filter=False,
            )

        # Category filter
        if wallet.allowed_categories:
            # We'd need market category info; for now pass if no category data
            pass

        # Market blacklist
        if wallet.blocked_markets and activity.market_id in wallet.blocked_markets:
            return self._skip(
                wallet, activity,
                f"Market {activity.market_id} is blacklisted",
                passes_market_filter=False,
            )

        # Determine what OUR trade should be:
        # - BUY trades: we copy directly (BUY the same outcome)
        # - SELL trades: the tracked wallet is selling tokens they own.
        #   We likely don't own those tokens, so we convert:
        #     SELL YES @ P  →  BUY NO  @ (1-P)  (economic equivalent)
        #     SELL NO  @ P  →  BUY YES @ (1-P)  (economic equivalent)
        #   UNLESS we already have an open position in the same market/outcome,
        #   in which case we should close it (actual SELL).
        copy_side = activity.side
        copy_outcome = activity.outcome
        copy_price = activity.price

        if activity.side == "sell":
            # Check if we have an open position in this market/outcome to close
            existing_position = (
                self.db.query(CopiedTrade)
                .filter(
                    CopiedTrade.market_id == activity.market_id,
                    CopiedTrade.outcome == activity.outcome,
                    CopiedTrade.side == "buy",
                    CopiedTrade.status == "executed",
                )
                .first()
            )
            if existing_position:
                # We own these tokens, so we can sell them to close
                copy_side = "sell"
                copy_outcome = activity.outcome
                copy_price = activity.price
                logger.info(
                    f"SELL copy: closing existing {activity.outcome.upper()} position "
                    f"(trade #{existing_position.id})"
                )
            else:
                # We don't own these tokens - convert to buying the opposite outcome
                copy_side = "buy"
                copy_outcome = "no" if activity.outcome == "yes" else "yes"
                copy_price = round(1.0 - activity.price, 4)
                logger.info(
                    f"SELL copy: no position to close, converting "
                    f"SELL {activity.outcome.upper()} @ {activity.price:.4f} → "
                    f"BUY {copy_outcome.upper()} @ {copy_price:.4f}"
                )

        # Check bankroll availability
        available = self.bankroll_manager.get_available_capital()
        if available <= 0:
            return self._skip(
                wallet, activity,
                "No available capital",
                passes_bankroll_check=False,
            )

        # Check total exposure
        bankroll_status = self.bankroll_manager.get_status()
        if bankroll_status.total_exposure > current_bankroll * self.max_total_exposure:
            return self._skip(
                wallet, activity,
                f"Total exposure exceeds {self.max_total_exposure:.0%} of bankroll",
                passes_exposure_check=False,
            )

        # Check max open positions (0 = unlimited)
        if self.max_open_positions > 0:
            open_count = (
                self.db.query(CopiedTrade)
                .filter(CopiedTrade.status.in_(["executed", "pending"]))
                .count()
            )
            if open_count >= self.max_open_positions:
                return self._skip(
                    wallet, activity,
                    f"Max open positions ({self.max_open_positions}) reached",
                    passes_exposure_check=False,
                )

        # Check single-market exposure
        market_exposure = (
            self.db.query(CopiedTrade)
            .filter(
                CopiedTrade.market_id == activity.market_id,
                CopiedTrade.status.in_(["executed", "pending"]),
            )
            .count()
        )
        max_per_market = max(3, self.max_open_positions // 4)
        if market_exposure >= max_per_market:
            return self._skip(
                wallet, activity,
                f"Already {market_exposure} positions in this market",
                passes_exposure_check=False,
            )

        # Calculate copy size
        copy_size = self._calculate_copy_size(
            wallet, activity, current_bankroll, available
        )

        if copy_size <= 0:
            return self._skip(wallet, activity, "Calculated copy size is 0")

        return CopyDecision(
            should_copy=True,
            reason="All filters passed",
            copy_size=round(copy_size, 2),
            copy_side=copy_side,
            copy_outcome=copy_outcome,
            target_price=copy_price,
            source_wallet=wallet.address,
            source_activity=activity,
        )

    def _calculate_copy_size(
        self,
        wallet: TrackedWallet,
        activity: WalletActivity,
        bankroll: float,
        available: float,
    ) -> float:
        """Calculate the USDC size for our copy trade."""
        if wallet.sizing_mode == "fixed":
            size = wallet.fixed_size
        elif wallet.sizing_mode == "percentage":
            size = bankroll * wallet.percentage_of_bankroll
        elif wallet.sizing_mode == "proportional":
            size = activity.size * wallet.proportional_factor
        else:
            size = wallet.fixed_size  # fallback

        # Apply caps
        size = min(size, wallet.max_trade_size)
        size = min(size, available)
        size = max(size, 0)

        return size

    def _skip(
        self,
        wallet: TrackedWallet,
        activity: WalletActivity,
        reason: str,
        **kwargs,
    ) -> CopyDecision:
        """Create a skip decision."""
        return CopyDecision(
            should_copy=False,
            reason=reason,
            source_wallet=wallet.address,
            source_activity=activity,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Trade execution
    # ------------------------------------------------------------------

    def execute_copy(
        self,
        decision: CopyDecision,
        wallet: TrackedWallet,
    ) -> CopyTradeResult:
        """
        Execute a copy trade based on an approved decision.

        Args:
            decision: The approved CopyDecision
            wallet: TrackedWallet configuration

        Returns:
            CopyTradeResult with execution details
        """
        activity = decision.source_activity

        # Enforce copy delay (0 = immediate copy for max speed)
        if wallet.copy_delay_seconds > 0:
            elapsed = (datetime.utcnow() - activity.timestamp).total_seconds()
            remaining = wallet.copy_delay_seconds - elapsed
            if remaining > 0:
                logger.debug(f"Copy delay: waiting {remaining:.1f}s")
                time.sleep(min(remaining, 30))

        # Check if this tx_hash already exists in DB
        existing = (
            self.db.query(CopiedTrade)
            .filter(CopiedTrade.source_tx_hash == activity.tx_hash)
            .first()
        )
        if existing:
            logger.debug(f"Trade {activity.tx_hash[:16]}... already in DB, skipping")
            return CopyTradeResult(
                success=False,
                error="Trade already recorded",
                source_wallet=wallet.address,
                source_tx_hash=activity.tx_hash,
                market_id=activity.market_id,
            )

        # Record pending trade in DB
        # Note: side/outcome reflect OUR trade (may differ from source if
        # SELL was converted to BUY opposite outcome)
        copied_trade = CopiedTrade(
            source_wallet=wallet.address,
            source_tx_hash=activity.tx_hash,
            source_trade_size=activity.size,
            source_price=activity.price,
            market_id=activity.market_id,
            condition_id=activity.condition_id,
            token_id=activity.token_id,  # May be updated in _execute_live_trade
            market_question=activity.market_question,
            market_slug=activity.market_slug,
            side=decision.copy_side,
            outcome=decision.copy_outcome,
            size=decision.copy_size,
            status="pending",
            source_time=activity.timestamp,
            is_paper_trade=self.is_paper_trading,
        )
        self.db.add(copied_trade)
        try:
            self.db.commit()
        except Exception as e:
            logger.warning(f"Error recording pending trade: {e}")
            self.db.rollback()
            return CopyTradeResult(
                success=False,
                error=f"DB error: {e}",
                source_wallet=wallet.address,
                source_tx_hash=activity.tx_hash,
                market_id=activity.market_id,
            )

        try:
            # Execute the trade
            if self.is_paper_trading:
                result = self._execute_paper_trade(decision, copied_trade)
            else:
                result = self._execute_live_trade(decision, copied_trade)

            # Update DB record
            if result.success:
                copied_trade.status = "executed"
                copied_trade.entry_price = result.executed_price
                copied_trade.slippage = result.slippage
                copied_trade.executed_at = datetime.utcnow()
                copied_trade.order_id = result.order_id
                if result.executed_size:
                    copied_trade.size = result.executed_size

                # Update wallet stats
                wallet.total_trades_copied += 1
                wallet.last_activity = datetime.utcnow()
            else:
                copied_trade.status = "failed"
                copied_trade.error_message = result.error

            self.db.commit()
            return result

        except Exception as e:
            logger.error(f"Error executing copy trade: {e}", exc_info=True)
            copied_trade.status = "failed"
            copied_trade.error_message = str(e)
            self.db.commit()
            return CopyTradeResult(
                success=False,
                error=str(e),
                source_wallet=wallet.address,
                source_tx_hash=activity.tx_hash,
                market_id=activity.market_id,
            )

    def _execute_paper_trade(
        self,
        decision: CopyDecision,
        record: CopiedTrade,
    ) -> CopyTradeResult:
        """Execute a paper (simulated) copy trade."""
        activity = decision.source_activity

        # Use the decision's target_price (already converted for opposite outcomes)
        base_price = decision.target_price or activity.price

        # Simulate slippage (paper trades get slightly worse price)
        import random
        slippage_pct = random.uniform(0, self.max_slippage)
        if decision.copy_side == "buy":
            executed_price = min(base_price * (1 + slippage_pct), 0.99)
        else:
            executed_price = max(base_price * (1 - slippage_pct), 0.01)

        slippage = abs(executed_price - base_price)

        # Show what we're actually doing vs what the source did
        is_converted = (decision.copy_outcome != activity.outcome)
        action_desc = (
            f"SELL→BUY {decision.copy_outcome.upper()}"
            if is_converted
            else f"{decision.copy_side.upper()} {decision.copy_outcome.upper()}"
        )

        logger.info(
            f"[PAPER] Copied {action_desc} "
            f"${decision.copy_size:.2f} @ {executed_price:.4f} "
            f"(source: {activity.side.upper()} {activity.outcome.upper()} "
            f"${activity.size:.2f} @ {activity.price:.4f}, "
            f"slippage: {slippage:.4f}) "
            f"Market: {activity.market_question or activity.market_id[:20]}"
        )

        return CopyTradeResult(
            success=True,
            order_id=f"paper_{record.id}_{int(time.time())}",
            executed_price=round(executed_price, 6),
            executed_size=decision.copy_size,
            slippage=round(slippage, 6),
            source_wallet=activity.wallet_address,
            source_tx_hash=activity.tx_hash,
            market_id=activity.market_id,
        )

    def _execute_live_trade(
        self,
        decision: CopyDecision,
        record: CopiedTrade,
    ) -> CopyTradeResult:
        """Execute a real copy trade via the Polymarket CLOB API."""
        activity = decision.source_activity

        # We need the token_id to place orders
        token_id = activity.token_id
        if not token_id:
            return CopyTradeResult(
                success=False,
                error="No token_id available for this market/outcome",
                source_wallet=activity.wallet_address,
                source_tx_hash=activity.tx_hash,
                market_id=activity.market_id,
            )

        # If the copy outcome differs from source (SELL converted to BUY opposite),
        # we need to resolve the opposite token_id
        is_opposite_conversion = (
            decision.copy_outcome != activity.outcome
            and decision.copy_side == "buy"
            and activity.side == "sell"
        )

        if is_opposite_conversion:
            # Resolve opposite token_id via condition_id
            condition_id = activity.condition_id or activity.market_id
            if hasattr(self.trading_client, "get_opposite_token_id"):
                opposite_token = self.trading_client.get_opposite_token_id(
                    condition_id, activity.outcome
                )
                if opposite_token:
                    logger.info(
                        f"Using opposite token: {activity.outcome.upper()} "
                        f"{token_id[:16]}... → {decision.copy_outcome.upper()} "
                        f"{opposite_token[:16]}..."
                    )
                    token_id = opposite_token
                else:
                    return CopyTradeResult(
                        success=False,
                        error=(
                            f"Could not resolve opposite token_id for "
                            f"{decision.copy_outcome.upper()} "
                            f"(condition={condition_id[:20]}...)"
                        ),
                        source_wallet=activity.wallet_address,
                        source_tx_hash=activity.tx_hash,
                        market_id=activity.market_id,
                    )
            else:
                return CopyTradeResult(
                    success=False,
                    error="Trading client does not support get_opposite_token_id",
                    source_wallet=activity.wallet_address,
                    source_tx_hash=activity.tx_hash,
                    market_id=activity.market_id,
                )

        # Fetch market info (tick_size, neg_risk) for proper order signing
        market_info = {"tick_size": "0.01", "neg_risk": False, "tokens": []}
        if hasattr(self.trading_client, "get_market_info"):
            market_info = self.trading_client.get_market_info(token_id)

        # The price we'll use for our order
        order_price = decision.target_price

        # Check current price to avoid excessive slippage
        current_price = self.trading_client.get_price(token_id)
        logger.info(
            f"Price check: order_price={order_price:.4f}, current={current_price}, "
            f"side={decision.copy_side.upper()} {decision.copy_outcome.upper()} "
            f"token={token_id[:20]}... "
            f"(tick={market_info['tick_size']}, neg_risk={market_info['neg_risk']})"
            f"{' [opposite conversion]' if is_opposite_conversion else ''}"
        )
        if current_price is not None:
            # If current_price is exactly 0.5, the orderbook may be empty/broken
            if abs(current_price - 0.5) < 0.001:
                logger.warning(
                    f"Suspicious price 0.5000 (likely empty orderbook), "
                    f"skipping slippage check, using order price {order_price:.4f}"
                )
                current_price = None
            else:
                price_diff = abs(current_price - order_price)
                if price_diff > self.max_slippage:
                    return CopyTradeResult(
                        success=False,
                        error=(
                            f"Price moved too much: order={order_price:.4f}, "
                            f"current={current_price:.4f}, diff={price_diff:.4f}"
                        ),
                        source_wallet=activity.wallet_address,
                        source_tx_hash=activity.tx_hash,
                        market_id=activity.market_id,
                    )

        # Place the order as a limit order
        # Limit orders (GTC) stay in the orderbook until filled,
        # unlike market orders (FOK) which fail if no immediate match
        try:
            order_id = self.trading_client.place_order(
                token_id=token_id,
                side=decision.copy_side,
                size=decision.copy_size,
                price=order_price,
                order_type="limit",
                tick_size=market_info["tick_size"],
                neg_risk=market_info["neg_risk"],
            )

            if order_id:
                executed_price = current_price or order_price
                slippage = abs(executed_price - order_price)

                action_desc = (
                    f"SELL→BUY {decision.copy_outcome.upper()}"
                    if is_opposite_conversion
                    else f"{decision.copy_side.upper()} {decision.copy_outcome.upper()}"
                )
                logger.info(
                    f"[LIVE] Copied {action_desc} "
                    f"${decision.copy_size:.2f} @ ~{executed_price:.4f} "
                    f"(order_id={order_id})"
                )

                # Update the record with the actual token_id used
                record.token_id = token_id

                return CopyTradeResult(
                    success=True,
                    order_id=order_id,
                    executed_price=round(executed_price, 6),
                    executed_size=decision.copy_size,
                    slippage=round(slippage, 6),
                    source_wallet=activity.wallet_address,
                    source_tx_hash=activity.tx_hash,
                    market_id=activity.market_id,
                )
            else:
                return CopyTradeResult(
                    success=False,
                    error="Order placement returned no order_id",
                    source_wallet=activity.wallet_address,
                    source_tx_hash=activity.tx_hash,
                    market_id=activity.market_id,
                )

        except Exception as e:
            return CopyTradeResult(
                success=False,
                error=f"Order execution error: {e}",
                source_wallet=activity.wallet_address,
                source_tx_hash=activity.tx_hash,
                market_id=activity.market_id,
            )

    # ------------------------------------------------------------------
    # Skipped trade recording
    # ------------------------------------------------------------------

    def record_skipped_trade(
        self,
        decision: CopyDecision,
    ):
        """Record a trade that was evaluated but not copied."""
        activity = decision.source_activity

        # Check if this tx_hash already exists in DB to avoid UNIQUE constraint error
        existing = (
            self.db.query(CopiedTrade)
            .filter(CopiedTrade.source_tx_hash == activity.tx_hash)
            .first()
        )
        if existing:
            logger.debug(f"Trade {activity.tx_hash[:16]}... already recorded, skipping DB insert")
            return

        record = CopiedTrade(
            source_wallet=decision.source_wallet,
            source_tx_hash=activity.tx_hash,
            source_trade_size=activity.size,
            source_price=activity.price,
            market_id=activity.market_id,
            condition_id=activity.condition_id,
            token_id=activity.token_id,
            market_question=activity.market_question,
            market_slug=activity.market_slug,
            side=activity.side,
            outcome=activity.outcome,
            size=0,
            status="skipped",
            skip_reason=decision.reason,
            source_time=activity.timestamp,
            is_paper_trade=self.is_paper_trading,
        )
        self.db.add(record)
        try:
            self.db.commit()
        except Exception as e:
            logger.warning(f"Error recording skipped trade: {e}")
            self.db.rollback()

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def get_open_positions(self) -> list:
        """Get all open copied positions."""
        return (
            self.db.query(CopiedTrade)
            .filter(CopiedTrade.status == "executed")
            .order_by(CopiedTrade.executed_at.desc())
            .all()
        )

    def close_position(
        self,
        trade_id: int,
        exit_price: float,
        reason: str = "manual",
    ) -> float:
        """
        Close a copied trade position.

        Returns realized P&L.
        """
        trade = self.db.query(CopiedTrade).filter(CopiedTrade.id == trade_id).first()
        if not trade or trade.status != "executed":
            logger.warning(f"CopiedTrade {trade_id} not found or not open")
            return 0.0

        # Calculate P&L
        if trade.outcome.lower() == "yes":
            if trade.side == "buy":
                shares = trade.size / trade.entry_price
                pnl = shares * exit_price - trade.size
            else:
                shares = trade.size / trade.entry_price
                pnl = trade.size - shares * exit_price
        else:
            entry_cost = 1 - trade.entry_price
            if trade.side == "buy":
                shares = trade.size / entry_cost
                pnl = shares * (1 - exit_price) - trade.size
            else:
                shares = trade.size / entry_cost
                pnl = trade.size - shares * (1 - exit_price)

        trade.exit_price = exit_price
        trade.realized_pnl = round(pnl, 4)
        trade.status = "closed"
        trade.closed_at = datetime.utcnow()

        # Update wallet stats
        wallet = (
            self.db.query(TrackedWallet)
            .filter(TrackedWallet.address == trade.source_wallet)
            .first()
        )
        if wallet:
            wallet.total_pnl = (wallet.total_pnl or 0) + pnl
            # Recalculate win rate
            closed_from_wallet = (
                self.db.query(CopiedTrade)
                .filter(
                    CopiedTrade.source_wallet == wallet.address,
                    CopiedTrade.status == "closed",
                )
                .all()
            )
            wins = sum(1 for t in closed_from_wallet if (t.realized_pnl or 0) > 0)
            total = len(closed_from_wallet)
            wallet.win_rate = wins / total if total > 0 else 0

        self.db.commit()
        logger.info(f"Closed CopiedTrade {trade_id}: P&L=${pnl:.2f}, reason={reason}")
        return pnl
