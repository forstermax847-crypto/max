"""Shared fakes for the tests."""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone

from vintage_monitor import web
from vintage_monitor.config import parse_config

# 2026-11-08 12:00:00 UTC (= 12:00 in London, no daylight saving in November)
T0 = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc).timestamp()


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def item(
    item_id: str,
    title: str = "Barbour Beaufort wax jacket size 40",
    price: str = "20.00",
    shipping: str | None = "4.00",
    created: float | None = None,
    options=("FIXED_PRICE",),
    country: str = "GB",
) -> dict:
    raw = {
        "itemId": item_id,
        "title": title,
        "itemWebUrl": f"https://www.ebay.co.uk/itm/{item_id}",
        "price": {"value": price, "currency": "GBP"},
        "buyingOptions": list(options),
        "condition": "Pre-owned",
        "image": {"imageUrl": f"https://i.ebayimg.com/{item_id}.jpg"},
        "itemLocation": {"country": country},
        "seller": {"username": "someone", "feedbackPercentage": "99.5", "feedbackScore": 120},
    }
    if shipping is not None:
        raw["shippingOptions"] = [
            {"shippingCostType": "FIXED", "shippingCost": {"value": shipping, "currency": "GBP"}}
        ]
    if created is not None:
        raw["itemCreationDate"] = iso(created)
    return raw


def make_config(searches=None, **settings):
    data = {
        "settings": {"min_interval_seconds": 60, **settings},
        "defaults": {"condition": "used", "location": "GB", "exclude": ["kids", "replica"]},
        "search": searches
        or [{"name": "Barbour wax", "query": "barbour wax jacket", "max_total": 30}],
    }
    return parse_config(data, "test")


class Clock:
    def __init__(self, start: float = T0):
        self.t = start
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


class FakeEbay:
    """Transport that behaves like eBay's token + search endpoints."""

    def __init__(self):
        self.results: dict[str, list] = {}  # query -> list of item dicts
        self.fail_with: dict[str, tuple[int, dict]] = {}  # query -> (status, body)
        self.token_status = 200
        self.token_counter = 0
        self.calls: list[tuple[str, str, dict]] = []
        self.expire_next_search = False

    def __call__(self, method, url, headers=None, body=None, timeout=20):
        headers = headers or {}
        self.calls.append((method, url, headers))
        if "oauth2/token" in url:
            if self.token_status != 200:
                return web.Response(self.token_status, json.dumps(
                    {"error": "invalid_client", "error_description": "client authentication failed"}
                ).encode())
            self.token_counter += 1
            return web.Response(200, json.dumps(
                {"access_token": f"tok{self.token_counter}", "expires_in": 7200, "token_type": "Application Access Token"}
            ).encode())
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        q = query["q"][0]
        if self.expire_next_search:
            self.expire_next_search = False
            return web.Response(401, b'{"errors":[{"message":"Invalid access token"}]}')
        if q in self.fail_with:
            status, payload = self.fail_with[q]
            return web.Response(status, json.dumps(payload).encode())
        items = self.results.get(q, [])
        return web.Response(200, json.dumps({"total": len(items), "itemSummaries": items}).encode())

    @property
    def search_calls(self):
        return [c for c in self.calls if "item_summary" in c[1]]


class FakeDiscord:
    """Transport that records webhook posts; can be told to fail."""

    def __init__(self):
        self.posts: list[dict] = []
        self.responses: list[web.Response] = []  # consumed first, then 204
        self.down = False
        self.attempts = 0

    def __call__(self, method, url, headers=None, body=None, timeout=20):
        self.attempts += 1
        if self.down:
            raise web.NetworkError("connection refused")
        if self.responses:
            resp = self.responses.pop(0)
            if 200 <= resp.status < 300:
                self.posts.append(json.loads(body))
            return resp
        self.posts.append(json.loads(body))
        return web.Response(204)

    def deal_titles(self):
        return [p["embeds"][0]["title"] for p in self.posts if p["embeds"][0].get("url")]

    def texts(self):
        return [p["content"] for p in self.posts if not p["embeds"][0].get("url")]
