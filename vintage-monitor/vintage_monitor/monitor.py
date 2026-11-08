"""The main loop: check each search in turn, alert on new matching listings,
report problems, and send a daily still-alive message."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable, Optional

from .config import Config, Search
from .discord import (
    COLOUR_OK,
    COLOUR_PROBLEM,
    DiscordError,
    DiscordNotifier,
    listing_payload,
    text_payload,
)
from .ebay import EbayClient, EbayError, EbayRateLimitError
from .filters import rejection_reason
from .store import Store

log = logging.getLogger("vintage_monitor")

RATE_LIMIT_PAUSE_SECONDS = 15 * 60
PRUNE_EVERY_SECONDS = 24 * 3600


def fmt_seconds(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 120:
        return f"{seconds} seconds"
    minutes = seconds / 60
    if minutes < 120:
        return f"{minutes:.0f} minutes"
    return f"{minutes / 60:.1f} hours"


class Monitor:
    def __init__(
        self,
        config: Config,
        ebay: EbayClient,
        notifier: DiscordNotifier,
        store: Store,
        now: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self.settings = config.settings
        self.ebay = ebay
        self.notifier = notifier
        self.store = store
        self.now = now
        self.sleep = sleep
        self.by_fp = {s.fingerprint: s for s in config.searches}
        self.failing_since: dict[str, float] = {}
        self.failure_text: dict[str, str] = {}
        self.pause_until = 0.0
        self.last_prune = 0.0

    # ------------------------------------------------------------------ run

    def run(self, max_checks: Optional[int] = None) -> None:
        now = self.now()
        self.store.prune(now)
        self.last_prune = now
        self._prepare_summary(now)
        self._send_startup()
        slot = self.config.slot_seconds()
        n = len(self.config.searches)
        i = 0
        while max_checks is None or i < max_checks:
            wait = self.pause_until - self.now()
            if wait > 0:
                log.warning("Pausing %s because eBay is rate-limiting.", fmt_seconds(wait))
                self.sleep(wait)
            started = self.now()
            self.check(self.config.searches[i % n])
            self.housekeeping()
            i += 1
            if max_checks is not None and i >= max_checks:
                break
            self.sleep(max(0.0, slot - (self.now() - started)))

    # ---------------------------------------------------------------- check

    def check(self, search: Search) -> None:
        now = self.now()
        self.store.set("last_check_at", now)
        try:
            listings = self.ebay.search(search)
        except EbayError as exc:
            self._record_failure(search, exc, now)
            return
        self._record_success(search, now)

        fp = search.fingerprint
        if not self.store.is_seeded(fp):
            self.store.mark_seeded(fp, [l.item_id for l in listings], now)
            log.info(
                'New search "%s": recorded %d current listings silently; '
                "alerts start with the next new listing.",
                search.name,
                len(listings),
            )
            return

        new = [l for l in listings if not self.store.is_seen(fp, l.item_id)]
        # eBay gives newest first; alert oldest first so Discord reads in order.
        for listing in reversed(new):
            reason = rejection_reason(search, listing, self.settings, now)
            if reason is None and self.store.was_alerted(listing.item_id):
                reason = "already alerted by another search"
            if reason:
                self.store.mark_seen(fp, listing.item_id, now)
                log.debug("Skip %s (%s): %s", listing.item_id, reason, listing.title)
                continue
            try:
                self.notifier.send(listing_payload(listing, search.name, now))
            except DiscordError as exc:
                # Leave this and the rest unseen so they're retried next time.
                log.error("Couldn't send alert: %s", exc)
                self.store.increment("summary_errors")
                self.store.set("last_error", f"Discord: {exc}")
                self.store.set("last_error_at", now)
                break
            self.store.mark_alerted(fp, listing.item_id, now)
            self.store.increment("summary_alerts")
            self.store.set("last_alert_at", now)
            log.info('Alert [%s] %s %s', search.name, listing.total, listing.title)

    def _record_failure(self, search: Search, exc: EbayError, now: float) -> None:
        fp = search.fingerprint
        self.failing_since.setdefault(fp, now)
        self.failure_text[fp] = str(exc)
        self.store.increment("summary_errors")
        self.store.set("last_error", str(exc))
        self.store.set("last_error_at", now)
        log.warning("%s", exc)
        if isinstance(exc, EbayRateLimitError):
            self.pause_until = now + RATE_LIMIT_PAUSE_SECONDS

    def _record_success(self, search: Search, now: float) -> None:
        self.failing_since.pop(search.fingerprint, None)
        self.failure_text.pop(search.fingerprint, None)
        self.store.set("last_success_at", now)
        self.store.increment("summary_checks")

    # --------------------------------------------------------- housekeeping

    def housekeeping(self) -> None:
        now = self.now()
        self._problem_alerts(now)
        self._daily_summary(now)
        if now - self.last_prune >= PRUNE_EVERY_SECONDS:
            self.store.prune(now)
            self.last_prune = now

    def _send(self, payload: dict) -> bool:
        try:
            self.notifier.send(payload)
            return True
        except DiscordError as exc:
            log.error("Couldn't send message to Discord: %s", exc)
            self.store.set("last_error", f"Discord: {exc}")
            self.store.set("last_error_at", self.now())
            return False

    def _problem_alerts(self, now: float) -> None:
        threshold = self.settings.problem_alert_after_minutes * 60
        stuck = {fp: t for fp, t in self.failing_since.items() if now - t >= threshold}
        sent_at = self.store.get_float("problem_alert_sent_at")
        if stuck:
            if sent_at is not None and now - sent_at < self.settings.problem_alert_repeat_minutes * 60:
                return
            lines = []
            for fp, since in stuck.items():
                name = self.by_fp[fp].name if fp in self.by_fp else fp
                lines.append(
                    f'**{name}**: failing for {fmt_seconds(now - since)}\n{self.failure_text.get(fp, "")}'
                )
            if self._send(
                text_payload(
                    "⚠️ Vintage Monitor has a problem",
                    "\n\n".join(lines)
                    + "\n\nNo deal alerts are coming from the searches above until this is fixed.",
                    COLOUR_PROBLEM,
                )
            ):
                self.store.set("problem_alert_sent_at", now)
                self.store.set("problem_active", "1")
        elif not self.failing_since and self.store.get("problem_active") == "1":
            if self._send(text_payload("✅ Vintage Monitor recovered", "All searches are working again.")):
                self.store.set("problem_active", None)
                self.store.set("problem_alert_sent_at", None)

    def _summary_due(self, now: float) -> tuple[bool, str]:
        local = datetime.fromtimestamp(now, self.settings.tz)
        today = local.date().isoformat()
        due = (local.hour, local.minute) >= self.settings.summary_hour_minute
        return due and self.store.get("summary_date") != today, today

    def _prepare_summary(self, now: float) -> None:
        # Starting after today's summary time: the startup message stands in
        # for today's summary, so don't send a second one straight away.
        due, today = self._summary_due(now)
        if due:
            self.store.set("summary_date", today)
        if self.store.get_float("summary_since") is None:
            self.store.set("summary_since", now)

    def _daily_summary(self, now: float) -> None:
        due, today = self._summary_due(now)
        if not due:
            return
        since = self.store.get_float("summary_since") or now
        since_text = datetime.fromtimestamp(since, self.settings.tz).strftime("%a %d %b %H:%M")
        checks = self.store.get_int("summary_checks")
        alerts = self.store.get_int("summary_alerts")
        errors = self.store.get_int("summary_errors")
        body = (
            f"Since {since_text}: **{checks}** eBay checks, **{alerts}** alerts, "
            f"**{errors}** errors.\n"
            f"Watching {len(self.config.searches)} searches, each about every "
            f"{fmt_seconds(self.config.cycle_seconds())}."
        )
        if self.failing_since:
            names = ", ".join(self.by_fp[fp].name for fp in self.failing_since if fp in self.by_fp)
            body += f"\n⚠️ Currently failing: {names}"
        if self._send(text_payload("✅ Vintage Monitor: still running", body, COLOUR_OK)):
            self.store.set("summary_date", today)
            self.store.set("summary_since", now)
            for key in ("summary_checks", "summary_alerts", "summary_errors"):
                self.store.set(key, 0)

    def _send_startup(self) -> None:
        lines = [f"• **{s.name}**: `{s.query}`" for s in self.config.searches]
        body = (
            f"Watching {len(self.config.searches)} searches, each about every "
            f"{fmt_seconds(self.config.cycle_seconds())}:\n" + "\n".join(lines) + "\n\n"
            "New or changed searches are recorded silently first, so alerts only "
            "come for listings that appear from now on."
        )
        self._send(text_payload("🟢 Vintage Monitor started", body, COLOUR_OK))
