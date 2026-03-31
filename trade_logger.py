"""
Clawbot — Trade Logger
Writes every trade action and resolution to trade_log.csv.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

import config

# CSV columns — do NOT reorder (append-only file)
_COLUMNS = [
    "timestamp",
    "city",
    "market_slug",
    "edge_degrees",
    "signal_strength",
    "ensemble_agrees",
    "size_usdc",
    "yes_price",
    "kelly_fraction",
    "order_id",
    "status",          # PAPER | LIVE | FILLED | CANCELLED | EXPIRED
    "pnl",             # blank until resolved
    "notes",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TradeLogger:
    """Append-only CSV logger for weather bot trades."""

    def __init__(self, log_file: str = config.LOG_FILE):
        self.log_file = log_file
        self._ensure_header()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_trade(
        self,
        signal: dict,
        order_response: Optional[dict],
        size_usdc: float,
        kelly_fraction: float = 0.0,
        paper: bool = True,
    ) -> None:
        """
        Record a new trade (or paper trade) to the CSV.

        Args:
            signal:         The weather signal dict from weather_signals.json.
            order_response: The dict returned by the CLOB (or None for paper).
            size_usdc:      USDC spent on the trade.
            kelly_fraction: The Kelly fraction used to size this trade.
            paper:          True if this is a paper trade.
        """
        order_id = ""
        status = "PAPER" if paper else "LIVE"

        if order_response:
            order_id = order_response.get("orderID", order_response.get("id", ""))
            if not paper:
                api_status = order_response.get("status", "")
                if api_status:
                    status = api_status.upper()

        row = {
            "timestamp":       _now_iso(),
            "city":            signal.get("city", ""),
            "market_slug":     signal.get("slug", ""),
            "edge_degrees":    signal.get("edge_degrees", ""),
            "signal_strength": signal.get("signal_strength", ""),
            "ensemble_agrees": signal.get("ensemble_agrees", ""),
            "size_usdc":       round(size_usdc, 4),
            "yes_price":       signal.get("forecast_bucket_yes", ""),
            "kelly_fraction":  round(kelly_fraction, 6),
            "order_id":        order_id,
            "status":          status,
            "pnl":             "",
            "notes":           "",
        }

        self._append_row(row)
        logger.info(
            f"TradeLogger: logged {status} trade — {signal.get('city')} "
            f"${size_usdc:.2f} @ {signal.get('forecast_bucket_yes')} "
            f"| order={order_id or 'N/A'}"
        )

    def log_resolution(
        self,
        order_id: str,
        outcome: str,
        pnl: float,
    ) -> None:
        """
        Update the row for order_id with resolved outcome and P&L.

        Because the CSV is append-only, we add a new RESOLVED row that
        references the original order_id.

        Args:
            order_id: The CLOB order ID of the original trade.
            outcome:  "WIN" | "LOSS" | "PUSH"
            pnl:      Realised P&L in USDC (positive = profit).
        """
        row = {
            "timestamp":       _now_iso(),
            "city":            "",
            "market_slug":     "",
            "edge_degrees":    "",
            "signal_strength": "",
            "ensemble_agrees": "",
            "size_usdc":       "",
            "yes_price":       "",
            "kelly_fraction":  "",
            "order_id":        order_id,
            "status":          f"RESOLVED:{outcome}",
            "pnl":             round(pnl, 4),
            "notes":           f"outcome={outcome}",
        }
        self._append_row(row)
        logger.info(f"TradeLogger: resolved order {order_id} → {outcome}, P&L=${pnl:.2f}")

    def get_daily_pnl(self) -> float:
        """
        Sum all resolved P&L rows for today (UTC).

        Returns:
            Float — total realised P&L for today.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        total = 0.0
        for row in self._read_rows():
            if not row["timestamp"].startswith(today):
                continue
            if not row["status"].startswith("RESOLVED"):
                continue
            try:
                total += float(row["pnl"])
            except (ValueError, TypeError):
                pass
        return total

    def print_stats(self) -> None:
        """Print summary statistics to stdout."""
        rows = self._read_rows()
        trades = [r for r in rows if r["status"] in ("PAPER", "LIVE", "MATCHED")]
        resolved = [r for r in rows if r["status"].startswith("RESOLVED")]

        wins   = [r for r in resolved if "WIN"  in r["status"]]
        losses = [r for r in resolved if "LOSS" in r["status"]]
        pnls   = []
        for r in resolved:
            try:
                pnls.append(float(r["pnl"]))
            except (ValueError, TypeError):
                pass

        total_pnl  = sum(pnls)
        avg_pnl    = total_pnl / len(pnls) if pnls else 0
        win_rate   = len(wins) / len(resolved) * 100 if resolved else 0

        print("\n========== Clawbot Trade Stats ==========")
        print(f"  Total trades entered : {len(trades)}")
        print(f"  Resolved             : {len(resolved)}")
        print(f"  Win rate             : {win_rate:.1f}%")
        print(f"  Total P&L            : ${total_pnl:.2f}")
        print(f"  Avg P&L per trade    : ${avg_pnl:.2f}")
        print(f"  Today's P&L          : ${self.get_daily_pnl():.2f}")
        print("=========================================\n")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_header(self) -> None:
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=_COLUMNS)
                writer.writeheader()
            logger.debug(f"TradeLogger: created {self.log_file}")

    def _append_row(self, row: dict) -> None:
        with open(self.log_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS)
            writer.writerow(row)

    def _read_rows(self) -> list[dict]:
        if not os.path.exists(self.log_file):
            return []
        with open(self.log_file, newline="") as f:
            return list(csv.DictReader(f))
