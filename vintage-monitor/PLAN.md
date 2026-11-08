# Vintage Monitor — Build Plan

Status: **planned, not started.** Nothing gets built until Max says go.
Last updated: 2026-11-08

This file is the single source of truth for the project. A new Claude session
has no memory of earlier conversations. Start any session on this project by
reading this file, and update it whenever a decision changes.

---

## 1. What we are building

A bot that runs 24/7 on a **small rented server**, watches **eBay UK** for new listings
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
| Hosting | **Rented Linux server from Hetzner, ~£5/month** (decided 2026-11-08, replacing the MacBook idea) | It has to run 24/7, and a Claude cloud session shuts down when idle. A server avoids everything that could stop a home machine: sleep, lid, battery, Wi-Fi, power cuts, password screens after restarts. It costs about £40/year more than the MacBook would have. The old MacBook is still useful as the computer you **connect to** the server from. **The iPad can't be the server**; it can receive the alerts. |
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

1. **eBay developer account** (free). A normal eBay account alone can't do
   this: the monitor uses eBay's official API, which needs keys, and only
   the developer program issues them. Register at developer.ebay.com. The
   developer program has historically used its **own separate sign-up**
   (its own username/password), not your normal eBay login; if it offers to
   use your eBay login, that's fine too. The monitor never needs the two
   linked. Keep your normal eBay account for actually buying. Then create a
   **Production** keyset. You'll get an **App ID (Client ID)** and a
   **Cert ID (Client Secret)**.
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
3. **A rented server.**
   - **Provider:** Hetzner (cheapest; data centres in Germany/Finland, which
     doesn't matter for this) or DigitalOcean (slightly dearer, very
     beginner-friendly). Pick the **smallest, cheapest shared plan**; even
     1–2 GB of memory is far more than the monitor needs. Check the current
     price before buying; it should be around £4–5 a month including VAT.
   - **Operating system:** choose **Ubuntu 24.04 LTS**. It comes with
     Python 3.12, so there's nothing to install for the monitor itself.
   - **Don't** add paid extras (backups, volumes, load balancers, extra IPs).
     Nothing on the server is irreplaceable: the code and searches live in
     GitHub, and the only data is the list of listing IDs already seen.
   - **Sign-up:** you need a payment card, and providers require account
     holders to be 18 or over. Hetzner sometimes asks new customers for ID
     verification, which can take a day, so sign up early.
   - **Login key:** when the provider asks for an "SSH key", don't choose
     a password. I'll walk you through making a key on the MacBook (one
     command in the Terminal app) and pasting in its **public** half. The
     private half never leaves the MacBook and is never pasted anywhere.
   - **How you'll reach it:** from the old MacBook's Terminal app (best), or
     the provider's in-browser console as a backup. An iPad SSH app (e.g.
     Termius) works too, but I'd use the MacBook for setup.
   - **Not the iPad as the server.** iOS pauses or kills apps running in the background,
     usually within minutes of switching away or locking the screen, and
     there's no way to run a script as a permanent background service. It
     would appear to work and then go silent, which is the worst kind of
     failure here. The iPad is fine for *receiving* alerts, if it can still
     run the current Discord app (very old iPads stuck on old iOS versions
     sometimes can't; check the App Store on it).

**Never paste keys or passwords into chat.** They go into a `.env` file on the
server only, readable only by the monitor's user, and never committed to GitHub.

## 5. How it will work

```
 every ~1–2 min                          new matching item?
┌───────────┐   search    ┌──────────┐   ┌────────────┐   alert   ┌───────┐
│  monitor  │ ──────────▶ │ eBay API │   │ filter +   │ ────────▶ │ phone │
│ (server)  │ ◀────────── │ (UK)     │──▶│ "seen yet?"│           └───────┘
└───────────┘  newest 50  └──────────┘   └────────────┘
                                              │
                                        small database
                                      (listing IDs seen)
```

**Technical choices**
- Python **3.11 or newer** (Ubuntu 24.04 ships 3.12), **standard library
  only**. No extra packages, so nothing breaks when a package updates. 3.11
  is the minimum because it's the first version that reads `config.toml`
  without an add-on.
- Searches live in a readable `config.toml` file. Changing what you hunt means
  editing a few lines, with no code changes.
- Secrets (eBay keys, Discord URL) live in `.env` on the server only.
- Runs as a **systemd** service under its own unprivileged user account: it
  starts when the server boots and restarts itself if it crashes.
- Code reaches the server from GitHub using a **read-only deploy key**: the
  server can download this repo but can't change it, and can't see any
  other repo of yours.
- Scripts so you run one command instead of 20 manual steps:
  - **install** — creates the monitor user, checks Python, installs the
    systemd service, sets file permissions
  - **update** — pulls the latest code/searches from GitHub, checks the
    config, restarts the service (and refuses to restart if the config is
    broken, so a typo can't take the monitor down)
  - **uninstall** — reverses install

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
   if the server itself is down, the monitor can't send anything, including
   a problem alert. Silence from the bot could mean "no deals" or "dead".
   With a daily message, **no message by 9:15 means something is wrong**:
   check the server (or ask me to help).

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
      — *2026-11-08: account submitted, awaiting eBay approval*
- [ ] Discord server + `#deals` channel + webhook URL, with the channel's
      notifications set to All Messages
- [ ] In the normal eBay app: 1–2 **saved searches with notifications on**,
      as a free baseline to race the bot against in Phase 4
- [ ] Hetzner account opened (and ID-verified, if asked). **Don't
      create the server itself yet**: we do that together in Phase 2 so the
      SSH key is set up correctly from the start.
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
- [ ] Server install / update / uninstall scripts and the systemd service file
- [ ] Automated tests using fake eBay/Discord responses, covering each rule in §5
- [ ] Setup guide (README) written for a non-programmer
- [ ] Committed and pushed to branch `claude/zealous-mccarthy-surmas`
- **Done when:** all tests pass and I've run the full monitor locally against
  a fake eBay server, showing alerts firing correctly.
- **Honest limit:** this cloud session can't reach eBay or Discord
  (verified 2026-11-08: blocked), and it can't run a real systemd service.
  Phase 1 proves the logic is right, **not** that it works against the real
  eBay or that the install script works on a real server. Phases 2 and 3
  prove those.

### Phase 2 — Server set up + first live test (you + me; ~1 hour)
- [ ] Make an SSH key on the MacBook; create the server (Ubuntu 24.04,
      smallest plan) with that key
- [ ] Log in from the MacBook's Terminal; basic security: system updates,
      automatic security updates, firewall allowing SSH only, password
      login switched off
- [ ] Add a read-only deploy key to the GitHub repo; download the project
- [ ] Put your keys in `.env` on the server
- [ ] Run `test-alert` → the alert arrives on your phone
- [ ] Run `check` → real eBay listings print with correct prices and links
- [ ] Confirm the real daily call limit in the eBay developer dashboard
- [ ] Test whether OR searches work (`(carhartt, dickies) jacket`)
- **Done when:** real listings come back and a test alert reaches your phone.
  Anything that differs from my assumptions gets fixed here.

### Phase 3 — Go live on the server (you + me; ~30 min)
- [ ] Run the install script → systemd service installed and running
- [ ] Reboot the server and confirm the startup alert arrives on its own
- [ ] Deliberately break the eBay key and confirm the problem alert arrives,
      then fix the key
- [ ] Break the config on purpose and run update → confirm it refuses and
      the monitor keeps running on the old config
- [ ] Confirm the daily still-alive message arrives the next morning
- [ ] (Optional, free) An outside "dead man's switch" such as
      healthchecks.io: the monitor checks in every few minutes, and if the
      check-ins stop, that service messages your Discord. Faster warning
      than waiting for the daily message.
- **Done when:** it survives a reboot unaided, and you've seen the startup,
  problem and daily messages.

### Phase 4 — Tune for a week (you, with me)
- [ ] Replace the example searches with your homework from §3
- [ ] **Race against eBay's own alerts.** Set up the same search as an eBay
      app "saved search" with notifications (free, set up in Phase 0) and
      note which alert arrives first, and by how long. If eBay's own alerts
      are about as fast, the bot's value is its filters (max total incl.
      postage, excluded words) and the still-alive check, not speed, and we
      decide whether that's worth ~£5/month.
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
| Server (smallest plan, no extras) | ~£4–5/month; check the current price when buying |
| **Total** | **~£5/month (~£50–60/year)** |

## 9. Risks

| Risk | How likely | What we do |
|---|---|---|
| eBay's real API behaves differently from my assumptions | Medium | Phase 2 exists to catch this before going live. |
| Searches too broad → alert spam → you stop looking | High if we skip §3 homework | Tight searches, excluded words, review in Phase 4. |
| Other resellers' bots are faster | Medium | A niche you know well beats raw speed. |
| Buying items that don't resell (dead stock) | Real | Only search for things you've price-checked. |
| eBay changes its rules or limits | Low | Official API; change log in the developer portal. |
| Server goes down | Low | Service restarts itself; daily still-alive message; optional dead man's switch. |
| Someone breaks into the server | Low | SSH key only (no passwords), firewall, automatic security updates, monitor runs as an unprivileged user. |
| Lost access to the server (MacBook dies, key lost) | Low | Provider's in-browser console as a back door; the server can be rebuilt from GitHub in ~30 min. |
| Keys leak | Low | Keys only in `.env` on the server, never in git or chat; eBay keys and the Discord webhook can both be cancelled and replaced in minutes. |
| Forgotten subscription | Medium | It's a monthly charge. If you stop the project, **delete the server** in the provider's dashboard; switching it off still costs money with most providers. |

## 10. Open questions for Max

Answered 2026-11-08: Discord ✔ · Buy It Now only ✔ · 24/7 alerts ✔ ·
iPad as server ✘ · rented server ✔ (MacBook dropped as host; used to
connect to the server instead).

Still open:
1. ~~Hetzner or DigitalOcean?~~ Hetzner ✔ (DigitalOcean if Hetzner's ID
   check is a hassle).
2. Does the old MacBook still turn on and open the Terminal app? It's the
   simplest way to set up and reach the server. If not, the provider's
   browser console works.
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
- 2026-11-08 — Max chose the rented server instead ("easier"); agreed, as it
  removes every home-machine failure mode for ~£40/year more. Back to
  Ubuntu 24.04 + systemd; MacBook steps removed; added read-only deploy
  key, update script that refuses a broken config, server hardening, and
  "delete the server if you stop". Build still not started.
- 2026-11-08 — Hetzner chosen. Corrected §4: the eBay developer account is
  (historically) a separate free sign-up, not the normal eBay login.
  Added eBay's own saved-search alerts as a free baseline to race the bot
  against in Phase 4. Build still not started.
