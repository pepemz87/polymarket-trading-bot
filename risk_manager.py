"""
Clawbot — Risk Manager
All pre-trade checks and Kelly-based position sizing.
"""
from __future__ import annotations

from loguru import logger

import config


class RiskManager:
    """
    Gate-keeper for every trade the bot wants to place.

    All checks return True == safe to proceed.
    """

    def __init__(self, trade_logger=None):
        """
        Args:
            trade_logger: A TradeLogger instance used to query today's P&L.
                          Can be None; daily-loss check will be skipped.
        """
        self._logger = trade_logger

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_capital(self, available_usdc: float, trade_size: float) -> bool:
        """
        True if there is enough free capital for this trade.

        Args:
            available_usdc: Current liquid USDC (from WalletManager or paper balance).
            trade_size:     Proposed trade size in USDC.
        """
        if trade_size <= 0:
            logger.warning("RiskManager: trade_size must be > 0")
            return False

        if available_usdc < trade_size:
            logger.warning(
                f"RiskManager: insufficient capital — have ${available_usdc:.2f}, "
                f"need ${trade_size:.2f}"
            )
            return False

        return True

    def check_daily_loss(self) -> bool:
        """
        True if today's realised losses are within the daily stop limit.

        Returns False (halt trading) if MAX_DAILY_LOSS_USDC has been hit.
        """
        if self._logger is None:
            return True

        daily_pnl = self._logger.get_daily_pnl()

        if daily_pnl <= -config.MAX_DAILY_LOSS_USDC:
            logger.warning(
                f"RiskManager: daily stop triggered — P&L today = ${daily_pnl:.2f} "
                f"(limit = -${config.MAX_DAILY_LOSS_USDC:.2f})"
            )
            return False

        return True

    def check_max_positions(self, open_positions: list) -> bool:
        """
        True if we have capacity for at least one more position.

        Args:
            open_positions: List of current open position dicts.
        """
        n = len(open_positions)
        if n >= config.MAX_OPEN_POSITIONS:
            logger.warning(
                f"RiskManager: max positions reached ({n}/{config.MAX_OPEN_POSITIONS})"
            )
            return False
        return True

    def check_signal_filters(self, signal: dict) -> bool:
        """
        Apply all signal-level quality filters.

        Returns False if the signal fails any filter.
        """
        city = signal.get("city", "?")

        # Edge in degrees Celsius
        edge = signal.get("edge_degrees", 0)
        if edge < config.MIN_EDGE_DEGREES:
            logger.debug(f"RiskManager [{city}]: edge {edge}°C < {config.MIN_EDGE_DEGREES}°C min")
            return False

        # Market volume
        volume = signal.get("volume_24h", 0)
        if volume < config.MIN_VOLUME_24H:
            logger.debug(f"RiskManager [{city}]: volume ${volume} < ${config.MIN_VOLUME_24H} min")
            return False

        # YES price range
        yes_price = signal.get("forecast_bucket_yes", 0)
        if yes_price < config.MIN_YES_PRICE:
            logger.debug(f"RiskManager [{city}]: YES price {yes_price} < {config.MIN_YES_PRICE} min")
            return False
        if yes_price > config.MAX_YES_PRICE:
            logger.debug(f"RiskManager [{city}]: YES price {yes_price} > {config.MAX_YES_PRICE} max")
            return False

        # Ensemble agreement
        if config.ONLY_STRONG_SIGNALS and not signal.get("ensemble_agrees", False):
            logger.debug(f"RiskManager [{city}]: ensemble does not agree — skipping")
            return False

        return True

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def calculate_position_size(
        self,
        signal: dict,
        available_usdc: float,
    ) -> float:
        """
        Kelly Criterion (fractional) for prediction markets.

        For a binary market:
            p  = our estimated probability of YES resolving
            q  = 1 - p
            b  = net payout odds = (1 / market_price) - 1
            f* = (b*p - q) / b          ← full Kelly
            f  = f* * KELLY_FRACTION    ← fractional Kelly

        We derive `p` from the ensemble probability implied by the forecast
        bucket vs. the overall market. As a conservative proxy we use:
            p = 1 - market_yes_price    (we think yes is more likely than priced)

        Args:
            signal:          Weather signal dict.
            available_usdc:  Free capital available to deploy.

        Returns:
            Trade size in USDC, capped at MAX_TRADE_SIZE_USDC.
        """
        market_price = signal.get("forecast_bucket_yes", 0.10)
        market_price = max(0.01, min(0.99, market_price))  # guard bounds

        # Conservative win probability: midpoint between our forecast certainty
        # (treated as 1.0 because ensemble agrees) and the market price.
        # Using 0.70 as a base "confident but not certain" estimate.
        p = 0.70
        q = 1.0 - p
        b = (1.0 / market_price) - 1.0   # net payout multiplier

        if b <= 0:
            logger.debug("RiskManager: degenerate odds, defaulting to min size")
            return min(1.0, config.MAX_TRADE_SIZE_USDC)

        full_kelly = (b * p - q) / b

        if full_kelly <= 0:
            logger.debug(f"RiskManager: no Kelly edge (f*={full_kelly:.4f}) — skip")
            return 0.0

        kelly_fraction = full_kelly * config.KELLY_FRACTION
        bet = available_usdc * kelly_fraction

        # Cap to hard limits
        bet = min(bet, config.MAX_TRADE_SIZE_USDC)
        bet = min(bet, available_usdc)
        bet = max(bet, 1.0)   # never bet less than $1

        logger.debug(
            f"RiskManager: Kelly size — p={p:.2f}, b={b:.2f}, "
            f"full_kelly={full_kelly:.4f}, fraction={kelly_fraction:.4f}, "
            f"bet=${bet:.2f}"
        )
        return round(bet, 2)

    # ------------------------------------------------------------------
    # Composite gate
    # ------------------------------------------------------------------

    def approve_trade(
        self,
        signal: dict,
        open_positions: list,
        available_usdc: float,
        trade_size: float,
    ) -> bool:
        """
        Run all checks in one call.

        Returns True only if every check passes.
        """
        checks = [
            ("daily_loss",     self.check_daily_loss()),
            ("max_positions",  self.check_max_positions(open_positions)),
            ("signal_filters", self.check_signal_filters(signal)),
            ("capital",        self.check_capital(available_usdc, trade_size)),
        ]

        for name, result in checks:
            if not result:
                logger.info(f"RiskManager: trade REJECTED by [{name}] check")
                return False

        logger.info(f"RiskManager: trade APPROVED — ${trade_size:.2f} on {signal.get('city')}")
        return True
