import unittest
from datetime import datetime, timezone

from vintage_monitor.discord import DiscordNotifier
from vintage_monitor.ebay import EbayClient
from vintage_monitor.monitor import Monitor
from vintage_monitor.store import Store

from .helpers import T0, Clock, FakeDiscord, FakeEbay, item, make_config

Q = "barbour wax jacket"


class Rig:
    """A monitor wired to fake eBay, fake Discord, an in-memory DB and a fake clock."""

    def __init__(self, config=None, store=None, clock=None, ebay=None, discord=None):
        self.config = config or make_config()
        self.clock = clock or Clock()
        self.ebay = ebay or FakeEbay()
        self.discord = discord or FakeDiscord()
        self.store = store or Store(":memory:")
        self.monitor = Monitor(
            self.config,
            EbayClient("id", "secret", self.config.settings, transport=self.ebay, now=self.clock.now),
            DiscordNotifier("https://discord.com/api/webhooks/1/x", transport=self.discord,
                            sleep=lambda s: None, clock=self.clock.now),
            self.store,
            now=self.clock.now,
            sleep=self.clock.sleep,
        )
        # What run() does at startup (tests below call check() directly).
        self.monitor._prepare_summary(self.clock.now())

    def check(self, index=0):
        self.monitor.check(self.config.searches[index])
        self.monitor.housekeeping()

    def listed_now(self, item_id, **kw):
        return item(item_id, created=self.clock.t - 60, **kw)


class SeenTest(unittest.TestCase):
    def test_first_check_is_silent_then_only_new_items_alert(self):
        rig = Rig()
        rig.ebay.results[Q] = [rig.listed_now(str(i)) for i in range(30)]
        rig.check()
        self.assertEqual(rig.discord.posts, [])  # no flood

        rig.ebay.results[Q] = [rig.listed_now("new", title="Barbour Bedale")] + rig.ebay.results[Q]
        rig.check()
        self.assertEqual(rig.discord.deal_titles(), ["Barbour Bedale"])

        rig.check()  # same results again
        self.assertEqual(len(rig.discord.deal_titles()), 1)  # no duplicate
        self.assertEqual(rig.store.get_int("summary_alerts"), 1)

    def test_alerts_come_oldest_first(self):
        rig = Rig()
        rig.check()
        rig.ebay.results[Q] = [rig.listed_now("b", title="newest"), rig.listed_now("a", title="older")]
        rig.check()
        self.assertEqual(rig.discord.deal_titles(), ["older", "newest"])

    def test_filtered_items_are_not_alerted_or_rechecked(self):
        rig = Rig()
        rig.check()
        rig.ebay.results[Q] = [
            rig.listed_now("kid", title="Barbour kids jacket"),
            rig.listed_now("dear", price="50.00"),
            rig.listed_now("auction", options=("AUCTION",)),
            rig.listed_now("ok", title="Barbour Border"),
        ]
        rig.check()
        rig.check()
        self.assertEqual(rig.discord.deal_titles(), ["Barbour Border"])
        self.assertTrue(rig.store.is_seen(rig.config.searches[0].fingerprint, "kid"))

    def test_one_alert_when_two_searches_match(self):
        config = make_config([
            {"name": "A", "query": Q},
            {"name": "B", "query": "barbour"},
        ])
        rig = Rig(config)
        rig.check(0)
        rig.check(1)
        shared = rig.listed_now("same", title="Barbour Beaufort")
        rig.ebay.results[Q] = [shared]
        rig.ebay.results["barbour"] = [shared]
        rig.check(0)
        rig.check(1)
        self.assertEqual(rig.discord.deal_titles(), ["Barbour Beaufort"])

    def test_discord_failure_retries_next_time_without_duplicates(self):
        rig = Rig()
        rig.check()
        rig.ebay.results[Q] = [rig.listed_now("x", title="Barbour X")]
        rig.discord.down = True
        rig.check()
        self.assertEqual(rig.discord.posts, [])
        self.assertIn("Discord", rig.store.get("last_error"))
        rig.discord.down = False
        rig.check()
        rig.check()
        self.assertEqual(rig.discord.deal_titles(), ["Barbour X"])

    def test_discord_down_stops_after_first_failed_alert(self):
        # Each failed send can take up to 20 s to time out; trying every new
        # listing in turn would stall the monitor for many minutes.
        rig = Rig()
        rig.check()
        rig.ebay.results[Q] = [rig.listed_now(str(i)) for i in range(5)]
        rig.discord.down = True
        rig.check()
        self.assertEqual(rig.discord.attempts, 1)
        rig.discord.down = False
        rig.check()
        self.assertEqual(len(rig.discord.deal_titles()), 5)

    def test_changed_search_is_reseeded_silently(self):
        store = Store(":memory:")
        rig = Rig(store=store)
        rig.check()
        old = [rig.listed_now(str(i)) for i in range(10)]
        changed = make_config([{"name": "Barbour wax", "query": "barbour wax coat"}])
        rig2 = Rig(changed, store=store, clock=rig.clock)
        rig2.ebay.results["barbour wax coat"] = old
        rig2.check()
        self.assertEqual(rig2.discord.posts, [])

    def test_seen_survives_restart(self):
        store = Store(":memory:")
        rig = Rig(store=store)
        rig.ebay.results[Q] = [rig.listed_now("1")]
        rig.check()
        rig2 = Rig(store=store, clock=rig.clock)
        rig2.ebay.results[Q] = [rig.listed_now("1"), rig.listed_now("2", title="Second")]
        rig2.check()
        self.assertEqual(rig2.discord.deal_titles(), ["Second"])

    def test_old_seen_records_pruned(self):
        rig = Rig()
        rig.ebay.results[Q] = [rig.listed_now("1")]
        rig.check()
        rig.store.prune(rig.clock.t + 15 * 86400)
        self.assertFalse(rig.store.is_seen(rig.config.searches[0].fingerprint, "1"))


class ProblemAlertTest(unittest.TestCase):
    def test_problem_alert_after_15_minutes_repeat_hourly_then_recovered(self):
        rig = Rig()
        rig.ebay.fail_with[Q] = (500, {"errors": [{"message": "eBay is down"}]})
        rig.check()
        rig.clock.t += 14 * 60
        rig.check()
        self.assertEqual(rig.discord.texts(), [])  # not yet

        rig.clock.t += 61
        rig.check()
        self.assertEqual(rig.discord.texts(), ["⚠️ Vintage Monitor has a problem"])
        self.assertIn("eBay is down", rig.discord.posts[0]["embeds"][0]["description"])

        rig.clock.t += 30 * 60
        rig.check()
        self.assertEqual(len(rig.discord.texts()), 1)  # no spam within the hour
        rig.clock.t += 31 * 60
        rig.check()
        self.assertEqual(len(rig.discord.texts()), 2)  # repeated after an hour

        del rig.ebay.fail_with[Q]
        rig.check()
        self.assertEqual(rig.discord.texts()[-1], "✅ Vintage Monitor recovered")
        rig.check()
        self.assertEqual(len(rig.discord.texts()), 3)

    def test_one_broken_search_is_reported_even_if_others_work(self):
        config = make_config([{"name": "Good", "query": "good"}, {"name": "Bad", "query": "bad"}])
        rig = Rig(config)
        rig.ebay.fail_with["bad"] = (400, {"errors": [{"message": "Invalid query"}]})
        for _ in range(20):
            rig.check(0)
            rig.check(1)
            rig.clock.t += 60
        texts = rig.discord.texts()
        self.assertEqual(texts, ["⚠️ Vintage Monitor has a problem"])
        self.assertIn("**Bad**", rig.discord.posts[0]["embeds"][0]["description"])
        self.assertNotIn("**Good**", rig.discord.posts[0]["embeds"][0]["description"])

    def test_bad_keys_reported(self):
        rig = Rig()
        rig.ebay.token_status = 401
        rig.check()
        rig.clock.t += 16 * 60
        rig.check()
        self.assertIn("Production App ID", rig.discord.posts[0]["embeds"][0]["description"])

    def test_rate_limit_pauses_checks(self):
        rig = Rig()
        rig.ebay.fail_with[Q] = (429, {"errors": [{"message": "limit"}]})
        start = rig.clock.t
        rig.monitor.run(max_checks=2)
        self.assertEqual(len(rig.ebay.search_calls), 2)
        # The second call waited out the 15-minute pause (not just one slot).
        self.assertGreaterEqual(rig.clock.t - start, 15 * 60)
        self.assertEqual(round(sum(rig.clock.sleeps)), 15 * 60)


class DailySummaryTest(unittest.TestCase):
    @staticmethod
    def at(hour, minute=0, day=9):
        return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc).timestamp()

    def test_sent_once_at_nine_with_counts_then_reset(self):
        rig = Rig(clock=Clock(self.at(8, 0)))
        rig.monitor.run(max_checks=1)  # startup at 08:00
        self.assertEqual(rig.discord.texts(), ["🟢 Vintage Monitor started"])
        rig.check()
        rig.clock.t = self.at(8, 59)
        rig.check()
        self.assertEqual(len(rig.discord.texts()), 1)

        rig.clock.t = self.at(9, 0)
        rig.check()
        self.assertEqual(rig.discord.texts()[-1], "✅ Vintage Monitor: still running")
        body = rig.discord.posts[-1]["embeds"][0]["description"]
        self.assertIn("**4** eBay checks", body)
        self.assertIn("**0** errors", body)

        rig.clock.t = self.at(13, 0)
        rig.check()
        self.assertEqual(len(rig.discord.texts()), 2)  # once a day
        self.assertEqual(rig.store.get_int("summary_checks"), 1)

        rig.clock.t = self.at(9, 1, day=10)
        rig.check()
        self.assertEqual(len(rig.discord.texts()), 3)

    def test_starting_after_nine_waits_until_tomorrow(self):
        rig = Rig(clock=Clock(self.at(15, 0)))
        rig.monitor.run(max_checks=1)
        rig.check()
        self.assertEqual(rig.discord.texts(), ["🟢 Vintage Monitor started"])

    def test_uses_uk_time_in_summer(self):
        # 08:30 UTC on 1 July is 09:30 in London (BST), so it's due.
        rig = Rig(clock=Clock(datetime(2026, 7, 1, 7, 0, tzinfo=timezone.utc).timestamp()))
        rig.monitor.run(max_checks=1)
        rig.clock.t = datetime(2026, 7, 1, 8, 30, tzinfo=timezone.utc).timestamp()
        rig.check()
        self.assertEqual(rig.discord.texts()[-1], "✅ Vintage Monitor: still running")


class RunLoopTest(unittest.TestCase):
    def test_searches_take_turns_evenly_spaced(self):
        config = make_config([{"name": f"S{i}", "query": f"q{i}"} for i in range(4)])
        rig = Rig(config)
        rig.monitor.run(max_checks=8)
        queries = [c[1].split("q=")[1].split("&")[0] for c in rig.ebay.search_calls]
        self.assertEqual(queries, ["q0", "q1", "q2", "q3"] * 2)
        self.assertEqual(rig.clock.sleeps, [config.slot_seconds()] * 7)
        self.assertAlmostEqual(config.slot_seconds() * 4, 77.0)

    def test_startup_message_lists_searches(self):
        rig = Rig()
        rig.monitor.run(max_checks=1)
        self.assertEqual(rig.discord.texts()[0], "🟢 Vintage Monitor started")
        self.assertIn("barbour wax jacket", rig.discord.posts[0]["embeds"][0]["description"])

    def test_keeps_running_when_discord_is_down_at_startup(self):
        rig = Rig()
        rig.discord.down = True
        rig.monitor.run(max_checks=3)
        self.assertEqual(len(rig.ebay.search_calls), 3)


if __name__ == "__main__":
    unittest.main()
