"""eBay Browse API client: application login token + keyword search."""

from __future__ import annotations

import base64
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

from . import web
from .config import CONDITIONS, Search, Settings

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"
# Renew the login token this many seconds before eBay says it expires.
TOKEN_SAFETY_MARGIN = 300


class EbayError(Exception):
    """Anything that stopped a search from returning listings."""


class EbayAuthError(EbayError):
    """eBay rejected the App ID / Cert ID."""


class EbayRateLimitError(EbayError):
    """eBay says we've used up the allowance."""


@dataclass(frozen=True)
class Listing:
    item_id: str
    title: str
    url: str
    price: Optional[Decimal]
    currency: Optional[str]
    shipping: Optional[Decimal]  # None means eBay didn't give a postage cost
    image_url: Optional[str]
    condition: Optional[str]
    buying_options: tuple[str, ...]
    created_at: Optional[datetime]
    location_country: Optional[str]
    seller_feedback_pct: Optional[str]
    seller_feedback_score: Optional[int]

    @property
    def total(self) -> Optional[Decimal]:
        if self.price is None:
            return None
        return self.price + (self.shipping or Decimal("0"))

    @property
    def accepts_offers(self) -> bool:
        return "BEST_OFFER" in self.buying_options


def _decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _datetime(value) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_listing(raw: dict) -> Optional[Listing]:
    """Turn one eBay itemSummary into a Listing; None if it's unusable."""
    if not isinstance(raw, dict):
        return None
    item_id = raw.get("itemId")
    title = raw.get("title")
    url = raw.get("itemWebUrl")
    if not (isinstance(item_id, str) and isinstance(title, str) and isinstance(url, str)):
        return None

    price_obj = raw.get("price") or {}
    price = _decimal(price_obj.get("value"))
    currency = price_obj.get("currency")

    shipping = None
    for option in raw.get("shippingOptions") or []:
        cost = (option or {}).get("shippingCost") or {}
        value = _decimal(cost.get("value"))
        if value is None:
            continue
        if currency and cost.get("currency") and cost["currency"] != currency:
            continue
        if shipping is None or value < shipping:
            shipping = value

    image = (raw.get("image") or {}).get("imageUrl")
    seller = raw.get("seller") or {}
    score = seller.get("feedbackScore")
    location = raw.get("itemLocation") or {}

    return Listing(
        item_id=item_id,
        title=" ".join(title.split()),
        url=url,
        price=price,
        currency=currency,
        shipping=shipping,
        image_url=image if isinstance(image, str) else None,
        condition=raw.get("condition"),
        buying_options=tuple(raw.get("buyingOptions") or ()),
        created_at=_datetime(raw.get("itemCreationDate")),
        location_country=location.get("country"),
        seller_feedback_pct=seller.get("feedbackPercentage"),
        seller_feedback_score=score if isinstance(score, int) else None,
    )


def build_filter(search: Search, settings: Settings) -> str:
    parts = ["buyingOptions:{FIXED_PRICE}"]
    condition = CONDITIONS[search.condition]
    if condition:
        parts.append(f"conditions:{{{condition}}}")
    if search.location:
        parts.append(f"itemLocationCountry:{search.location}")
    # The min-only form isn't used: min_price is enforced by the monitor
    # instead, which avoids relying on an eBay syntax detail.
    if search.max_price is not None:
        low = "" if search.min_price is None else str(search.min_price)
        parts.append(f"price:[{low}..{search.max_price}]")
        parts.append(f"priceCurrency:{settings.currency}")
    return ",".join(parts)


def _error_text(resp: web.Response) -> str:
    try:
        data = resp.json()
    except (ValueError, UnicodeDecodeError):
        data = None
    if isinstance(data, dict):
        errors = data.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            msg = errors[0].get("longMessage") or errors[0].get("message")
            if msg:
                return str(msg)[:300]
        if data.get("error_description"):
            return str(data["error_description"])[:300]
        if data.get("error"):
            return str(data["error"])[:300]
    return f"HTTP {resp.status}"


class EbayClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        settings: Settings,
        transport: web.Transport = web.request,
        now: Callable[[], float] = time.time,
        token_url: Optional[str] = None,
        search_url: Optional[str] = None,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._settings = settings
        self._transport = transport
        self._now = now
        self._token_url = token_url or TOKEN_URL
        self._search_url = search_url or SEARCH_URL
        self._token: Optional[str] = None
        self._token_expires_at = 0.0
        self.calls_made = 0  # search calls, for the daily summary

    # -- login -------------------------------------------------------------

    def _get_token(self, force: bool = False) -> str:
        if not force and self._token and self._now() < self._token_expires_at - TOKEN_SAFETY_MARGIN:
            return self._token
        basic = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": SCOPE}).encode()
        try:
            resp = self._transport(
                "POST",
                self._token_url,
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                body=body,
            )
        except web.NetworkError as exc:
            raise EbayError(f"Couldn't reach eBay to log in: {exc}") from None
        if resp.status in (400, 401):
            raise EbayAuthError(
                f"eBay rejected the keys ({_error_text(resp)}). Check EBAY_CLIENT_ID and "
                f"EBAY_CLIENT_SECRET are your Production App ID and Cert ID."
            )
        if resp.status == 429:
            raise EbayRateLimitError("eBay login is rate-limited; will retry.")
        if resp.status != 200:
            raise EbayError(f"eBay login failed: {_error_text(resp)}")
        try:
            data = resp.json()
            token = data["access_token"]
            expires_in = int(data.get("expires_in", 7200))
        except (ValueError, KeyError, TypeError):
            raise EbayError("eBay login replied with something unexpected.") from None
        self._token = token
        self._token_expires_at = self._now() + expires_in
        return token

    # -- search ------------------------------------------------------------

    def build_params(self, search: Search) -> dict:
        return {
            "q": search.query,
            "filter": build_filter(search, self._settings),
            "sort": "newlyListed",
            "limit": str(self._settings.results_per_search),
        }

    def search(self, search: Search) -> list[Listing]:
        url = self._search_url + "?" + urllib.parse.urlencode(self.build_params(search))
        resp = None
        for attempt in (1, 2):
            token = self._get_token(force=attempt == 2)
            try:
                resp = self._transport(
                    "GET",
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-EBAY-C-MARKETPLACE-ID": self._settings.marketplace,
                        "Accept": "application/json",
                    },
                )
            except web.NetworkError as exc:
                raise EbayError(f"Couldn't reach eBay: {exc}") from None
            self.calls_made += 1
            if resp.status == 401 and attempt == 1:
                continue  # token expired early; log in again once
            break

        if resp.status == 429:
            raise EbayRateLimitError(
                "eBay says the daily allowance is used up. Alerts pause until it resets."
            )
        if resp.status != 200:
            raise EbayError(f'eBay search "{search.name}" failed: {_error_text(resp)}')
        try:
            data = resp.json() or {}
        except (ValueError, UnicodeDecodeError):
            raise EbayError(f'eBay search "{search.name}" replied with invalid data.') from None
        if not isinstance(data, dict):
            raise EbayError(f'eBay search "{search.name}" replied with invalid data.')
        listings = []
        for raw in data.get("itemSummaries") or []:
            listing = parse_listing(raw)
            if listing is not None:
                listings.append(listing)
        return listings
