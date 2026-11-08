import json
import unittest

from vintage_monitor import web
from vintage_monitor.discord import (
    DiscordError,
    DiscordNotifier,
    escape,
    listing_payload,
    text_payload,
)
from vintage_monitor.ebay import parse_listing

from .helpers import T0, Clock, FakeDiscord, item

URL = "https://discord.com/api/webhooks/1/x"


def notifier(fake, clock=None):
    clock = clock or Clock()
    return DiscordNotifier(URL, transport=fake, sleep=clock.sleep, clock=clock.now), clock


class PayloadTest(unittest.TestCase):
    def test_listing_payload(self):
        listing = parse_listing(item("1", price="20.00", shipping="4.49", created=T0 - 180))
        p = listing_payload(listing, "Barbour wax", T0)
        self.assertTrue(p["content"].startswith("£24.49 · Barbour Beaufort"))
        self.assertEqual(p["allowed_mentions"], {"parse": []})
        embed = p["embeds"][0]
        self.assertEqual(embed["url"], "https://www.ebay.co.uk/itm/1")
        self.assertEqual(embed["image"]["url"], "https://i.ebayimg.com/1.jpg")
        fields = {f["name"]: f["value"] for f in embed["fields"]}
        self.assertEqual(fields["Price"], "£20.00")
        self.assertEqual(fields["Postage"], "£4.49")
        self.assertEqual(fields["Total"], "£24.49")
        self.assertEqual(fields["Listed"], "3 min ago")
        self.assertEqual(fields["Search"], "Barbour wax")
        self.assertEqual(fields["Seller feedback"], "99.5% (120)")
        self.assertNotIn("someone", json.dumps(p))  # seller username never sent
        self.assertLessEqual(len(json.dumps(p)), 6000)

    def test_unknown_and_free_postage(self):
        unknown = listing_payload(parse_listing(item("1", shipping=None)), "S", T0)
        fields = {f["name"]: f["value"] for f in unknown["embeds"][0]["fields"]}
        self.assertEqual(fields["Postage"], "unknown")
        self.assertEqual(fields["Total"], "£20.00 + postage?")
        free = listing_payload(parse_listing(item("1", shipping="0")), "S", T0)
        fields = {f["name"]: f["value"] for f in free["embeds"][0]["fields"]}
        self.assertEqual(fields["Postage"], "free")

    def test_offers_and_long_titles(self):
        raw = item("1", title="x" * 400, options=("FIXED_PRICE", "BEST_OFFER"))
        p = listing_payload(parse_listing(raw), "S", T0, test=True)
        self.assertEqual(len(p["embeds"][0]["title"]), 256)
        self.assertTrue(p["embeds"][0]["title"].startswith("TEST: "))
        self.assertIn("accepts offers", json.dumps(p))

    def test_titles_cannot_fake_links_or_ping(self):
        self.assertEqual(escape("[click](http://evil)"), "\\[click\\](http://evil)")
        p = listing_payload(parse_listing(item("1", title="@everyone **FREE**")), "S", T0)
        self.assertIn("\\*\\*FREE\\*\\*", p["content"])
        self.assertEqual(p["allowed_mentions"], {"parse": []})

    def test_text_payload(self):
        p = text_payload("Title", "Body")
        self.assertEqual(p["content"], "Title")
        self.assertEqual(p["embeds"][0]["description"], "Body")


class SendTest(unittest.TestCase):
    def test_success(self):
        fake = FakeDiscord()
        n, _ = notifier(fake)
        n.send(text_payload("hi", "there"))
        self.assertEqual(fake.posts[0]["content"], "hi")

    def test_rate_limit_waits_and_retries(self):
        fake = FakeDiscord()
        fake.responses = [web.Response(429, json.dumps({"retry_after": 1.5}).encode())]
        n, clock = notifier(fake)
        n.send(text_payload("hi", "there"))
        self.assertEqual(len(fake.posts), 1)
        self.assertIn(1.5, clock.sleeps)

    def test_deleted_webhook(self):
        fake = FakeDiscord()
        fake.responses = [web.Response(404, b'{"message": "Unknown Webhook"}')]
        n, _ = notifier(fake)
        with self.assertRaisesRegex(DiscordError, "deleted"):
            n.send(text_payload("hi", "there"))

    def test_server_errors_retry_then_give_up(self):
        fake = FakeDiscord()
        fake.responses = [web.Response(502)] * 4
        n, _ = notifier(fake)
        with self.assertRaises(DiscordError):
            n.send(text_payload("hi", "there"))
        self.assertEqual(fake.responses, [])  # tried 4 times

    def test_network_error(self):
        fake = FakeDiscord()
        fake.down = True
        n, _ = notifier(fake)
        with self.assertRaisesRegex(DiscordError, "Couldn't reach Discord"):
            n.send(text_payload("hi", "there"))

    def test_messages_are_spaced_out(self):
        fake = FakeDiscord()
        n, clock = notifier(fake)
        for _ in range(3):
            n.send(text_payload("hi", "there"))
        self.assertEqual(clock.sleeps, [0.6, 0.6])


if __name__ == "__main__":
    unittest.main()
