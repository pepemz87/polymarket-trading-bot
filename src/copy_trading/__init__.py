"""
Copy Trading module for Polymarket.

Monitors target wallets on Polymarket and automatically replicates
their trades with configurable sizing, delays, and risk filters.
"""

from .wallet_tracker import WalletTracker
from .trade_copier import TradeCopier
from .copy_trading_bot import CopyTradingBot

__all__ = [
    "WalletTracker",
    "TradeCopier",
    "CopyTradingBot",
]
