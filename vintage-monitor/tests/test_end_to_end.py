"""End to end: the real commands, real HTTP (urllib) and a real database file,
against local fake eBay and Discord servers. Nothing leaves this machine."""

import base64
import contextlib
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from vintage_monitor import cli

from .helpers import item

CLIENT_ID = "Max-Vintage-PRD-0123456789-abcdef"
CLIENT_SECRET = "PRD-secret-value"


class FakeServers:
    def __init__(self):
        self.items: dict[str, list] = {}
        self.discord_posts: list[dict] = []
        self.user_agents: set[str] = set()
        self.search_headers: list[dict] = []
        state = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, payload=None):
                body = b"" if payload is None else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                state.user_agents.add(self.headers.get("User-Agent", ""))
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                if self.path == "/identity/v1/oauth2/token":
                    expected = "Basic " + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
                    form = urllib.parse.parse_qs(body.decode())
                    if self.headers.get("Authorization") != expected:
                        return self._send(401, {"error": "invalid_client",
                                                "error_description": "client authentication failed"})
                    assert form["grant_type"] == ["client_credentials"], form
                    assert form["scope"] == ["https://api.ebay.com/oauth/api_scope"], form
                    return self._send(200, {"access_token": "real-token", "expires_in": 7200})
                if self.path.startswith("/api/webhooks/"):
                    state.discord_posts.append(json.loads(body))
                    return self._send(204)
                return self._send(404)

            def do_GET(self):
                state.user_agents.add(self.headers.get("User-Agent", ""))
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != "/buy/browse/v1/item_summary/search":
                    return self._send(404)
                if self.headers.get("Authorization") != "Bearer real-token":
                    return self._send(401, {"errors": [{"message": "Invalid access token"}]})
                state.search_headers.append({k.lower(): v for k, v in self.headers.items()})
                q = urllib.parse.parse_qs(parsed.query)["q"][0]
                items = state.items.get(q, [])
                return self._send(200, {"total": len(items), "itemSummaries": items})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.servers = FakeServers()
        self.addCleanup(self.servers.close)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.config = self.dir / "config.toml"
        self.config.write_text(
            '[defaults]\nexclude = ["kids"]\n\n'
            '[[search]]\nname = "Barbour wax"\nquery = "barbour wax jacket"\nmax_total = 30\n'
        )
        self.env = self.dir / ".env"
        self.webhook = f"{self.servers.base}/api/webhooks/1/abc"
        self.write_env(CLIENT_SECRET)
        self.db = self.dir / "data" / "monitor.db"
        for target, value in (
            ("vintage_monitor.ebay.TOKEN_URL", f"{self.servers.base}/identity/v1/oauth2/token"),
            ("vintage_monitor.ebay.SEARCH_URL", f"{self.servers.base}/buy/browse/v1/item_summary/search"),
            ("vintage_monitor.config.WEBHOOK_PREFIXES", (f"{self.servers.base}/api/webhooks/",)),
        ):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_env(self, secret):
        self.env.write_text(
            f"EBAY_CLIENT_ID={CLIENT_ID}\nEBAY_CLIENT_SECRET={secret}\nDISCORD_WEBHOOK_URL={self.webhook}\n"
        )

    def cli(self, *args):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main([args[0], "--config", str(self.config), "--env", str(self.env),
                             "--db", str(self.db), *args[1:]])
        return code, out.getvalue() + err.getvalue()

    def fresh(self, item_id, **kw):
        return item(item_id, created=time.time() - 120, **kw)

    def test_full_flow(self):
        code, out = self.cli("validate")
        self.assertEqual(code, 0, out)
        self.assertIn("Config OK: 1 searches", out)

        code, out = self.cli("test-alert")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.servers.discord_posts), 2)
        self.assertTrue(self.servers.discord_posts[1]["embeds"][0]["title"].startswith("TEST: "))

        q = "barbour wax jacket"
        self.servers.items[q] = [
            self.fresh("1", title="Barbour Bedale", price="18.00", shipping="4.00"),
            self.fresh("2", title="Barbour kids jacket"),
            self.fresh("3", title="Barbour Beaufort", price="40.00"),
        ]
        code, out = self.cli("check")
        self.assertEqual(code, 0, out)
        self.assertIn("3 listings returned; 1 pass your filters", out)
        self.assertIn('skip: excluded word "kids"', out)
        self.assertIn("above max_total", out)
        headers = self.servers.search_headers[-1]
        self.assertEqual(headers.get("x-ebay-c-marketplace-id"), "EBAY_GB")

        # First run: startup message, current listings recorded silently.
        self.servers.discord_posts.clear()
        code, out = self.cli("run", "--max-checks", "1")
        self.assertEqual(code, 0, out)
        self.assertEqual([p["content"] for p in self.servers.discord_posts], ["🟢 Vintage Monitor started"])
        self.assertTrue(self.db.exists())

        # Restart with a new listing: exactly one deal alert.
        self.servers.items[q].insert(0, self.fresh("4", title="Barbour Border", price="15.00", shipping="3.50"))
        self.servers.discord_posts.clear()
        code, out = self.cli("run", "--max-checks", "1")
        self.assertEqual(code, 0, out)
        deals = [p for p in self.servers.discord_posts if p["embeds"][0].get("url")]
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0]["embeds"][0]["title"], "Barbour Border")
        self.assertTrue(deals[0]["content"].startswith("£18.50"))

        code, out = self.cli("status")
        self.assertIn("Last alert:", out)
        self.assertIn("Looks healthy", out)
        self.assertEqual(code, 0, out)

        # Every request identified itself (Discord blocks Python's default agent).
        self.assertTrue(all(ua.startswith("VintageMonitor/") for ua in self.servers.user_agents),
                        self.servers.user_agents)

    def test_wrong_keys_are_explained(self):
        self.write_env("wrong-secret")
        code, out = self.cli("check")
        self.assertEqual(code, 1)
        self.assertIn("eBay rejected the keys", out)

    def test_broken_config_is_refused(self):
        self.config.write_text('[[search]]\nname = "X"\nquery = "x"\nmax_prise = 10\n')
        code, out = self.cli("validate")
        self.assertEqual(code, 2)
        self.assertIn("max_prise", out)

    def test_status_before_first_run(self):
        code, out = self.cli("status")
        self.assertEqual(code, 1)
        self.assertIn("never run", out)


if __name__ == "__main__":
    unittest.main()
