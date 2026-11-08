"""Discord webhook alerts."""

from __future__ import annotations

import json
import re
import time
from decimal import Decimal
from typing import Callable, Optional

from . import web
from .ebay import Listing
from .filters import minutes_ago

COLOUR_DEAL = 0x2E8B57
COLOUR_PROBLEM = 0xD9822B
COLOUR_OK = 0x3B82F6
MIN_GAP_SECONDS = 0.6  # stays under Discord's ~5 messages / 2 seconds
MAX_RETRY_WAIT = 30.0

# Only characters that change meaning in Discord; brackets stop fake links.
# Pings are blocked separately by allowed_mentions.
_MARKDOWN = re.compile(r"([\\*_~`|\[\]>])")


class DiscordError(Exception):
    pass


def escape(text: str) -> str:
    """Stop listing titles from being read as Discord formatting/links."""
    return _MARKDOWN.sub(r"\\\1", text)


def money(value: Optional[Decimal], currency: Optional[str]) -> str:
    if value is None:
        return "?"
    if currency in (None, "GBP"):
        return f"£{value:.2f}"
    return f"{value:.2f} {currency}"


def listing_payload(listing: Listing, search_name: str, now: float, test: bool = False) -> dict:
    cur = listing.currency
    postage = "unknown" if listing.shipping is None else (
        "free" if listing.shipping == 0 else money(listing.shipping, cur)
    )
    total = money(listing.total, cur) + (" + postage?" if listing.shipping is None else "")
    age = minutes_ago(listing, now)
    age_text = "unknown" if age is None else ("just now" if age == 0 else f"{age} min ago")

    fields = [
        {"name": "Price", "value": money(listing.price, cur), "inline": True},
        {"name": "Postage", "value": postage, "inline": True},
        {"name": "Total", "value": total, "inline": True},
        {"name": "Condition", "value": escape(listing.condition or "not given"), "inline": True},
        {"name": "Listed", "value": age_text, "inline": True},
        {"name": "Search", "value": escape(search_name), "inline": True},
    ]
    if listing.seller_feedback_score is not None or listing.seller_feedback_pct:
        pct = f"{listing.seller_feedback_pct}%" if listing.seller_feedback_pct else "?"
        score = "?" if listing.seller_feedback_score is None else str(listing.seller_feedback_score)
        fields.append({"name": "Seller feedback", "value": f"{pct} ({score})", "inline": True})
    if listing.accepts_offers:
        fields.append({"name": "Offers", "value": "accepts offers", "inline": True})

    prefix = "TEST: " if test else ""
    embed = {
        "title": (prefix + listing.title)[:256],
        "url": listing.url,
        "color": COLOUR_DEAL,
        "fields": fields,
        "footer": {"text": "Vintage Monitor · eBay UK"},
    }
    if listing.image_url:
        embed["image"] = {"url": listing.image_url}

    # The plain-text line is what shows in the phone's push notification.
    content = f"{prefix}{total} · {escape(listing.title[:120])}"
    return {
        "content": content[:2000],
        "embeds": [embed],
        "allowed_mentions": {"parse": []},
    }


def text_payload(title: str, body: str, colour: int = COLOUR_OK) -> dict:
    return {
        "content": title[:2000],
        "embeds": [{"description": body[:4000], "color": colour}],
        "allowed_mentions": {"parse": []},
    }


class DiscordNotifier:
    def __init__(
        self,
        webhook_url: str,
        transport: web.Transport = web.request,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_gap: float = MIN_GAP_SECONDS,
    ):
        self._url = webhook_url
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self._min_gap = min_gap
        self._last_sent: Optional[float] = None

    def send(self, payload: dict) -> None:
        """Post one message; raises DiscordError if it can't be delivered."""
        body = json.dumps(payload).encode("utf-8")
        for attempt in range(1, 5):
            if self._last_sent is not None:
                wait = self._min_gap - (self._clock() - self._last_sent)
                if wait > 0:
                    self._sleep(wait)
            try:
                resp = self._transport(
                    "POST",
                    self._url,
                    headers={"Content-Type": "application/json"},
                    body=body,
                )
            except web.NetworkError as exc:
                raise DiscordError(f"Couldn't reach Discord: {exc}") from None
            finally:
                self._last_sent = self._clock()

            if 200 <= resp.status < 300:
                return
            if resp.status == 429 and attempt < 4:
                self._sleep(min(MAX_RETRY_WAIT, self._retry_after(resp)))
                continue
            if resp.status >= 500 and attempt < 4:
                self._sleep(2.0 * attempt)
                continue
            if resp.status in (401, 403, 404):
                raise DiscordError(
                    f"Discord rejected the webhook (HTTP {resp.status}). It may have been "
                    f"deleted. Make a new one and update DISCORD_WEBHOOK_URL."
                )
            raise DiscordError(f"Discord refused the message (HTTP {resp.status}).")
        raise DiscordError("Discord kept rate-limiting; message not sent.")

    @staticmethod
    def _retry_after(resp: web.Response) -> float:
        try:
            data = resp.json()
            if isinstance(data, dict) and "retry_after" in data:
                return max(0.1, float(data["retry_after"]))
        except (ValueError, TypeError, UnicodeDecodeError):
            pass
        try:
            return max(0.1, float(resp.headers.get("retry-after", "1")))
        except ValueError:
            return 1.0
