"""Loading and strictly validating config.toml and the .env secrets file."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# eBay's default Browse API allowance is 5,000 calls a day. If eBay ever
# raises yours, change this number; the config can then go higher.
MAX_DAILY_CALL_BUDGET = 5000
# eBay rejects keyword searches longer than this.
MAX_QUERY_LENGTH = 100

CONDITIONS = {"used": "USED", "new": "NEW", "any": None}

SETTINGS_KEYS = {
    "marketplace",
    "currency",
    "daily_call_budget",
    "min_interval_seconds",
    "results_per_search",
    "max_listing_age_minutes",
    "problem_alert_after_minutes",
    "problem_alert_repeat_minutes",
    "daily_summary_time",
    "timezone",
}
DEFAULTS_KEYS = {"condition", "location", "exclude"}
SEARCH_KEYS = {
    "name",
    "query",
    "condition",
    "location",
    "min_price",
    "max_price",
    "max_total",
    "exclude",
}
TOP_LEVEL_KEYS = {"settings", "defaults", "search"}

WEBHOOK_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
    "https://canary.discord.com/api/webhooks/",
    "https://ptb.discord.com/api/webhooks/",
)


class ConfigError(Exception):
    """A problem in config.toml or .env, explained in plain words."""


@dataclass(frozen=True)
class Settings:
    marketplace: str = "EBAY_GB"
    currency: str = "GBP"
    daily_call_budget: int = 4500
    min_interval_seconds: int = 60
    results_per_search: int = 50
    max_listing_age_minutes: int = 120
    problem_alert_after_minutes: int = 15
    problem_alert_repeat_minutes: int = 60
    daily_summary_time: str = "09:00"
    timezone: str = "Europe/London"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def summary_hour_minute(self) -> tuple[int, int]:
        hour, minute = self.daily_summary_time.split(":")
        return int(hour), int(minute)


@dataclass(frozen=True)
class Search:
    name: str
    query: str
    condition: str = "used"
    location: Optional[str] = "GB"
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    max_total: Optional[Decimal] = None
    exclude: tuple[str, ...] = ()

    @property
    def fingerprint(self) -> str:
        """Identifies what eBay is asked. Changing any of these makes the
        monitor treat it as a new search (silently recorded, no flood)."""
        parts = [
            self.query.strip().lower(),
            self.condition,
            self.location,
            None if self.min_price is None else str(self.min_price),
            None if self.max_price is None else str(self.max_price),
        ]
        raw = json.dumps(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Config:
    settings: Settings
    searches: tuple[Search, ...]

    def cycle_seconds(self) -> float:
        """How often each search is checked, keeping within the daily budget."""
        n = len(self.searches)
        budget_based = 86400 * n / self.settings.daily_call_budget
        return float(max(self.settings.min_interval_seconds, math.ceil(budget_based)))

    def slot_seconds(self) -> float:
        """Gap between consecutive eBay calls (searches are spread evenly)."""
        return self.cycle_seconds() / len(self.searches)


@dataclass(frozen=True)
class Secrets:
    ebay_client_id: Optional[str]
    ebay_client_secret: Optional[str]
    discord_webhook_url: Optional[str]


# --------------------------------------------------------------------------
# helpers


def _check_keys(table: dict, allowed: set, where: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigError(
            f"{where}: unknown setting(s) {', '.join(repr(u) for u in unknown)}. "
            f"Allowed: {', '.join(sorted(allowed))}. Check for a typo."
        )


def _int(value, where: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{where} must be a whole number, got {value!r}.")
    if not lo <= value <= hi:
        raise ConfigError(f"{where} must be between {lo} and {hi}, got {value}.")
    return value


def _str(value, where: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{where} must be text in quotes, got {value!r}.")
    return value


def _money(value, where: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where} must be a number like 25 or 25.50, got {value!r}.")
    if value < 0:
        raise ConfigError(f"{where} can't be negative, got {value}.")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _condition(value, where: str) -> str:
    value = _str(value, where).strip().lower()
    if value not in CONDITIONS:
        raise ConfigError(f"{where} must be one of {', '.join(CONDITIONS)}, got {value!r}.")
    return value


def _location(value, where: str) -> Optional[str]:
    value = _str(value, where).strip().upper()
    if value == "":
        return None
    if not re.fullmatch(r"[A-Z]{2}", value):
        raise ConfigError(
            f"{where} must be a two-letter country code such as \"GB\", "
            f"or \"\" for anywhere; got {value!r}."
        )
    return value


def _exclude(value, where: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigError(f'{where} must be a list like ["kids", "replica"], got {value!r}.')
    out = []
    for i, word in enumerate(value):
        word = _str(word, f"{where}[{i}]").strip().lower()
        if not word:
            raise ConfigError(f"{where}[{i}] is empty.")
        if word not in out:
            out.append(word)
    return tuple(out)


# --------------------------------------------------------------------------
# config.toml


def load_config(path: str | os.PathLike) -> Config:
    path = Path(path)
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} isn't valid TOML: {exc}") from None
    return parse_config(data, str(path))


def parse_config(data: dict, source: str = "config") -> Config:
    _check_keys(data, TOP_LEVEL_KEYS, source)

    raw_settings = data.get("settings", {})
    if not isinstance(raw_settings, dict):
        raise ConfigError("[settings] must be a table.")
    _check_keys(raw_settings, SETTINGS_KEYS, "[settings]")
    kw = {}
    if "marketplace" in raw_settings:
        kw["marketplace"] = _str(raw_settings["marketplace"], "settings.marketplace").strip()
    if "currency" in raw_settings:
        kw["currency"] = _str(raw_settings["currency"], "settings.currency").strip().upper()
    if "daily_call_budget" in raw_settings:
        kw["daily_call_budget"] = _int(
            raw_settings["daily_call_budget"], "settings.daily_call_budget", 1, MAX_DAILY_CALL_BUDGET
        )
    if "min_interval_seconds" in raw_settings:
        kw["min_interval_seconds"] = _int(
            raw_settings["min_interval_seconds"], "settings.min_interval_seconds", 1, 86400
        )
    if "results_per_search" in raw_settings:
        kw["results_per_search"] = _int(
            raw_settings["results_per_search"], "settings.results_per_search", 1, 200
        )
    if "max_listing_age_minutes" in raw_settings:
        kw["max_listing_age_minutes"] = _int(
            raw_settings["max_listing_age_minutes"], "settings.max_listing_age_minutes", 0, 100000
        )
    if "problem_alert_after_minutes" in raw_settings:
        kw["problem_alert_after_minutes"] = _int(
            raw_settings["problem_alert_after_minutes"],
            "settings.problem_alert_after_minutes",
            1,
            10000,
        )
    if "problem_alert_repeat_minutes" in raw_settings:
        kw["problem_alert_repeat_minutes"] = _int(
            raw_settings["problem_alert_repeat_minutes"],
            "settings.problem_alert_repeat_minutes",
            1,
            100000,
        )
    if "daily_summary_time" in raw_settings:
        t = _str(raw_settings["daily_summary_time"], "settings.daily_summary_time").strip()
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", t)
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ConfigError(f'settings.daily_summary_time must look like "09:00", got {t!r}.')
        kw["daily_summary_time"] = f"{int(m.group(1)):02d}:{m.group(2)}"
    if "timezone" in raw_settings:
        kw["timezone"] = _str(raw_settings["timezone"], "settings.timezone").strip()
    s = Settings(**kw)
    try:
        ZoneInfo(s.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(f'settings.timezone {s.timezone!r} is unknown. Use e.g. "Europe/London".') from None

    raw_defaults = data.get("defaults", {})
    if not isinstance(raw_defaults, dict):
        raise ConfigError("[defaults] must be a table.")
    _check_keys(raw_defaults, DEFAULTS_KEYS, "[defaults]")
    d_condition = _condition(raw_defaults.get("condition", "used"), "defaults.condition")
    d_location = _location(raw_defaults.get("location", "GB"), "defaults.location")
    d_exclude = _exclude(raw_defaults.get("exclude", []), "defaults.exclude")

    raw_searches = data.get("search", [])
    if not isinstance(raw_searches, list) or not raw_searches:
        raise ConfigError("Add at least one [[search]] section to the config.")

    searches = []
    seen_names = set()
    seen_fps = {}
    for i, raw in enumerate(raw_searches, start=1):
        if not isinstance(raw, dict):
            raise ConfigError(f"Search #{i} must be a [[search]] table.")
        label = f"Search #{i}"
        if "name" in raw and isinstance(raw["name"], str) and raw["name"].strip():
            label = f'Search #{i} ("{raw["name"].strip()}")'
        _check_keys(raw, SEARCH_KEYS, label)
        if "name" not in raw:
            raise ConfigError(f"{label} needs a name.")
        name = _str(raw["name"], f"{label} name").strip()
        if not name:
            raise ConfigError(f"{label} has an empty name.")
        if name.lower() in seen_names:
            raise ConfigError(f'Two searches are both called "{name}". Names must be different.')
        seen_names.add(name.lower())

        if "query" not in raw:
            raise ConfigError(f"{label} needs a query (the eBay search words).")
        query = " ".join(_str(raw["query"], f"{label} query").split())
        if not query:
            raise ConfigError(f"{label} has an empty query.")
        if len(query) > MAX_QUERY_LENGTH:
            raise ConfigError(
                f"{label} query is {len(query)} characters; eBay allows {MAX_QUERY_LENGTH}."
            )

        condition = _condition(raw["condition"], f"{label} condition") if "condition" in raw else d_condition
        location = _location(raw["location"], f"{label} location") if "location" in raw else d_location
        min_price = _money(raw["min_price"], f"{label} min_price") if "min_price" in raw else None
        max_price = _money(raw["max_price"], f"{label} max_price") if "max_price" in raw else None
        max_total = _money(raw["max_total"], f"{label} max_total") if "max_total" in raw else None
        if min_price is not None and max_price is not None and min_price > max_price:
            raise ConfigError(f"{label}: min_price ({min_price}) is above max_price ({max_price}).")
        if min_price is not None and max_total is not None and min_price > max_total:
            raise ConfigError(f"{label}: min_price ({min_price}) is above max_total ({max_total}).")
        extra = _exclude(raw["exclude"], f"{label} exclude") if "exclude" in raw else ()
        exclude = tuple(dict.fromkeys(d_exclude + extra))

        search = Search(
            name=name,
            query=query,
            condition=condition,
            location=location,
            min_price=min_price,
            max_price=max_price,
            max_total=max_total,
            exclude=exclude,
        )
        if search.fingerprint in seen_fps:
            raise ConfigError(
                f'"{name}" asks eBay exactly the same thing as "{seen_fps[search.fingerprint]}". '
                f"Remove one; duplicates waste your daily eBay allowance."
            )
        seen_fps[search.fingerprint] = name
        searches.append(search)

    return Config(settings=s, searches=tuple(searches))


# --------------------------------------------------------------------------
# .env secrets


def read_env_file(path: str | os.PathLike) -> dict:
    """Parse KEY=VALUE lines. Blank lines and # comments are ignored;
    matching surrounding quotes are removed."""
    path = Path(path)
    values = {}
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"Secrets file not found: {path}") from None
    except PermissionError:
        raise ConfigError(f"No permission to read the secrets file: {path}") from None
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            raise ConfigError(f"{path} line {lineno}: expected KEY=VALUE.")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_secrets(
    env_path: Optional[str | os.PathLike],
    need_ebay: bool = True,
    need_discord: bool = True,
) -> Secrets:
    """Secrets come from the .env file; real environment variables win."""
    values = read_env_file(env_path) if env_path else {}
    for key in ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET", "DISCORD_WEBHOOK_URL"):
        if os.environ.get(key):
            values[key] = os.environ[key]

    def present(key: str) -> bool:
        value = values.get(key, "")
        return bool(value) and not value.startswith("PASTE_")

    required = []
    if need_ebay:
        required += ["EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"]
    if need_discord:
        required += ["DISCORD_WEBHOOK_URL"]
    missing = [k for k in required if not present(k)]
    if missing:
        where = f" ({env_path})" if env_path else ""
        raise ConfigError(f"Missing in the secrets file{where}: {', '.join(missing)}.")

    client_id = values["EBAY_CLIENT_ID"] if present("EBAY_CLIENT_ID") else None
    secret = values["EBAY_CLIENT_SECRET"] if present("EBAY_CLIENT_SECRET") else None
    webhook = values["DISCORD_WEBHOOK_URL"] if present("DISCORD_WEBHOOK_URL") else None

    if need_ebay and "-SBX-" in client_id.upper():
        raise ConfigError(
            "EBAY_CLIENT_ID is a Sandbox key (it contains -SBX-). Sandbox is eBay's "
            "fake test site. Use the Production keyset (contains -PRD-)."
        )
    if need_discord and not webhook.startswith(WEBHOOK_PREFIXES):
        raise ConfigError(
            "DISCORD_WEBHOOK_URL doesn't look like a Discord webhook. It should start "
            "with https://discord.com/api/webhooks/"
        )
    return Secrets(client_id, secret, webhook)
