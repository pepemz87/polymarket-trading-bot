"""
Clawbot — Wallet Manager
Reads USDC balance, open positions, and allowance from Polymarket CLOB.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from loguru import logger

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds, AssetType, BalanceAllowanceParams
    from py_clob_client.constants import POLYGON
    CLOB_AVAILABLE = True
except ImportError:
    CLOB_AVAILABLE = False
    logger.warning("py-clob-client not installed — wallet queries will be skipped")

import config


class WalletManager:
    """
    Thin wrapper around the CLOB client for wallet-related queries.

    All methods are read-only; order placement is handled by WeatherBot.
    """

    def __init__(self, client: Optional[object] = None):
        """
        Args:
            client: An already-initialised ClobClient instance, or None to
                    build one from config.py environment variables.
        """
        self._client = client

        if self._client is None and CLOB_AVAILABLE:
            self._client = self._build_client()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_client(self) -> Optional[object]:
        """Build a ClobClient from config.py credentials."""
        if not config.POLY_PRIVATE_KEY:
            logger.warning("POLY_PRIVATE_KEY not set — wallet queries disabled")
            return None

        try:
            creds = None
            if all([config.POLY_API_KEY, config.POLY_API_SECRET, config.POLY_API_PASSPHRASE]):
                creds = ApiCreds(
                    api_key=config.POLY_API_KEY,
                    api_secret=config.POLY_API_SECRET,
                    api_passphrase=config.POLY_API_PASSPHRASE,
                )

            client = ClobClient(
                host=config.CLOB_HOST,
                key=config.POLY_PRIVATE_KEY,
                chain_id=POLYGON,
                creds=creds,
                signature_type=0,   # EOA
                funder=config.POLY_WALLET_ADDRESS or None,
            )
            logger.info("WalletManager: ClobClient initialised")
            return client
        except Exception as exc:
            logger.error(f"WalletManager: failed to build ClobClient — {exc}")
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_usdc_balance(self) -> float:
        """
        Return the USDC balance available on the CLOB.

        Returns:
            Balance in USDC (float). Returns 0.0 on failure.
        """
        if self._client is None:
            logger.warning("WalletManager: client not available — returning 0 balance")
            return 0.0

        try:
            params = BalanceAllowanceParams(asset_type=AssetType.USDC)
            result = self._client.get_balance_allowance(params=params)
            # result is a dict: {"balance": "...", "allowance": "..."}
            raw = result.get("balance", "0")
            # USDC has 6 decimals on Polygon
            usdc = float(raw) / 1_000_000
            logger.debug(f"WalletManager: USDC balance = ${usdc:.2f}")
            return usdc
        except Exception as exc:
            logger.error(f"WalletManager.get_usdc_balance failed: {exc}")
            return 0.0

    def get_open_positions(self) -> list[dict]:
        """
        Return open positions from the CLOB (active orders / fills).

        Returns:
            List of position dicts with keys:
            {asset_id, size, avg_price, side, market_slug}
        """
        if self._client is None:
            return []

        try:
            trades = self._client.get_trades(
                params={"maker_address": config.POLY_WALLET_ADDRESS, "status": "MATCHED"}
            )
            positions = []
            seen: set[str] = set()
            for t in (trades or []):
                asset_id = t.get("asset_id", "")
                if asset_id in seen:
                    continue
                seen.add(asset_id)
                positions.append({
                    "asset_id":   asset_id,
                    "size":       float(t.get("size", 0)),
                    "avg_price":  float(t.get("price", 0)),
                    "side":       t.get("side", "BUY"),
                    "market_slug": t.get("market", ""),
                })
            logger.debug(f"WalletManager: {len(positions)} open positions")
            return positions
        except Exception as exc:
            logger.error(f"WalletManager.get_open_positions failed: {exc}")
            return []

    def check_allowance(self) -> bool:
        """
        Verify that the CTF Exchange contract has USDC allowance.

        Returns:
            True if allowance > 0, False otherwise.
        """
        if self._client is None:
            return False

        try:
            params = BalanceAllowanceParams(asset_type=AssetType.USDC)
            result = self._client.get_balance_allowance(params=params)
            raw_allowance = result.get("allowance", "0")
            allowance = float(raw_allowance) / 1_000_000
            ok = allowance > 0
            if not ok:
                logger.warning("WalletManager: USDC allowance is 0 — approve the CLOB contract first")
            else:
                logger.debug(f"WalletManager: USDC allowance = ${allowance:.2f}")
            return ok
        except Exception as exc:
            logger.error(f"WalletManager.check_allowance failed: {exc}")
            return False

    def get_client(self):
        """Return the underlying ClobClient for use by WeatherBot."""
        return self._client

    def create_or_derive_api_creds(self) -> Optional[object]:
        """
        Derive CLOB API credentials from the private key (one-time setup).
        Prints the creds so you can save them to .env.

        Returns:
            ApiCreds object or None.
        """
        if self._client is None:
            logger.error("Cannot derive creds: client not initialised")
            return None
        try:
            creds = self._client.create_or_derive_api_creds()
            print("\n--- Save these to your .env file ---")
            print(f"POLY_API_KEY={creds.api_key}")
            print(f"POLY_API_SECRET={creds.api_secret}")
            print(f"POLY_API_PASSPHRASE={creds.api_passphrase}")
            print("------------------------------------\n")
            return creds
        except Exception as exc:
            logger.error(f"WalletManager.create_or_derive_api_creds failed: {exc}")
            return None
