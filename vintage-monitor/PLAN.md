# Vintage Monitor — Build Plan

Status: **planned, not started.** Nothing gets built until Max says go.
Last updated: 2026-11-08

This file is the single source of truth for the project. A new Claude session
has no memory of earlier conversations. Start any session on this project by
reading this file, and update it whenever a decision changes.

---

## 1. What we are building

A bot that runs 24/7 on your **old MacBook**, watches **eBay UK** for new listings
matching saved searches, and sends an alert to your phone within about a minute
of a matching item being listed, so you can buy underpriced vintage items
before other people do and resell them.

It is for **one user (you)**. It is not a product for other people, and I won't
build accounts, payments or a website for it.

## 2. Decisions already made

| Decision | Choice | Why |
|---|---|---|
| Marketplace | **eBay UK first** | Official API: legal, stable, unlikely to break or get you banned. |
| Depop | **Deferred to Phase 5** | Depop has no public API and its terms forbid scraping. A Depop monitor is fragile and could get your account banned. We'll add it only once eBay is making money, and only if you accept that risk. |
| Alerts | **Discord only** (decided 2026-11-08) | Push notifications come from the Discord app on your phone/iPad. Telegram and ntfy are dropped from v1: fewer moving parts, fewer things to break. |
| Listing format | **Buy It Now only** (decided 2026-11-08) | A newly listed auction says nothing about its final price. Fixed in code, not a setting. |
| Alert hours | **24/7** (decided 2026-11-08) | No quiet hours built in. If you ever want silence at night, use the phone's Focus / Do Not Disturb, which needs no code. |
| Hosting | **Max's old, unused MacBook** (decided 2026-11-08), staying on macOS | It has to run 24/7, and a Claude cloud session shuts down when idle. A MacBook costs about £1–1.50/month in electricity, and its battery carries it through short power cuts. Fallback if it turns out unsuitable (§4): a rented server, about £5/month. **The iPad can't be the server**; it can receive the alerts. |
| Users | Just you | Keeps it simple: no logins, no dashboard. |

## 3. Where I disagree with you

**"Hunting for anything" doesn't work, and it's the most important decision
left.** The monitor only alerts on searches you define. "Anything vintage" on
eBay UK means thousands of new listings a day, so every alert would be noise.
eBay also limits how often we can ask, so each extra search makes all of them
slower:

eBay's Browse API allows about **5,000 calls a day** by default (we'll confirm
the exact number in your developer dashboard). We'd use 4,500 and keep the rest
as a safety margin.

| Number of searches | Each search is checked every |
|---|---|
| 3 | ~58 seconds |
| 5 | ~96 seconds |
| 10 | ~3.2 minutes |
| 20 | ~6.4 minutes |

(Formula: 86,400 seconds a day × number of searches ÷ 4,500 calls.)

When good items sell in minutes, 3–5 tight searches beat 20 loose ones. eBay
lets one search cover several brands with OR syntax, which we'll test in
Phase 2 to stretch the budget.

**The monitor finds items; it doesn't tell you what they're worth.** The
standard eBay API doesn't give sold prices (that's a restricted API most
developers can't get). Your profit comes from knowing that a £12 jacket sells
for £45. That knowledge has to come from you, at least at first.

**So your homework before Phase 4:** pick 3 things you could price accurately
yourself. For each, write down the brand or item, the most you'd pay, and what
it typically sells for. Use eBay's "Sold items" filter in the app to research
this; it's free and takes about 20 minutes.

## 4. What only you can do (accounts and keys)

I can't create accounts, accept terms, or enter payment details. You need:

1. **eBay developer account.** Sign up at developer.ebay.com with your normal
   eBay login, then create a **Production** keyset. You'll get an **App ID
   (Client ID)** and a **Cert ID (Client Secret)**.
   - Gotcha: eBay won't turn on production keys until you deal with
     "Marketplace Account Deletion notifications". Choose the **exemption**.
     The monitor only stores listing ID numbers, never sellers' personal data,
     so the exemption applies.
   - Account approval can take anywhere from minutes to a day or so. **Do this
     first.**
2. **Discord:**
   - Create a free private Discord server just for you, with a channel such
     as `#deals`.
   - Channel settings → Integrations → Webhooks → New Webhook → copy the URL.
     Treat this URL like a password: anyone who has it can post in your
     channel.
   - Install the Discord app on your phone (and iPad if you like). Set that
     channel's notifications to **All Messages**. By default Discord only
     notifies on @mentions in servers, and with that default **you would
     get no alerts**.
3. **The MacBook.** It runs the monitor 24/7. Checks before we rely on it:
   - **Which model and macOS version?** Apple menu → About This Mac. Note the
     year, the chip (Intel or Apple M1/M2/…) and the macOS version. The
     monitor needs Python 3.11 or newer from python.org, whose installers
     support macOS back to about 10.13 High Sierra (2017). If the Mac is
     older than that, we need a different approach or the rented server.
   - **Battery safety.** Old MacBook batteries left on charge for months can
     swell, and a swollen battery is a fire risk. Warning signs: the case
     bulging, the trackpad hard to click or raised, the lid not closing flat,
     or the Mac rocking on a table. Also check System Information → Power →
     Battery Information → Condition. Anything other than "Normal" means:
     tell me before going further. Keep it on a hard surface with space
     around it, not a bed or sofa.
   - **The lid must stay open.** A MacBook sleeps when the lid is closed
     (unless a monitor, keyboard and mouse are plugged in), and asleep it
     checks nothing. The screen can turn itself off; only the lid has to
     stay up.
   - **Does it still hold personal stuff** (photos, saved passwords, old
     accounts)? This decides the FileVault question in Phase 3.
   - **Working charger**, and a spot with a decent Wi-Fi signal (or a
     network cable, if the Mac has a port or adapter).
   - **Fallback:** if any check fails, rent a small Linux server (Ubuntu
     24.04, around £4–5/month from a provider such as Hetzner or
     DigitalOcean). The monitor code is the same either way; only the
     auto-start setup differs.
   - **Not the iPad.** iOS pauses or kills apps running in the background,
     usually within minutes of switching away or locking the screen, and
     there's no way to run a script as a permanent background service. It
     would appear to work and then go silent, which is the worst kind of
     failure here. The iPad is fine for *receiving* alerts, if it can still
     run the current Discord app (very old iPads stuck on old iOS versions
     sometimes can't; check the App Store on it).

**Never paste keys or passwords into chat.** They go into a `.env` file on the
MacBook only, readable only by its owner, and never committed to GitHub.

## 5. How it will work

```
 every ~1–2 min                          new matching item?
┌───────────┐   search    ┌──────────┐   ┌────────────┐   alert   ┌───────┐
│  monitor  │ ──────────▶ │ eBay API │   │ filter +   │ ────────▶ │ phone │
│ (MacBook) │ ◀────────── │ (UK)     │──▶│ "seen yet?"│           └───────┘
└───────────┘  newest 50  └──────────┘   └────────────┘
                                              │
                                        small database
                                      (listing IDs seen)
```

**Technical choices**
- Python **3.11 or newer**, **standard library only**. No extra packages, so
  nothing breaks when a package updates.
  - Why 3.11: it's the first version that can read `config.toml` without an
    add-on. The Python Apple bundles with its developer tools is 3.9, which
    is too old, so we install the official one from python.org.
  - Gotcha: python.org's Mac Python doesn't use the Mac's own security
    certificates. Until you run the **"Install Certificates.command"** it
    ships with (one double-click, in Applications → Python 3.x), every
    connection to eBay and Discord fails with `CERTIFICATE_VERIFY_FAILED`.
    The setup script will check for this and say so plainly.
- Searches live in a readable `config.toml` file. Changing what you hunt means
  editing a few lines, with no code changes.
- Secrets (eBay keys, Discord URL) live in `.env` on the MacBook only.
- Auto-start uses **launchd**, the Mac's built-in service manager: it starts
  at boot (no login needed) and restarts the monitor within seconds if it
  crashes.
- It runs under `caffeinate`, the Mac's built-in "don't sleep" command, as a
  second guard on top of the sleep settings.
- An **install script** does the Mac setup (checks Python and certificates,
  installs the launchd service, sets permissions) so you run one command
  instead of following 20 steps by hand, plus an **uninstall script** that
  reverses it.

**Each search can set**
- keywords (e.g. `vintage carhartt jacket`)
- minimum and maximum price
- maximum total including postage (checked by the monitor, since eBay can't
  filter on it)
- condition: used / new / any
- (format is always Buy It Now; not a setting)
- excluded words (e.g. `kids`, `replica`, `damaged`)
- item location (default: UK only, so postage stays cheap and fast)

**Behaviour that prevents mistakes**
1. **No flood on day one.** When a search is new, everything currently listed
   is recorded silently. You only get alerts for items listed *after* that.
2. **No duplicates.** If one item matches two searches, you get one alert.
3. **No stale items.** Listings older than a set age (default 2 hours) are
   ignored, even if eBay shows them because the seller edited them.
4. **Stays within eBay's limit automatically.** The check interval is
   calculated from the number of searches using the formula in §3, so adding
   a search can't push it over the daily limit.
5. **Tells you when it breaks.** If eBay or the alert service fails for more
   than about 15 minutes, you get a "monitor has a problem" alert (at most one
   an hour). This guards against the bot dying silently while you think it's
   working.
6. **Startup message**, so you know it's alive after a reboot.
7. **Config is checked strictly.** A typo like `max_prise` stops it with a
   clear error instead of being silently ignored.
8. **Daily "still alive" message** (e.g. 9am): checks made, alerts sent,
   errors in the last 24 hours. This covers the one failure point 5 can't:
   if the MacBook itself is off, asleep or offline, the monitor can't send
   anything, including a problem alert. Silence from the bot could mean "no
   deals" or "dead". With a daily message, **no message by 9:15 means
   something is wrong**: go and look at the Mac.

**What an alert shows:** photo, title, price, postage, total, condition,
seller feedback, how long ago it was listed, which search it matched, and a
tap-to-open link.

**Commands**
- `run` — the normal 24/7 mode
- `check` — runs each search once and prints the results, to confirm your
  eBay keys and searches work before going live
- `test-alert` — sends one test alert to confirm your phone gets it
- `status` — says whether the background service is running, when it last
  checked eBay, and the last error, if any

## 6. Alert channel: Discord (decided)

One webhook URL, no bot to run. It shows the photo nicely, sends real push
notifications through the phone app, and keeps a scrollable history of every
alert, which is useful for the Phase 4 review. The alert code stays in its own
small module, so adding Telegram or another channel later is a contained
change.

Limit: Discord slows down a webhook that posts more than a few messages a
second. The monitor will space out messages and obey Discord's "wait" replies,
so a burst of 30 new items arrives over a few seconds rather than being lost.
If you regularly get bursts that big, your searches are too broad (§3).

## 7. Phases

Each phase has a check that must pass before the next starts.

### Phase 0 — Accounts (you; can start now)
- [ ] eBay developer account + Production keys + deletion-notification exemption
- [ ] Discord server + `#deals` channel + webhook URL, with the channel's
      notifications set to All Messages
- [ ] MacBook checks from §4 item 3: model, macOS version, battery
      condition, personal data or not. Send me the answers (no passwords).
- **Done when:** you have the eBay App ID, Cert ID and Discord webhook URL
  saved somewhere safe (a password manager or your phone's notes, **not**
  chat), and a message posted in `#deals` from another device makes your
  phone buzz.

### Phase 1 — Build (me; one session)
- [ ] Project structure, config loading with strict validation
- [ ] eBay client: login token (auto-renewed every 2 hours), search, rate budget
- [ ] Seen-items database, silent first run, de-duplication, stale filter
- [ ] Filters: excluded words, max total including postage
- [ ] Discord alerts (with rate-limit handling), plus problem alerts and
      startup message
- [ ] Buy It Now only, enforced in the eBay search itself
- [ ] `run`, `check`, `test-alert`, `status` commands, plus the daily
      still-alive message
- [ ] Mac install/uninstall scripts (Python version check, certificate
      check, launchd service, `caffeinate`, file permissions)
- [ ] Automated tests using fake eBay/Discord responses, covering each rule in §5
- [ ] Setup guide (README) written for a non-programmer
- [ ] Committed and pushed to branch `claude/zealous-mccarthy-surmas`
- **Done when:** all tests pass and I've run the full monitor locally against
  a fake eBay server, showing alerts firing correctly.
- **Honest limit:** this cloud session can't reach eBay or Discord
  (verified 2026-11-08: blocked), and it runs Linux, not macOS. Phase 1
  proves the logic is right, **not** that it works against the real eBay or
  that the Mac scripts work on your Mac. Phases 2 and 3 prove those.

### Phase 2 — First live test on the MacBook (you + me; ~45 min)
- [ ] Install Python 3.11+ from python.org and run "Install Certificates.command"
- [ ] Download the project onto the Mac (I'll give exact steps)
- [ ] Put your keys in `.env` on the Mac
- [ ] Run `test-alert` → the alert arrives on your phone
- [ ] Run `check` → real eBay listings print with correct prices and links
- [ ] Confirm the real daily call limit in the eBay developer dashboard
- [ ] Test whether OR searches work (`(carhartt, dickies) jacket`)
- **Done when:** real listings come back and a test alert reaches your phone.
  Anything that differs from my assumptions gets fixed here.

### Phase 3 — Go live on the MacBook (you + me; ~45 min)
- [ ] **FileVault decision** (System Settings → Privacy & Security →
      FileVault). With FileVault on, after any restart (power cut, update)
      the Mac waits at a password screen and **the monitor doesn't run until
      someone types the password**.
      - If the Mac holds no personal data: **turn FileVault off.** The only
        secrets on it are the eBay keys (which can only read public
        listings) and the Discord webhook, and both can be cancelled and
        replaced in minutes if the Mac is stolen.
      - If it does hold personal data: either back it up and erase the Mac,
        or keep FileVault on and accept typing the password after restarts.
- [ ] Sleep settings: never sleep on the charger, screen off after a few
      minutes. Lid stays open.
- [ ] Software updates: keep security updates on, but turn off automatic
      macOS **upgrades**, which restart the Mac at random times and can
      change things.
- [ ] Run the install script → launchd service installed
- [ ] Restart the Mac and confirm the startup alert arrives **without
      logging in**
- [ ] Unplug the charger for 10 minutes and confirm it keeps working on
      battery, then plug back in
- [ ] Deliberately break the eBay key and confirm the problem alert arrives,
      then fix the key
- [ ] Confirm the daily still-alive message arrives the next morning
- [ ] (Optional, free) An outside "dead man's switch" such as
      healthchecks.io: the monitor checks in every few minutes, and if the
      check-ins stop, that service messages your Discord. Faster warning
      than waiting for the daily message.
- **Done when:** it survives a restart with nobody logging in, survives
  10 minutes on battery, and you've seen the startup, problem and daily
  messages.
- **Known gap:** after a long power cut that drains the battery completely,
  the Mac may not switch itself back on when power returns; it might need
  the power button pressing. The missing daily message is how you'd find out.

### Phase 4 — Tune for a week (you, with me)
- [ ] Replace the example searches with your homework from §3
- [ ] Keep a simple log of each alert: bought? price? sold for? profit?
- [ ] After 7 days: which searches made money, which were noise, which were
      too slow
- **Done when:** you know your profit per search and have cut the losers.
  This is the phase that decides whether this is a business or a toy.

### Phase 5 — Later, only if Phase 4 makes money
- Depop (or Vinted, which is bigger for vintage clothing in the UK) — with
  the ban risk accepted in writing
- Profit estimate in each alert, based on your own sold-price notes
- A "deal score" to rank alerts by how underpriced they look

## 8. Costs

| Item | Cost |
|---|---|
| eBay developer account | Free |
| Discord | Free |
| Python | Free |
| Electricity for the MacBook | ~£1–1.50/month (estimate: ~5–8 W, screen off, at ~25p per unit) |
| **Total** | **~£1–1.50/month** (fallback server instead: ~£5/month) |

## 9. Risks

| Risk | How likely | What we do |
|---|---|---|
| eBay's real API behaves differently from my assumptions | Medium | Phase 2 exists to catch this before going live. |
| Searches too broad → alert spam → you stop looking | High if we skip §3 homework | Tight searches, excluded words, review in Phase 4. |
| Other resellers' bots are faster | Medium | A niche you know well beats raw speed. |
| Buying items that don't resell (dead stock) | Real | Only search for things you've price-checked. |
| eBay changes its rules or limits | Low | Official API; change log in the developer portal. |
| MacBook goes to sleep, gets switched off, or loses Wi-Fi | Medium | Sleep settings + `caffeinate` + lid open; the daily still-alive message reveals it; optional dead man's switch. |
| MacBook battery swells | Low–medium on an old Mac | Battery check before starting (§4); hard surface; stop using it if signs appear. |
| Mac too old for current Python | Unknown until you check | Version check in Phase 0; rented server as fallback. |
| macOS update restarts or changes things | Low | Automatic upgrades off; service starts at boot without login. |
| Keys leak | Low | Keys only in `.env` on the Mac, owner-readable only, never in git or chat; both can be cancelled and replaced. |

## 10. Open questions for Max

Answered 2026-11-08: Discord ✔ · Buy It Now only ✔ · 24/7 alerts ✔ ·
iPad as server ✘ · old unused MacBook as the host ✔.

Still open:
1. MacBook details: year/model, Intel or Apple chip, macOS version, battery
   condition, any swelling signs (§4 item 3).
2. Is there still personal data on the MacBook? (Decides FileVault, Phase 3.)
3. By "notifications as well as Discord", did you mean the Discord app's own
   phone push notifications (already the plan), or a second, separate alert
   method on top of Discord?
4. Your 3 starter searches with price limits (§3 homework). I'll ship
   placeholder examples until then.

---

## Change log
- 2026-11-08 — Plan written. eBay first, Depop deferred, ~£5/month server,
  single user. Build not started.
- 2026-11-08 — Decided: Discord only (Telegram/ntfy dropped from v1), Buy It
  Now only, alerts 24/7 (quiet hours removed from Phase 5). Ruled out the
  iPad as the server. Build still not started.
- 2026-11-08 — Host: Max's old, unused MacBook, staying on macOS (installing
  Linux on a Mac is often painful, especially Wi-Fi drivers, and not worth
  it). systemd swapped for launchd + caffeinate; added install/uninstall
  scripts, `status` command, daily still-alive message, FileVault and
  battery checks. Rented server kept as the fallback. Build still not started.
