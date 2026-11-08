"""Decides whether a new listing deserves an alert."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from .config import Search, Settings
from .ebay import Listing


@lru_cache(maxsize=512)
def _word_pattern(term: str) -> re.Pattern:
    # Whole words/phrases only: "kids" matches "Kids'" but "boy" won't match "boyfriend".
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)


def excluded_word(title: str, exclude: tuple[str, ...]) -> Optional[str]:
    for term in exclude:
        if _word_pattern(term).search(title):
            return term
    return None


def rejection_reason(
    search: Search, listing: Listing, settings: Settings, now: float
) -> Optional[str]:
    """None means "alert"; otherwise a short reason it was skipped."""
    options = listing.buying_options
    if "FIXED_PRICE" not in options:
        return "not Buy It Now"
    if "AUCTION" in options:
        return "auction (with a Buy It Now option)"

    if search.location and listing.location_country and listing.location_country != search.location:
        return f"located in {listing.location_country}"

    term = excluded_word(listing.title, search.exclude)
    if term:
        return f'excluded word "{term}"'

    if listing.price is None:
        return "no price given"
    if listing.currency and listing.currency != settings.currency:
        return f"priced in {listing.currency}"
    if search.min_price is not None and listing.price < search.min_price:
        return f"price {listing.price} below min_price {search.min_price}"
    if search.max_price is not None and listing.price > search.max_price:
        return f"price {listing.price} above max_price {search.max_price}"
    if search.max_total is not None and listing.total > search.max_total:
        return f"total {listing.total} above max_total {search.max_total}"

    max_age = settings.max_listing_age_minutes
    if max_age and listing.created_at is not None:
        age_minutes = (now - listing.created_at.timestamp()) / 60
        if age_minutes > max_age:
            return f"listed {int(age_minutes)} minutes ago"
    return None


def minutes_ago(listing: Listing, now: float) -> Optional[int]:
    if listing.created_at is None:
        return None
    return max(0, int((now - listing.created_at.timestamp()) // 60))


def utc(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)
