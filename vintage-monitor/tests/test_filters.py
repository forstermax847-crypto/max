import unittest

from vintage_monitor.ebay import parse_listing
from vintage_monitor.filters import excluded_word, rejection_reason

from .helpers import T0, item, make_config


def reason(raw, **search):
    config = make_config([{"name": "S", "query": "q", **search}])
    return rejection_reason(config.searches[0], parse_listing(raw), config.settings, T0)


class ExcludeTest(unittest.TestCase):
    def test_whole_words_only(self):
        ex = ("kids", "boys", "hood only", "children's")
        self.assertEqual(excluded_word("Barbour KIDS' wax jacket", ex), "kids")
        self.assertEqual(excluded_word("Barbour jacket (kids)", ex), "kids")
        self.assertIsNone(excluded_word("Barbour boyfriend fit jacket", ex))
        self.assertIsNone(excluded_word("Barbour jacket with hood", ex))
        self.assertEqual(excluded_word("Barbour hood only, olive", ex), "hood only")
        self.assertEqual(excluded_word("Patagonia Children's fleece", ex), "children's")

    def test_good_listings_not_hidden(self):
        # The traps called out in PLAN.md.
        config = make_config([{"name": "B", "query": "barbour", "exclude": ["style", "dressing", "hood only"]}])
        ex = config.searches[0].exclude
        self.assertIsNone(excluded_word("Barbour Bedale wax jacket tartan lining", ex))
        self.assertIsNone(excluded_word("Barbour Beaufort recently rewaxed", ex))
        self.assertEqual(excluded_word("Barbour style wax jacket", ex), "style")


class RejectionTest(unittest.TestCase):
    def test_good_listing_alerts(self):
        self.assertIsNone(reason(item("a", created=T0 - 300), max_total=30))

    def test_buy_it_now_only(self):
        self.assertEqual(reason(item("a", options=("AUCTION",))), "not Buy It Now")
        self.assertIn("auction", reason(item("a", options=("AUCTION", "FIXED_PRICE"))))
        self.assertIsNone(reason(item("a", options=("FIXED_PRICE", "BEST_OFFER"))))

    def test_excluded_words_from_defaults(self):
        self.assertIn("kids", reason(item("a", title="Barbour kids jacket")))

    def test_max_total_includes_postage(self):
        self.assertIsNone(reason(item("a", price="20", shipping="10"), max_total=30))
        self.assertIn("above max_total", reason(item("a", price="20", shipping="10.01"), max_total=30))
        # Unknown postage: judged on price alone (the alert says postage unknown).
        self.assertIsNone(reason(item("a", price="29", shipping=None), max_total=30))

    def test_min_and_max_price(self):
        self.assertIn("below min_price", reason(item("a", price="4.99"), min_price=5))
        self.assertIn("above max_price", reason(item("a", price="26"), max_price=25))

    def test_age(self):
        self.assertIsNone(reason(item("a", created=T0 - 119 * 60)))
        self.assertIn("minutes ago", reason(item("a", created=T0 - 121 * 60)))
        self.assertIsNone(reason(item("a", created=None)))  # no date: allow

    def test_location_and_currency(self):
        self.assertIn("located in DE", reason(item("a", country="DE")))
        self.assertIsNone(reason(item("a", country="DE"), location=""))
        raw = item("a")
        raw["price"]["currency"] = "EUR"
        self.assertIn("EUR", reason(raw))

    def test_no_price(self):
        raw = item("a")
        del raw["price"]
        self.assertEqual(reason(raw), "no price given")


if __name__ == "__main__":
    unittest.main()
