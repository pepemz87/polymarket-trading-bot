"""
Entry point for the Polymarket Copy Trading Bot.

Usage:
    # Run in continuous mode (default)
    python run_copy_trading.py

    # Run a single scan cycle
    python run_copy_trading.py --once

    # Add wallets interactively
    python run_copy_trading.py --add-wallet 0x1234... --label "Whale_Alpha"

    # Discover top traders
    python run_copy_trading.py --discover

    # Show status
    python run_copy_trading.py --status
"""
import argparse
import sys
from loguru import logger

from src.copy_trading.copy_trading_bot import CopyTradingBot


def main():
    parser = argparse.ArgumentParser(
        description="Polymarket Copy Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_copy_trading.py                          # Run continuous
  python run_copy_trading.py --once                   # Single scan
  python run_copy_trading.py --add-wallet 0xABC...    # Add wallet
  python run_copy_trading.py --discover               # Find top traders
  python run_copy_trading.py --status                 # Show status
        """,
    )

    parser.add_argument(
        "--once", action="store_true",
        help="Run a single scan cycle and exit",
    )
    parser.add_argument(
        "--add-wallet", type=str, metavar="ADDRESS",
        help="Add a wallet address to track",
    )
    parser.add_argument(
        "--remove-wallet", type=str, metavar="ADDRESS",
        help="Stop tracking a wallet address",
    )
    parser.add_argument(
        "--label", type=str, default=None,
        help="Label for the wallet (use with --add-wallet)",
    )
    parser.add_argument(
        "--sizing-mode", type=str, default="proportional",
        choices=["fixed", "proportional", "percentage"],
        help="Sizing mode for copied trades (default: proportional)",
    )
    parser.add_argument(
        "--fixed-size", type=float, default=10.0,
        help="Fixed USDC amount per trade (for fixed sizing mode)",
    )
    parser.add_argument(
        "--proportional-factor", type=float, default=1.0,
        help="Multiplier for proportional sizing (e.g. 0.5 = half their size)",
    )
    parser.add_argument(
        "--discover", action="store_true",
        help="Discover top profitable traders on Polymarket",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show current bot status and exit",
    )
    parser.add_argument(
        "--list-wallets", action="store_true",
        help="List all tracked wallets with stats",
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--env", type=str, default=None,
        help="Path to .env file",
    )

    args = parser.parse_args()

    try:
        bot = CopyTradingBot(config_path=args.config, env_path=args.env)

        # --- Wallet management commands ---
        if args.add_wallet:
            wallet = bot.add_wallet(
                address=args.add_wallet,
                label=args.label,
                sizing_mode=args.sizing_mode,
                fixed_size=args.fixed_size,
                proportional_factor=args.proportional_factor,
            )
            logger.info(
                f"Wallet added: {wallet.address} "
                f"(label={wallet.label}, sizing={wallet.sizing_mode})"
            )
            return

        if args.remove_wallet:
            removed = bot.remove_wallet(args.remove_wallet)
            if removed:
                logger.info(f"Wallet {args.remove_wallet} deactivated")
            else:
                logger.warning(f"Wallet {args.remove_wallet} not found")
            return

        if args.list_wallets:
            stats = bot.list_wallets()
            if not stats:
                logger.info("No wallets tracked yet")
            else:
                logger.info(f"{'Address':<44} {'Label':<15} {'P&L':>10} {'WR':>6} {'Trades':>7}")
                logger.info("-" * 85)
                for s in stats:
                    logger.info(
                        f"{s.address:<44} {(s.label or '-'):<15} "
                        f"${s.total_pnl:>9.2f} {s.win_rate:>5.0%} {s.total_trades_copied:>7}"
                    )
            return

        if args.discover:
            logger.info("Discovering top traders on Polymarket...")
            traders = bot.discover_traders(min_volume=10000, min_markets=5, limit=20)
            if not traders:
                logger.info("No traders found (API may be unavailable)")
            else:
                logger.info(f"{'Rank':>4} {'Address':<44} {'Profit':>12} {'Volume':>12} {'WR':>6}")
                logger.info("-" * 80)
                for t in traders:
                    logger.info(
                        f"{t.rank or '-':>4} {t.address:<44} "
                        f"${t.profit_total:>11.2f} ${t.volume_total:>11.2f} "
                        f"{t.win_rate:>5.0%}"
                    )
            return

        if args.status:
            bot.print_status()
            return

        # --- Run the bot ---
        active = bot.wallet_tracker.get_active_wallets()
        if not active:
            logger.warning(
                "No wallets are being tracked! Add wallets first:\n"
                "  python run_copy_trading.py --add-wallet 0x... --label 'MyTrader'"
            )
            sys.exit(1)

        logger.info(f"Tracking {len(active)} wallet(s)")
        for w in active:
            logger.info(f"  - {w.label or w.address[:12]}... ({w.sizing_mode})")

        if args.once:
            bot.run_once()
        else:
            bot.run_continuous()

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
