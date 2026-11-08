import base64
import json
import unittest
import urllib.parse
from decimal import Decimal

from vintage_monitor import web
from vintage_monitor.ebay import (
    EbayAuthError,
    EbayClient,
    EbayError,
    EbayRateLimitError,
    build_filter,
    parse_listing,
)

from .helpers import T0, Clock, FakeEbay, item, make_config


def client_for(config, fake, clock=None):
    clock = clock or Clock()
    return EbayClient("my-id", "my-secret", config.settings, transport=fake, now=clock.now), clock


class FilterTest(unittest.TestCase):
    def test_default_filter(self):
        config = make_config()
        self.assertEqual(
            build_filter(config.searches[0], config.settings),
            "buyingOptions:{FIXED_PRICE},conditions:{USED},itemLocationCountry:GB",
        )

    def test_price_filters(self):
        config = make_config([
            {"name": "a", "query": "a", "max_price": 25},
            {"name": "b", "query": "b", "max_price": 25, "min_price": 5},
            {"name": "c", "query": "c", "min_price": 5},
            {"name": "d", "query": "d", "condition": "any", "location": ""},
        ])
        a, b, c, d = (build_filter(s, config.settings) for s in config.searches)
        self.assertTrue(a.endswith("price:[..25.00],priceCurrency:GBP"))
        self.assertTrue(b.endswith("price:[5.00..25.00],priceCurrency:GBP"))
        self.assertNotIn("price", c.replace("FIXED_PRICE", ""))  # min-only is checked locally
        self.assertEqual(d, "buyingOptions:{FIXED_PRICE}")


class ParseTest(unittest.TestCase):
    def test_full_item(self):
        raw = item("v1|1|0", created=T0 - 60)
        raw["shippingOptions"].append(
            {"shippingCostType": "FIXED", "shippingCost": {"value": "2.50", "currency": "GBP"}}
        )
        listing = parse_listing(raw)
        self.assertEqual(listing.price, Decimal("20.00"))
        self.assertEqual(listing.shipping, Decimal("2.50"))  # cheapest option
        self.assertEqual(listing.total, Decimal("22.50"))
        self.assertEqual(listing.created_at.timestamp(), T0 - 60)
        self.assertEqual(listing.location_country, "GB")
        self.assertEqual(listing.seller_feedback_score, 120)
        self.assertFalse(hasattr(listing, "seller_username"))  # never kept

    def test_missing_shipping_and_free(self):
        unknown = parse_listing(item("a", shipping=None))
        self.assertIsNone(unknown.shipping)
        self.assertEqual(unknown.total, Decimal("20.00"))
        calculated = item("b", shipping=None)
        calculated["shippingOptions"] = [{"shippingCostType": "CALCULATED"}]
        self.assertIsNone(parse_listing(calculated).shipping)
        free = parse_listing(item("c", shipping="0.00"))
        self.assertEqual(free.shipping, Decimal("0.00"))

    def test_unusable_items_skipped(self):
        self.assertIsNone(parse_listing({"title": "x"}))
        self.assertIsNone(parse_listing("nonsense"))
        no_price = item("a")
        del no_price["price"]
        self.assertIsNone(parse_listing(no_price).price)
        bad_date = item("a")
        bad_date["itemCreationDate"] = "yesterday"
        self.assertIsNone(parse_listing(bad_date).created_at)

    def test_title_whitespace_collapsed(self):
        self.assertEqual(parse_listing(item("a", title="  Barbour \n  jacket ")).title, "Barbour jacket")


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.config = make_config()
        self.search = self.config.searches[0]
        self.fake = FakeEbay()
        self.fake.results["barbour wax jacket"] = [item("1"), item("2")]
        self.client, self.clock = client_for(self.config, self.fake)

    def test_login_and_search_request(self):
        listings = self.client.search(self.search)
        self.assertEqual([l.item_id for l in listings], ["1", "2"])

        method, url, headers = self.fake.calls[0]
        self.assertEqual(method, "POST")
        expected = base64.b64encode(b"my-id:my-secret").decode()
        self.assertEqual(headers["Authorization"], f"Basic {expected}")

        method, url, headers = self.fake.calls[1]
        self.assertEqual(method, "GET")
        self.assertEqual(headers["Authorization"], "Bearer tok1")
        self.assertEqual(headers["X-EBAY-C-MARKETPLACE-ID"], "EBAY_GB")
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(params["q"], ["barbour wax jacket"])
        self.assertEqual(params["sort"], ["newlyListed"])
        self.assertEqual(params["limit"], ["50"])
        self.assertEqual(
            params["filter"], ["buyingOptions:{FIXED_PRICE},conditions:{USED},itemLocationCountry:GB"]
        )

    def test_token_reused_then_renewed_before_expiry(self):
        self.client.search(self.search)
        self.client.search(self.search)
        self.assertEqual(self.fake.token_counter, 1)
        self.clock.t += 7200 - 299  # inside the 5-minute safety margin
        self.client.search(self.search)
        self.assertEqual(self.fake.token_counter, 2)

    def test_expired_token_relogin_once(self):
        self.client.search(self.search)
        self.fake.expire_next_search = True
        listings = self.client.search(self.search)
        self.assertEqual(len(listings), 2)
        self.assertEqual(self.fake.token_counter, 2)

    def test_bad_keys(self):
        self.fake.token_status = 401
        with self.assertRaisesRegex(EbayAuthError, "Production App ID"):
            self.client.search(self.search)

    def test_rate_limited(self):
        self.fake.fail_with["barbour wax jacket"] = (429, {"errors": [{"message": "Too many"}]})
        with self.assertRaises(EbayRateLimitError):
            self.client.search(self.search)

    def test_error_message_from_ebay(self):
        self.fake.fail_with["barbour wax jacket"] = (
            400,
            {"errors": [{"message": "short", "longMessage": "The filter value is invalid."}]},
        )
        with self.assertRaisesRegex(EbayError, "The filter value is invalid"):
            self.client.search(self.search)

    def test_network_error(self):
        def broken(*a, **k):
            raise web.NetworkError("Name or service not known")

        client, _ = client_for(self.config, broken)
        with self.assertRaisesRegex(EbayError, "Couldn't reach eBay"):
            client.search(self.search)

    def test_invalid_json(self):
        def garbage(method, url, headers=None, body=None, timeout=20):
            if "oauth2" in url:
                return web.Response(200, json.dumps({"access_token": "t"}).encode())
            return web.Response(200, b"<html>")

        client, _ = client_for(self.config, garbage)
        with self.assertRaisesRegex(EbayError, "invalid data"):
            client.search(self.search)

    def test_no_results(self):
        self.fake.results["barbour wax jacket"] = []
        self.assertEqual(self.client.search(self.search), [])


if __name__ == "__main__":
    unittest.main()
