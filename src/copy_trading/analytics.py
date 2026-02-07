"""
Analytics and performance tracking for copy trading.
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from loguru import logger

from .models import TrackedWallet, CopiedTrade, WalletPerformance
from .schemas import TrackedWalletStats, CopyTradingStatus


class CopyTradingAnalytics:
    """
    Tracks and reports performance metrics for copy trading.

    Provides:
    - Per-wallet P&L and win rates
    - Overall portfolio performance
    - Slippage analysis
    - Trade frequency and volume metrics
    - Daily performance snapshots
    """

    def __init__(self, db_session: Session):
        self.db = db_session

    # ------------------------------------------------------------------
    # Wallet-level stats
    # ------------------------------------------------------------------

    def get_wallet_stats(self, address: str) -> Optional[TrackedWalletStats]:
        """Get comprehensive statistics for a tracked wallet."""
        wallet = (
            self.db.query(TrackedWallet)
            .filter(TrackedWallet.address == address.lower())
            .first()
        )
        if not wallet:
            return None

        # Query copied trades for this wallet
        all_trades = (
            self.db.query(CopiedTrade)
            .filter(CopiedTrade.source_wallet == address.lower())
            .all()
        )

        total_detected = len(all_trades)
        executed = [t for t in all_trades if t.status in ("executed", "closed")]
        skipped = [t for t in all_trades if t.status == "skipped"]
        closed = [t for t in all_trades if t.status == "closed"]

        total_pnl = sum(t.realized_pnl or 0 for t in closed)
        wins = sum(1 for t in closed if (t.realized_pnl or 0) > 0)
        win_rate = wins / len(closed) if closed else 0

        volumes = [t.size for t in executed if t.size]
        avg_size = sum(volumes) / len(volumes) if volumes else 0
        total_volume = sum(volumes)

        # 24h and 7d stats
        now = datetime.utcnow()
        trades_24h = [
            t for t in all_trades
            if t.detected_at and (now - t.detected_at).total_seconds() < 86400
        ]
        closed_24h = [t for t in trades_24h if t.status == "closed"]
        pnl_24h = sum(t.realized_pnl or 0 for t in closed_24h)

        trades_7d_closed = [
            t for t in closed
            if t.closed_at and (now - t.closed_at).total_seconds() < 7 * 86400
        ]
        pnl_7d = sum(t.realized_pnl or 0 for t in trades_7d_closed)

        return TrackedWalletStats(
            address=wallet.address,
            label=wallet.label,
            is_active=wallet.is_active,
            total_trades_detected=total_detected,
            total_trades_copied=len(executed),
            total_trades_skipped=len(skipped),
            total_pnl=round(total_pnl, 2),
            win_rate=round(win_rate, 4),
            avg_trade_size=round(avg_size, 2),
            total_volume=round(total_volume, 2),
            last_activity=wallet.last_activity,
            tracking_since=wallet.added_at,
            pnl_24h=round(pnl_24h, 2),
            pnl_7d=round(pnl_7d, 2),
            trades_24h=len(trades_24h),
        )

    def get_all_wallet_stats(self) -> List[TrackedWalletStats]:
        """Get stats for all tracked wallets."""
        wallets = self.db.query(TrackedWallet).all()
        stats = []
        for w in wallets:
            s = self.get_wallet_stats(w.address)
            if s:
                stats.append(s)
        stats.sort(key=lambda x: x.total_pnl, reverse=True)
        return stats

    # ------------------------------------------------------------------
    # Overall system status
    # ------------------------------------------------------------------

    def get_system_status(
        self,
        is_running: bool = False,
        mode: str = "paper",
        bankroll: float = 0,
        available_capital: float = 0,
        start_time: Optional[datetime] = None,
        last_scan: Optional[datetime] = None,
    ) -> CopyTradingStatus:
        """Get comprehensive system status."""
        wallets = self.db.query(TrackedWallet).all()
        active_wallets = [w for w in wallets if w.is_active]

        open_positions = (
            self.db.query(CopiedTrade)
            .filter(CopiedTrade.status == "executed")
            .all()
        )
        total_exposure = sum(t.size or 0 for t in open_positions)

        all_closed = (
            self.db.query(CopiedTrade)
            .filter(CopiedTrade.status == "closed")
            .all()
        )
        total_pnl = sum(t.realized_pnl or 0 for t in all_closed)

        all_executed = (
            self.db.query(CopiedTrade)
            .filter(CopiedTrade.status.in_(["executed", "closed"]))
            .count()
        )
        all_skipped = (
            self.db.query(CopiedTrade)
            .filter(CopiedTrade.status == "skipped")
            .count()
        )

        wins = sum(1 for t in all_closed if (t.realized_pnl or 0) > 0)
        overall_win_rate = wins / len(all_closed) if all_closed else 0

        uptime = 0
        if start_time:
            uptime = int((datetime.utcnow() - start_time).total_seconds())

        top_wallet_stats = self.get_all_wallet_stats()[:5]

        return CopyTradingStatus(
            is_running=is_running,
            mode=mode,
            total_wallets_tracked=len(wallets),
            active_wallets=len(active_wallets),
            open_positions=len(open_positions),
            total_exposure=round(total_exposure, 2),
            total_pnl=round(total_pnl, 2),
            total_trades_copied=all_executed,
            total_trades_skipped=all_skipped,
            overall_win_rate=round(overall_win_rate, 4),
            bankroll=bankroll,
            available_capital=available_capital,
            last_scan=last_scan,
            uptime_seconds=uptime,
            top_wallets=top_wallet_stats,
        )

    # ------------------------------------------------------------------
    # Slippage analysis
    # ------------------------------------------------------------------

    def get_slippage_report(self, days: int = 7) -> Dict[str, Any]:
        """Analyze slippage across all copy trades."""
        since = datetime.utcnow() - timedelta(days=days)
        trades = (
            self.db.query(CopiedTrade)
            .filter(
                CopiedTrade.status.in_(["executed", "closed"]),
                CopiedTrade.executed_at >= since,
                CopiedTrade.slippage.isnot(None),
            )
            .all()
        )

        if not trades:
            return {"trades_analyzed": 0}

        slippages = [t.slippage for t in trades if t.slippage is not None]
        return {
            "trades_analyzed": len(trades),
            "avg_slippage": round(sum(slippages) / len(slippages), 6),
            "max_slippage": round(max(slippages), 6),
            "min_slippage": round(min(slippages), 6),
            "median_slippage": round(sorted(slippages)[len(slippages) // 2], 6),
            "total_slippage_cost": round(
                sum(t.slippage * t.size for t in trades if t.slippage), 2
            ),
        }

    # ------------------------------------------------------------------
    # Daily snapshots
    # ------------------------------------------------------------------

    def save_daily_snapshot(self):
        """Save a daily performance snapshot for each tracked wallet."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        wallets = self.db.query(TrackedWallet).all()

        for wallet in wallets:
            # Check if snapshot already exists
            existing = (
                self.db.query(WalletPerformance)
                .filter(
                    WalletPerformance.wallet_address == wallet.address,
                    WalletPerformance.date == today,
                )
                .first()
            )
            if existing:
                continue

            # Get today's trades
            today_trades = (
                self.db.query(CopiedTrade)
                .filter(
                    CopiedTrade.source_wallet == wallet.address,
                    CopiedTrade.detected_at >= today,
                )
                .all()
            )

            detected = len(today_trades)
            copied = [t for t in today_trades if t.status in ("executed", "closed")]
            skipped = [t for t in today_trades if t.status == "skipped"]
            closed = [t for t in today_trades if t.status == "closed"]

            realized = sum(t.realized_pnl or 0 for t in closed)
            unrealized = sum(t.unrealized_pnl or 0 for t in today_trades if t.status == "executed")
            wins = sum(1 for t in closed if (t.realized_pnl or 0) > 0)
            losses = sum(1 for t in closed if (t.realized_pnl or 0) < 0)
            volume = sum(t.size or 0 for t in copied)

            snapshot = WalletPerformance(
                wallet_address=wallet.address,
                date=today,
                trades_detected=detected,
                trades_copied=len(copied),
                trades_skipped=len(skipped),
                realized_pnl=round(realized, 2),
                unrealized_pnl=round(unrealized, 2),
                total_pnl=round(realized + unrealized, 2),
                winning_trades=wins,
                losing_trades=losses,
                total_volume_copied=round(volume, 2),
            )
            self.db.add(snapshot)

        self.db.commit()
        logger.info("Daily performance snapshots saved")

    # ------------------------------------------------------------------
    # Trade history queries
    # ------------------------------------------------------------------

    def get_recent_trades(
        self,
        limit: int = 50,
        wallet_address: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[CopiedTrade]:
        """Get recent copied trades with optional filters."""
        query = self.db.query(CopiedTrade)

        if wallet_address:
            query = query.filter(
                CopiedTrade.source_wallet == wallet_address.lower()
            )
        if status:
            query = query.filter(CopiedTrade.status == status)

        return query.order_by(CopiedTrade.detected_at.desc()).limit(limit).all()

    def get_pnl_history(
        self,
        days: int = 30,
        wallet_address: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get daily P&L history."""
        since = datetime.utcnow() - timedelta(days=days)
        query = self.db.query(WalletPerformance).filter(
            WalletPerformance.date >= since
        )
        if wallet_address:
            query = query.filter(
                WalletPerformance.wallet_address == wallet_address.lower()
            )

        snapshots = query.order_by(WalletPerformance.date.asc()).all()

        # Aggregate by date if viewing all wallets
        daily: Dict[str, Dict[str, float]] = {}
        for s in snapshots:
            date_str = s.date.strftime("%Y-%m-%d")
            if date_str not in daily:
                daily[date_str] = {
                    "date": date_str,
                    "realized_pnl": 0,
                    "unrealized_pnl": 0,
                    "total_pnl": 0,
                    "trades_copied": 0,
                    "volume": 0,
                }
            daily[date_str]["realized_pnl"] += s.realized_pnl or 0
            daily[date_str]["unrealized_pnl"] += s.unrealized_pnl or 0
            daily[date_str]["total_pnl"] += s.total_pnl or 0
            daily[date_str]["trades_copied"] += s.trades_copied or 0
            daily[date_str]["volume"] += s.total_volume_copied or 0

        return list(daily.values())
