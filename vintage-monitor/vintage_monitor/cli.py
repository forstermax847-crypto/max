"""Command line: run, check, test-alert, status, validate."""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from . import __version__
from .config import Config, ConfigError, load_config, load_secrets
from .discord import DiscordError, DiscordNotifier, listing_payload, text_payload
from .ebay import EbayClient, EbayError, Listing, build_filter
from .filters import minutes_ago, rejection_reason
from .monitor import Monitor, fmt_seconds
from .store import Store

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_DIR / "config.toml"
DEFAULT_ENV = PROJECT_DIR / ".env"
DEFAULT_DB = PROJECT_DIR / "data" / "monitor.db"
SERVICE_NAME = "vintage-monitor"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CONFIG = 2


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=str(DEFAULT_CONFIG), help="searches file (config.toml)")
    common.add_argument("--env", default=str(DEFAULT_ENV), help="secrets file (.env)")
    common.add_argument("--db", default=str(DEFAULT_DB), help="database file")
    common.add_argument("-v", "--verbose", action="store_true", help="show skipped listings too")

    parser = argparse.ArgumentParser(
        prog="vintage_monitor",
        description="Watches eBay UK for new listings and alerts Discord.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    run = sub.add_parser("run", parents=[common], help="run 24/7 (what the service does)")
    run.add_argument("--max-checks", type=int, default=None, help=argparse.SUPPRESS)
    sub.add_parser("check", parents=[common], help="run each search once and print results")
    sub.add_parser("test-alert", parents=[common], help="send a test alert to Discord")
    sub.add_parser("status", parents=[common], help="show whether it's working")
    sub.add_parser("validate", parents=[common], help="check config.toml for mistakes")
    return parser


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def _when(ts: Optional[float], now: float, tz=None) -> str:
    if ts is None:
        return "never"
    local = datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M:%S")
    return f"{local} ({fmt_seconds(max(0.0, now - ts))} ago)"


def _money(value: Optional[Decimal]) -> str:
    return "?" if value is None else f"£{value:.2f}"


# ---------------------------------------------------------------- commands


def cmd_validate(config: Config) -> int:
    s = config.settings
    print(f"Config OK: {len(config.searches)} searches.")
    print(
        f"Each search is checked about every {fmt_seconds(config.cycle_seconds())} "
        f"(one eBay call every {config.slot_seconds():.1f} s, "
        f"budget {s.daily_call_budget} calls/day)."
    )
    for search in config.searches:
        limits = []
        if search.min_price is not None:
            limits.append(f"min {_money(search.min_price)}")
        if search.max_price is not None:
            limits.append(f"max price {_money(search.max_price)}")
        if search.max_total is not None:
            limits.append(f"max total {_money(search.max_total)}")
        print(f"\n  {search.name}")
        print(f"    query:   {search.query}")
        print(f"    eBay:    {build_filter(search, s)}")
        print(f"    limits:  {', '.join(limits) if limits else 'NONE (every new listing alerts)'}")
        print(f"    exclude: {', '.join(search.exclude) if search.exclude else '(none)'}")
    return EXIT_OK


def cmd_check(config: Config, env: str) -> int:
    secrets = load_secrets(env, need_ebay=True, need_discord=False)
    client = EbayClient(secrets.ebay_client_id, secrets.ebay_client_secret, config.settings)
    now = time.time()
    failed = False
    for search in config.searches:
        print(f"\n=== {search.name}: {search.query}")
        try:
            listings = client.search(search)
        except EbayError as exc:
            print(f"  ERROR: {exc}")
            failed = True
            continue
        would = 0
        for listing in listings:
            if rejection_reason(search, listing, config.settings, now) is None:
                would += 1
        print(
            f"  {len(listings)} listings returned; {would} pass your filters "
            f"(ignoring whether they were already seen)."
        )
        for listing in listings[:8]:
            reason = rejection_reason(search, listing, config.settings, now)
            age = minutes_ago(listing, now)
            age_text = "?" if age is None else f"{age} min"
            post = "?" if listing.shipping is None else _money(listing.shipping)
            verdict = "ALERT" if reason is None else f"skip: {reason}"
            print(
                f"  {age_text:>8} ago  {_money(listing.price)} + {post} = "
                f"{_money(listing.total)}  [{verdict}]"
            )
            print(f"             {listing.title}")
            print(f"             {listing.url}")
    return EXIT_FAILED if failed else EXIT_OK


def cmd_test_alert(env: str) -> int:
    secrets = load_secrets(env, need_ebay=False, need_discord=True)
    notifier = DiscordNotifier(secrets.discord_webhook_url)
    now = time.time()
    sample = Listing(
        item_id="TEST",
        title="Barbour Beaufort wax jacket, size 40 (sample, not a real listing)",
        url="https://www.ebay.co.uk/",
        price=Decimal("22.00"),
        currency="GBP",
        shipping=Decimal("4.49"),
        image_url=None,
        condition="Pre-owned",
        buying_options=("FIXED_PRICE", "BEST_OFFER"),
        created_at=datetime.fromtimestamp(now - 180, tz=timezone.utc),
        location_country="GB",
        seller_feedback_pct="99.6",
        seller_feedback_score=412,
    )
    try:
        notifier.send(
            text_payload(
                "🧪 Vintage Monitor test",
                "If your phone buzzed for this, alerts are set up correctly. "
                "The next message is a sample deal alert.",
            )
        )
        notifier.send(listing_payload(sample, "Test", now, test=True))
    except DiscordError as exc:
        print(f"FAILED: {exc}")
        return EXIT_FAILED
    print("Sent 2 test messages to Discord. Check #deals and your phone.")
    return EXIT_OK


def _service_state() -> Optional[str]:
    if not shutil.which("systemctl"):
        return None
    try:
        out = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout.strip() or out.stderr.strip()).splitlines()
    return text[0] if text else None


def cmd_status(config: Config, db: str) -> int:
    now = time.time()
    tz = config.settings.tz
    state = _service_state()
    if state is not None:
        print(f"Service:               {state}")
    if not Path(db).exists():
        print(f"No database yet at {db}: the monitor has never run with these settings.")
        return EXIT_FAILED
    store = Store(db)
    try:
        last_check = store.get_float("last_check_at")
        print(f"Last eBay check:       {_when(last_check, now, tz)}")
        print(f"Last successful check: {_when(store.get_float('last_success_at'), now, tz)}")
        print(f"Last alert:            {_when(store.get_float('last_alert_at'), now, tz)}")
        last_error = store.get("last_error")
        if last_error:
            print(f"Last error:            {_when(store.get_float('last_error_at'), now, tz)}")
            print(f"                       {last_error}")
        else:
            print("Last error:            none")
        print(
            f"Since last daily message: {store.get_int('summary_checks')} checks, "
            f"{store.get_int('summary_alerts')} alerts, {store.get_int('summary_errors')} errors"
        )
        print(f"Searches recorded:     {store.count_seeded()} (current config has {len(config.searches)})")
        healthy = last_check is not None and now - last_check < 3 * config.slot_seconds() + 120
        if store.get("problem_active") == "1":
            print("\n⚠️  A problem alert is active: see Discord for details.")
            return EXIT_FAILED
        if not healthy:
            print("\n⚠️  No recent eBay check: the monitor may be stopped.")
            return EXIT_FAILED
        print("\nLooks healthy.")
        return EXIT_OK
    finally:
        store.close()


def cmd_run(config: Config, env: str, db: str, max_checks: Optional[int]) -> int:
    secrets = load_secrets(env)
    logging.getLogger("vintage_monitor").info(
        "Starting: %d searches, each every %s.",
        len(config.searches),
        fmt_seconds(config.cycle_seconds()),
    )
    store = Store(db)
    try:
        monitor = Monitor(
            config,
            EbayClient(secrets.ebay_client_id, secrets.ebay_client_secret, config.settings),
            DiscordNotifier(secrets.discord_webhook_url),
            store,
        )
        monitor.run(max_checks=max_checks)
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        store.close()
    return EXIT_OK


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    _setup_logging(getattr(args, "verbose", False))
    try:
        config = load_config(args.config)
        if args.command == "validate":
            return cmd_validate(config)
        if args.command == "check":
            return cmd_check(config, args.env)
        if args.command == "test-alert":
            return cmd_test_alert(args.env)
        if args.command == "status":
            return cmd_status(config, args.db)
        if args.command == "run":
            return cmd_run(config, args.env, args.db, args.max_checks)
    except ConfigError as exc:
        print(f"CONFIG PROBLEM: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    return EXIT_FAILED  # pragma: no cover - argparse guarantees a command
