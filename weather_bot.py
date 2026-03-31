"""
Clawbot — Weather Market Trading Bot
=====================================
Reads weather_signals.json (produced by weather_scanner.py) and executes
trades on Polymarket based on detected temperature mispricing.

Usage
-----
  python weather_bot.py            # run the trading loop
  python weather_bot.py --status   # print status snapshot and exit
  python weather_bot.py --paper    # force paper-trading mode for this session
  python weather_bot.py --live     # force live-trading mode (needs creds)
  python weather_bot.py --setup-creds   # derive CLOB API keys from private key

⚠️  Always test in paper mode first.  Set PAPER_TRADING=True in config.py
    or pass --paper flag.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from loguru import logger

import config
from wallet_manager import WalletManager
from risk_manager import RiskManager
from trade_logger import TradeLogger

# Optional CLOB SDK
try:
    from py_clob_client.clob_types import OrderArgs, OrderType, ApiCreds
    from py_clob_client.constants import POLYGON
    CLOB_AVAILABLE = True
except ImportError:
    CLOB_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────────────
# Helper: pretty console output
# ──────────────────────────────────────────────────────────────────────────────

try:
    from termcolor import colored
    def _c(text, color): return colored(str(text), color)
except ImportError:
    def _c(text, color): return str(text)


# ──────────────────────────────────────────────────────────────────────────────
# WeatherBot
# ──────────────────────────────────────────────────────────────────────────────

class WeatherBot:
    """
    Main trading loop.

    Lifecycle
    ---------
    1. Load weather_signals.json every SCAN_SIGNALS_EVERY seconds.
    2. Filter signals through RiskManager.
    3. Execute (or simulate) trades via the CLOB.
    4. Persist open positions to open_positions.json.
    5. Poll open positions for resolution.
    """

    def __init__(self, paper_override: Optional[bool] = None):
        """
        Args:
            paper_override: If not None, overrides config.PAPER_TRADING for
                            this session only.
        """
        self.paper = config.PAPER_TRADING if paper_override is None else paper_override
        mode_label = _c("PAPER", "yellow") if self.paper else _c("LIVE", "red")
        logger.info(f"WeatherBot starting in {mode_label} mode")

        self.trade_logger  = TradeLogger()
        self.risk_manager  = RiskManager(trade_logger=self.trade_logger)
        self.wallet        = WalletManager()

        # Paper trading virtual balance
        self._paper_balance = config.TOTAL_CAPITAL_USDC

        # In-memory open positions (also persisted to disk)
        self._open_positions: list[dict] = self._load_positions()

        # Cycle counter for status line
        self._cycle = 0

    # ──────────────────────────────────────────────────────────────────────────
    # Main loop
    # ──────────────────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the main trading loop.  Ctrl-C to exit cleanly."""
        logger.info(
            f"Bot live — scanning {config.SIGNALS_FILE} "
            f"every {config.SCAN_SIGNALS_EVERY}s"
        )
        while True:
            try:
                self._cycle += 1
                logger.info(f"── Cycle {self._cycle} ──────────────────────────────")

                self.check_and_trade()
                self.check_open_positions()

                logger.info(
                    f"Cycle {self._cycle} done.  "
                    f"Next scan in {config.SCAN_SIGNALS_EVERY}s.  "
                    f"Open positions: {len(self._open_positions)}"
                )
                time.sleep(config.SCAN_SIGNALS_EVERY)

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt — shutting down")
                self._save_positions()
                break
            except Exception as exc:
                logger.error(f"Unexpected error in main loop: {exc}", exc_info=True)
                time.sleep(30)   # brief back-off before retry

    # ──────────────────────────────────────────────────────────────────────────
    # Step 1: Read signals and decide
    # ──────────────────────────────────────────────────────────────────────────

    def check_and_trade(self) -> None:
        """Load signals and attempt a trade for each qualifying signal."""
        signals = self.load_signals()
        if not signals:
            logger.info("No fresh signals found")
            return

        logger.info(f"Evaluating {len(signals)} signal(s)")
        for signal in signals:
            city = signal.get("city", "?")
            if self.should_trade(signal):
                logger.info(f"Signal ACCEPTED — {city}")
                self.execute_trade(signal)
            else:
                logger.debug(f"Signal SKIPPED — {city}")

    # ──────────────────────────────────────────────────────────────────────────
    # Step 2: Should we trade this signal?
    # ──────────────────────────────────────────────────────────────────────────

    def should_trade(self, signal: dict) -> bool:
        """
        Run all pre-trade checks.

        Returns True only when every gate passes.
        """
        city = signal.get("city", "?")

        # 1. Stale signal?
        if not self._is_fresh(signal):
            logger.debug(f"[{city}] signal too old — skipping")
            return False

        # 2. Already have a position in this market?
        slug = signal.get("slug", "")
        if any(p["slug"] == slug for p in self._open_positions):
            logger.debug(f"[{city}] position already open — skipping")
            return False

        # 3. YES price has moved adversely since signal was generated?
        current_yes = self._get_current_price(signal.get("forecast_bucket_token", ""))
        if current_yes is not None:
            original_yes = signal.get("forecast_bucket_yes", 0)
            if current_yes > original_yes * 1.5:
                logger.debug(
                    f"[{city}] YES price moved too much "
                    f"({original_yes:.3f} → {current_yes:.3f}) — skipping"
                )
                return False

        # 4. Risk manager composite check
        available = self._available_balance()
        trade_size = self.risk_manager.calculate_position_size(signal, available)
        if trade_size <= 0:
            logger.debug(f"[{city}] Kelly returned 0 size — skipping")
            return False

        return self.risk_manager.approve_trade(
            signal=signal,
            open_positions=self._open_positions,
            available_usdc=available,
            trade_size=trade_size,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Step 3: Execute (or simulate) the trade
    # ──────────────────────────────────────────────────────────────────────────

    def execute_trade(self, signal: dict) -> None:
        """
        Place (or simulate) a BUY order on the forecast bucket YES token.
        """
        city   = signal.get("city", "?")
        slug   = signal.get("slug", "")
        token  = signal.get("forecast_bucket_token", "")

        # Calculate final position size
        available  = self._available_balance()
        trade_size = self.risk_manager.calculate_position_size(signal, available)
        yes_price  = signal.get("forecast_bucket_yes", 0.10)

        # Determine limit price
        if config.USE_LIMIT_ORDERS:
            order_book_price = self._get_current_price(token)
            if order_book_price:
                limit_price = min(order_book_price + config.LIMIT_ORDER_SLIPPAGE, config.MAX_YES_PRICE)
            else:
                limit_price = yes_price + config.LIMIT_ORDER_SLIPPAGE
        else:
            limit_price = yes_price

        limit_price = round(limit_price, 4)

        logger.info(
            f"[{city}] Placing {'PAPER ' if self.paper else ''}BUY — "
            f"size=${trade_size:.2f} | limit={limit_price:.4f} | token={token[:10]}..."
        )

        order_response: Optional[dict] = None

        if self.paper:
            # ── PAPER TRADE ──────────────────────────────────────────────
            order_response = {
                "orderID": f"PAPER-{int(time.time()*1000)}",
                "status":  "PAPER",
                "price":   limit_price,
                "size":    trade_size,
            }
            self._paper_balance -= trade_size
            logger.info(
                f"[{city}] PAPER trade simulated — "
                f"virtual balance now ${self._paper_balance:.2f}"
            )

        else:
            # ── LIVE TRADE ───────────────────────────────────────────────
            client = self.wallet.get_client()
            if client is None:
                logger.error(f"[{city}] CLOB client not available — aborting live trade")
                return

            try:
                order_args = OrderArgs(
                    token_id=token,
                    price=limit_price,
                    size=trade_size,
                    side="BUY",
                )
                signed = client.create_order(order_args)
                order_type = OrderType.GTC if config.USE_LIMIT_ORDERS else OrderType.FOK
                resp = client.post_order(signed, order_type)
                order_response = resp if isinstance(resp, dict) else {"orderID": str(resp)}
                logger.info(f"[{city}] LIVE order submitted: {order_response}")
            except Exception as exc:
                logger.error(f"[{city}] Order failed: {exc}")
                return

        # ── Persist trade ──────────────────────────────────────────────
        kelly_fraction = self.risk_manager.calculate_position_size(signal, available) / available if available > 0 else 0
        self.trade_logger.log_trade(
            signal=signal,
            order_response=order_response,
            size_usdc=trade_size,
            kelly_fraction=kelly_fraction,
            paper=self.paper,
        )

        # Track as open position
        position = {
            "city":          city,
            "slug":          slug,
            "token":         token,
            "order_id":      order_response.get("orderID", ""),
            "size_usdc":     trade_size,
            "limit_price":   limit_price,
            "paper":         self.paper,
            "opened_at":     _now_iso(),
            "timeout_at":    _timeout_iso(),
        }
        self._open_positions.append(position)
        self._save_positions()

    # ──────────────────────────────────────────────────────────────────────────
    # Step 4: Poll open positions
    # ──────────────────────────────────────────────────────────────────────────

    def check_open_positions(self) -> None:
        """
        For each open position:
        - Check if the limit order has timed out (cancel it).
        - Check if the market has resolved (log P&L).
        """
        if not self._open_positions:
            return

        still_open: list[dict] = []
        client = self.wallet.get_client()
        now = datetime.now(timezone.utc)

        for pos in self._open_positions:
            city     = pos.get("city", "?")
            order_id = pos.get("order_id", "")
            paper    = pos.get("paper", True)

            # ── Check timeout ─────────────────────────────────────────
            timeout_at_str = pos.get("timeout_at")
            if timeout_at_str:
                try:
                    timeout_at = datetime.fromisoformat(timeout_at_str)
                    if now > timeout_at:
                        logger.info(f"[{city}] Limit order timed out — cancelling {order_id}")
                        if not paper and client and order_id:
                            try:
                                client.cancel_order(order_id)
                            except Exception as exc:
                                logger.warning(f"[{city}] Cancel failed: {exc}")
                        # No P&L — just remove from open
                        continue
                except ValueError:
                    pass

            # ── Check resolution (live only) ──────────────────────────
            if not paper and client and order_id:
                try:
                    trades = client.get_trades(params={"id": order_id})
                    for t in (trades or []):
                        if t.get("status") in ("CONFIRMED", "FILLED"):
                            pnl = float(t.get("pnl", 0))
                            outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "PUSH"
                            self.trade_logger.log_resolution(order_id, outcome, pnl)
                            logger.info(f"[{city}] Position resolved — {outcome} ${pnl:.2f}")
                            pos = None  # mark for removal
                            break
                except Exception as exc:
                    logger.debug(f"[{city}] Resolution check failed: {exc}")

            if pos is not None:
                still_open.append(pos)

        self._open_positions = still_open
        self._save_positions()

    # ──────────────────────────────────────────────────────────────────────────
    # Signal loading
    # ──────────────────────────────────────────────────────────────────────────

    def load_signals(self) -> list[dict]:
        """
        Read weather_signals.json and return only fresh signals.
        """
        if not os.path.exists(config.SIGNALS_FILE):
            logger.warning(f"Signals file not found: {config.SIGNALS_FILE}")
            return []

        try:
            with open(config.SIGNALS_FILE) as f:
                signals = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Cannot read signals file: {exc}")
            return []

        fresh = [s for s in signals if self._is_fresh(s)]
        logger.debug(f"Loaded {len(signals)} signals, {len(fresh)} fresh")
        return fresh

    # ──────────────────────────────────────────────────────────────────────────
    # Status command
    # ──────────────────────────────────────────────────────────────────────────

    def print_status(self) -> None:
        """Print a human-readable status snapshot."""
        print("\n" + _c("═" * 55, "cyan"))
        print(_c("  Clawbot Weather Bot — Status", "cyan"))
        print(_c("═" * 55, "cyan"))

        # Balance
        if self.paper:
            balance = self._paper_balance
            label   = "Virtual (paper)"
        else:
            balance = self.wallet.get_usdc_balance()
            label   = "Live USDC"
        print(f"  {label} balance : {_c(f'${balance:.2f}', 'green')}")

        # Mode
        mode = _c("PAPER TRADING", "yellow") if self.paper else _c("LIVE TRADING", "red")
        print(f"  Mode             : {mode}")

        # Open positions
        print(f"\n  Open positions   : {len(self._open_positions)}")
        for pos in self._open_positions:
            print(
                f"    • {pos['city']:<12} | "
                f"${pos['size_usdc']:.2f} | "
                f"limit={pos['limit_price']:.3f} | "
                f"opened={pos['opened_at']}"
            )

        # Today's P&L
        today_pnl = self.trade_logger.get_daily_pnl()
        pnl_color = "green" if today_pnl >= 0 else "red"
        print(f"\n  Today's P&L      : {_c(f'${today_pnl:.2f}', pnl_color)}")

        # Upcoming signals
        signals = self.load_signals()
        print(f"\n  Live signals     : {len(signals)}")
        for s in signals[:5]:
            print(
                f"    → {s['city_display']:<14} "
                f"edge={s['edge_degrees']}°C  "
                f"YES={s['forecast_bucket_yes']:.2f}  "
                f"strength={s['signal_strength']}"
            )
        if len(signals) > 5:
            print(f"    ... and {len(signals) - 5} more")

        # Next cycle
        print(f"\n  Next scan in     : {config.SCAN_SIGNALS_EVERY}s")
        print(_c("═" * 55, "cyan") + "\n")

        # Full stats
        self.trade_logger.print_stats()

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _is_fresh(self, signal: dict) -> bool:
        """True if the signal timestamp is within MAX_SIGNAL_AGE_HOURS."""
        ts_str = signal.get("timestamp")
        if not ts_str:
            return False
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - ts
            return age <= timedelta(hours=config.MAX_SIGNAL_AGE_HOURS)
        except ValueError:
            return False

    def _available_balance(self) -> float:
        """Return the free capital we can deploy right now."""
        if self.paper:
            return self._paper_balance
        return self.wallet.get_usdc_balance()

    def _get_current_price(self, token_id: str) -> Optional[float]:
        """Fetch the best ask price from the CLOB order book."""
        if not token_id:
            return None

        client = self.wallet.get_client()
        if client is None:
            return None

        try:
            book = client.get_order_book(token_id)
            asks = getattr(book, "asks", None) or book.get("asks", [])
            if asks:
                return float(asks[0].price if hasattr(asks[0], "price") else asks[0]["price"])
        except Exception as exc:
            logger.debug(f"Order book fetch failed for {token_id[:10]}: {exc}")
        return None

    def _load_positions(self) -> list[dict]:
        if not os.path.exists(config.POSITIONS_FILE):
            return []
        try:
            with open(config.POSITIONS_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def _save_positions(self) -> None:
        with open(config.POSITIONS_FILE, "w") as f:
            json.dump(self._open_positions, f, indent=2)


# ──────────────────────────────────────────────────────────────────────────────
# Time helpers (module-level so they can be called before bot is instantiated)
# ──────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _timeout_iso() -> str:
    dt = datetime.now(timezone.utc) + timedelta(seconds=config.LIMIT_ORDER_TIMEOUT)
    return dt.isoformat(timespec="seconds")


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clawbot — Polymarket Weather Trading Bot"
    )
    parser.add_argument("--status",      action="store_true", help="Print status and exit")
    parser.add_argument("--paper",       action="store_true", help="Force paper-trading mode")
    parser.add_argument("--live",        action="store_true", help="Force live-trading mode")
    parser.add_argument("--setup-creds", action="store_true", help="Derive and print CLOB API creds")
    args = parser.parse_args()

    # Resolve paper/live override
    paper_override = None
    if args.paper:
        paper_override = True
    elif args.live:
        paper_override = False

    bot = WeatherBot(paper_override=paper_override)

    if args.setup_creds:
        bot.wallet.create_or_derive_api_creds()
        return

    if args.status:
        bot.print_status()
        return

    bot.run()


if __name__ == "__main__":
    main()
