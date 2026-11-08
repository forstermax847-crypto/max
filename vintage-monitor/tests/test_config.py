import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from vintage_monitor.config import ConfigError, load_config, load_secrets, parse_config, read_env_file

from .helpers import make_config

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"
WEBHOOK = "https://discord.com/api/webhooks/123/abc"


def base(**search):
    s = {"name": "A", "query": "barbour wax jacket", **search}
    return {"search": [s]}


class RepoConfigTest(unittest.TestCase):
    # Only checks the config is valid. It must NOT pin which searches exist:
    # update.sh runs these tests, so pinning them would block every change
    # Max makes to his searches.
    def test_repo_config_is_valid(self):
        config = load_config(REPO_CONFIG)
        self.assertGreaterEqual(len(config.searches), 1)

    def test_four_searches_take_77_seconds(self):
        # The figure quoted in PLAN.md section 3.
        four = make_config([{"name": f"S{i}", "query": f"q{i}"} for i in range(4)])
        self.assertEqual(four.cycle_seconds(), 77.0)


class ParseTest(unittest.TestCase):
    def test_typo_in_key_is_an_error(self):
        with self.assertRaisesRegex(ConfigError, "max_prise"):
            parse_config(base(max_prise=10))
        with self.assertRaisesRegex(ConfigError, "daily_budget"):
            parse_config({"settings": {"daily_budget": 10}, **base()})
        with self.assertRaisesRegex(ConfigError, "searches"):
            parse_config({"searches": [], **base()})

    def test_types(self):
        with self.assertRaisesRegex(ConfigError, "number"):
            parse_config(base(max_total="30"))
        with self.assertRaisesRegex(ConfigError, "number"):
            parse_config(base(max_total=True))
        with self.assertRaisesRegex(ConfigError, "whole number"):
            parse_config({"settings": {"daily_call_budget": True}, **base()})
        with self.assertRaisesRegex(ConfigError, "negative"):
            parse_config(base(max_total=-1))

    def test_money_is_exact(self):
        config = parse_config(base(max_total=29.99, min_price=5))
        self.assertEqual(config.searches[0].max_total, Decimal("29.99"))
        self.assertEqual(config.searches[0].min_price, Decimal("5.00"))

    def test_needs_searches_name_and_query(self):
        with self.assertRaisesRegex(ConfigError, "at least one"):
            parse_config({})
        with self.assertRaisesRegex(ConfigError, "needs a name"):
            parse_config({"search": [{"query": "x"}]})
        with self.assertRaisesRegex(ConfigError, "needs a query"):
            parse_config({"search": [{"name": "x"}]})
        with self.assertRaisesRegex(ConfigError, "empty query"):
            parse_config(base(query="   "))

    def test_duplicates(self):
        with self.assertRaisesRegex(ConfigError, "both called"):
            parse_config({"search": [{"name": "A", "query": "x"}, {"name": "a", "query": "y"}]})
        with self.assertRaisesRegex(ConfigError, "exactly the same"):
            parse_config({"search": [{"name": "A", "query": "x y"}, {"name": "B", "query": "X  Y"}]})

    def test_price_order(self):
        with self.assertRaisesRegex(ConfigError, "above max_price"):
            parse_config(base(min_price=50, max_price=10))
        with self.assertRaisesRegex(ConfigError, "above max_total"):
            parse_config(base(min_price=50, max_total=10))

    def test_query_length(self):
        with self.assertRaisesRegex(ConfigError, "eBay allows 100"):
            parse_config(base(query="a" * 101))
        parse_config(base(query="a" * 100))

    def test_exclude_merges_with_defaults(self):
        config = parse_config(
            {"defaults": {"exclude": ["Kids", "replica"]}, **base(exclude=["style", "kids"])}
        )
        self.assertEqual(config.searches[0].exclude, ("kids", "replica", "style"))

    def test_location_and_condition(self):
        config = parse_config(base(location="", condition="Any"))
        self.assertIsNone(config.searches[0].location)
        self.assertEqual(config.searches[0].condition, "any")
        with self.assertRaisesRegex(ConfigError, "two-letter"):
            parse_config(base(location="UK!"))
        with self.assertRaisesRegex(ConfigError, "one of"):
            parse_config(base(condition="vintage"))

    def test_settings_validation(self):
        with self.assertRaisesRegex(ConfigError, "unknown"):
            parse_config({"settings": {"timezone": "Mars/Base"}, **base()})
        with self.assertRaisesRegex(ConfigError, "09:00"):
            parse_config({"settings": {"daily_summary_time": "9am"}, **base()})
        with self.assertRaisesRegex(ConfigError, "between 1 and 5000"):
            parse_config({"settings": {"daily_call_budget": 45000}, **base()})
        config = parse_config({"settings": {"daily_summary_time": "8:05"}, **base()})
        self.assertEqual(config.settings.summary_hour_minute, (8, 5))

    def test_fingerprint(self):
        a = parse_config(base()).searches[0]
        same_api = parse_config(base(max_total=10, exclude=["x"], name="Renamed")).searches[0]
        changed = parse_config(base(query="barbour wax coat")).searches[0]
        price_changed = parse_config(base(max_price=40)).searches[0]
        self.assertEqual(a.fingerprint, same_api.fingerprint)
        self.assertNotEqual(a.fingerprint, changed.fingerprint)
        self.assertNotEqual(a.fingerprint, price_changed.fingerprint)

    def test_cycle_maths(self):
        one = make_config()
        self.assertEqual(one.cycle_seconds(), 60.0)  # min_interval wins
        ten = make_config([{"name": f"S{i}", "query": f"q{i}"} for i in range(10)])
        self.assertEqual(ten.cycle_seconds(), 192.0)
        self.assertAlmostEqual(ten.slot_seconds(), 19.2)
        # Whatever the number of searches, calls/day stay within budget.
        for n in range(1, 30):
            c = make_config([{"name": f"S{i}", "query": f"q{i}"} for i in range(n)])
            self.assertLessEqual(86400 / c.slot_seconds(), c.settings.daily_call_budget)


class SecretsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET", "DISCORD_WEBHOOK_URL"):
            os.environ.pop(key, None)

    def env(self, text: str) -> str:
        path = Path(self.dir.name) / ".env"
        path.write_text(text)
        return str(path)

    def test_reads_values(self):
        path = self.env(
            "# comment\n\nEBAY_CLIENT_ID=Me-App-PRD-123\n"
            "EBAY_CLIENT_SECRET='PRD-secret'\nexport DISCORD_WEBHOOK_URL=\"" + WEBHOOK + "\"\n"
        )
        s = load_secrets(path)
        self.assertEqual(s.ebay_client_id, "Me-App-PRD-123")
        self.assertEqual(s.ebay_client_secret, "PRD-secret")
        self.assertEqual(s.discord_webhook_url, WEBHOOK)

    def test_placeholders_count_as_missing(self):
        template = Path(__file__).resolve().parent.parent / ".env.example"
        with self.assertRaisesRegex(ConfigError, "EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, DISCORD_WEBHOOK_URL"):
            load_secrets(str(template))

    def test_partial_needs(self):
        path = self.env(f"DISCORD_WEBHOOK_URL={WEBHOOK}\nEBAY_CLIENT_ID=PASTE_X\n")
        s = load_secrets(path, need_ebay=False)
        self.assertEqual(s.discord_webhook_url, WEBHOOK)
        self.assertIsNone(s.ebay_client_id)
        with self.assertRaisesRegex(ConfigError, "EBAY_CLIENT_ID"):
            load_secrets(path)

    def test_sandbox_key_rejected(self):
        path = self.env(f"EBAY_CLIENT_ID=Me-App-SBX-1\nEBAY_CLIENT_SECRET=x\nDISCORD_WEBHOOK_URL={WEBHOOK}\n")
        with self.assertRaisesRegex(ConfigError, "Sandbox"):
            load_secrets(path)

    def test_bad_webhook_rejected(self):
        path = self.env("EBAY_CLIENT_ID=a\nEBAY_CLIENT_SECRET=b\nDISCORD_WEBHOOK_URL=https://example.com/x\n")
        with self.assertRaisesRegex(ConfigError, "Discord webhook"):
            load_secrets(path)

    def test_environment_overrides_file(self):
        path = self.env("EBAY_CLIENT_ID=a\nEBAY_CLIENT_SECRET=b\nDISCORD_WEBHOOK_URL=bad\n")
        os.environ["DISCORD_WEBHOOK_URL"] = WEBHOOK
        self.assertEqual(load_secrets(path).discord_webhook_url, WEBHOOK)

    def test_errors(self):
        with self.assertRaisesRegex(ConfigError, "not found"):
            read_env_file(Path(self.dir.name) / "missing")
        with self.assertRaisesRegex(ConfigError, "line 1"):
            read_env_file(self.env("just words\n"))


if __name__ == "__main__":
    unittest.main()
