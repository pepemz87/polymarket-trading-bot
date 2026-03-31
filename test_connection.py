"""
Clawbot — Integration Test
===========================
Run this once before starting the bot to verify your setup is correct.

    python test_connection.py

All 4 tests must pass before you switch PAPER_TRADING = False.
"""
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ── colour helpers ────────────────────────────────────────────────────────────
try:
    from termcolor import colored
    def ok(msg):   print(colored(f"  ✅  {msg}", "green"))
    def fail(msg): print(colored(f"  ❌  {msg}", "red"))
    def info(msg): print(colored(f"  ℹ️   {msg}", "cyan"))
except ImportError:
    def ok(msg):   print(f"  OK  {msg}")
    def fail(msg): print(f"  FAIL  {msg}")
    def info(msg): print(f"  INFO  {msg}")

errors = 0

print("\n╔═══════════════════════════════════════════════╗")
print("║   Clawbot — Connection & Config Test          ║")
print("╚═══════════════════════════════════════════════╝\n")

# ── Test 0: imports ───────────────────────────────────────────────────────────
print("Test 0: Python imports")
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds, BalanceAllowanceParams, AssetType
    from py_clob_client.constants import POLYGON
    ok("py-clob-client imported successfully")
except ImportError as e:
    fail(f"py-clob-client import failed: {e}")
    fail("Run:  pip install py-clob-client")
    errors += 1

try:
    import config
    ok("config.py imported successfully")
except Exception as e:
    fail(f"config.py import failed: {e}")
    errors += 1

# ── Test 1: CLOB server ───────────────────────────────────────────────────────
print("\nTest 1: CLOB server reachability")
try:
    client = ClobClient(
        host=config.CLOB_HOST,
        key=config.POLY_PRIVATE_KEY or "0x" + "0" * 64,
        chain_id=POLYGON,
    )
    server_time = client.get_server_time()
    ok(f"CLOB server OK — time: {server_time}")
except Exception as e:
    fail(f"CLOB server unreachable: {e}")
    errors += 1

# ── Test 2: API credentials ───────────────────────────────────────────────────
print("\nTest 2: API credentials")
if not config.POLY_PRIVATE_KEY:
    fail("POLY_PRIVATE_KEY not set in .env")
    info("Add your wallet private key to the .env file")
    errors += 1
else:
    try:
        creds = client.create_or_derive_api_creds()
        ok(f"API Creds OK — key: {creds.api_key[:8]}...")
        if not config.POLY_API_KEY:
            info("Save these creds to .env (run:  python weather_bot.py --setup-creds)")
    except Exception as e:
        fail(f"create_or_derive_api_creds failed: {e}")
        errors += 1

# ── Test 3: USDC balance ──────────────────────────────────────────────────────
print("\nTest 3: USDC balance & allowance")
if config.POLY_API_KEY and config.POLY_API_SECRET and config.POLY_API_PASSPHRASE:
    try:
        authed_client = ClobClient(
            host=config.CLOB_HOST,
            key=config.POLY_PRIVATE_KEY,
            chain_id=POLYGON,
            creds=ApiCreds(
                api_key=config.POLY_API_KEY,
                api_secret=config.POLY_API_SECRET,
                api_passphrase=config.POLY_API_PASSPHRASE,
            ),
            signature_type=0,
        )
        params = BalanceAllowanceParams(asset_type=AssetType.USDC)
        result = authed_client.get_balance_allowance(params=params)
        raw_bal = float(result.get("balance", 0)) / 1_000_000
        raw_all = float(result.get("allowance", 0)) / 1_000_000
        ok(f"USDC balance   = ${raw_bal:.2f}")
        ok(f"USDC allowance = ${raw_all:.2f}")
        if raw_all == 0:
            fail("Allowance is 0 — approve the CLOB contract to spend USDC first")
            errors += 1
    except Exception as e:
        fail(f"Balance/allowance check failed: {e}")
        errors += 1
else:
    info("Skipping balance check — API creds not set in .env")
    info("Run  python weather_bot.py --setup-creds  to generate them")

# ── Test 4: Order book from signals file ─────────────────────────────────────
print("\nTest 4: Order book lookup from weather_signals.json")
signals_file = config.SIGNALS_FILE
if not os.path.exists(signals_file):
    info(f"{signals_file} not found — run weather_scanner.py first")
else:
    try:
        with open(signals_file) as f:
            signals = json.load(f)

        if not signals:
            info(f"{signals_file} is empty — no signals to test")
        else:
            s = signals[0]
            token_id = s.get("forecast_bucket_token", "")
            city     = s.get("city_display", "?")
            if not token_id:
                fail("First signal has no forecast_bucket_token")
                errors += 1
            else:
                book = client.get_order_book(token_id)
                asks = getattr(book, "asks", None) or []
                bids = getattr(book, "bids", None) or []
                best_ask = float(asks[0].price) if asks else None
                best_bid = float(bids[0].price) if bids else None
                ok(f"Order book for {city} — best ask: {best_ask}, best bid: {best_bid}")
    except Exception as e:
        fail(f"Order book test failed: {e}")
        errors += 1

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "─" * 48)
if errors == 0:
    ok(f"All tests passed — ready to run the bot!")
    print()
    print("  Start paper trading:  python weather_bot.py --paper")
    print("  Check status:         python weather_bot.py --status")
else:
    fail(f"{errors} test(s) failed — fix the issues above before running the bot")
    sys.exit(1)
print()
