# Vintage Monitor — Build Plan

Status: **planned, not started.** Nothing gets built until Max says go.
Last updated: 2026-11-08

This file is the single source of truth for the project. A new Claude session
has no memory of earlier conversations. Start any session on this project by
reading this file, and update it whenever a decision changes.

---

## 1. What we are building

A bot that runs 24/7 on a small server, watches **eBay UK** for new listings
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
| Alerts | Discord, Telegram or phone push (ntfy) | All three get built; you set up whichever you want. **My recommendation: Discord** (see §6). |
| Hosting | A cheap server, about £5/month | It has to run 24/7, and a Claude cloud session shuts down when idle. |
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
2. **The alert channel you chose:**
   - Discord: make a private server → channel settings → Integrations →
     Webhooks → New Webhook → copy the URL. Install the Discord app on your
     phone and turn notifications on for that channel.
   - Telegram: message @BotFather to create a bot and get a token, then get
     your chat ID (I'll walk you through it).
   - ntfy: install the ntfy app and subscribe to a long random topic name.
     Anyone who guesses the name can read your alerts, so make it unguessable.
3. **A server.** A small Linux machine (Ubuntu 24.04) from a provider such as
   Hetzner or DigitalOcean. The smallest plan is plenty. Check the current
   price; it should be around £4–5 a month. An old laptop or a Raspberry Pi at
   home also works and costs nothing per month.

**Never paste keys or passwords into chat.** They go into a `.env` file on the
server only, and that file is never committed to GitHub.

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
- Python 3, **standard library only**. Nothing to install, so nothing to break
  when a package updates.
- Searches live in a readable `config.toml` file. Changing what you hunt means
  editing a few lines, with no code changes.
- Secrets (eBay keys, Discord URL) live in `.env` on the server only.
- Runs as a `systemd` service, so it starts when the server boots and restarts
  itself if it crashes.

**Each search can set**
- keywords (e.g. `vintage carhartt jacket`)
- minimum and maximum price
- maximum total including postage (checked by the monitor, since eBay can't
  filter on it)
- condition: used / new / any
- format: Buy It Now / auction / both
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

**What an alert shows:** photo, title, price, postage, total, condition,
seller feedback, how long ago it was listed, which search it matched, and a
tap-to-open link.

**Commands**
- `run` — the normal 24/7 mode
- `check` — runs each search once and prints the results, to confirm your
  eBay keys and searches work before going live
- `test-alert` — sends one test alert to confirm your phone gets it

## 6. Alert channel: my recommendation

**Discord.** It's the easiest to set up (one URL, no bot), shows the photo
nicely, sends push notifications through the phone app, and keeps a scrollable
history of every alert. Telegram is just as good if you already use it. ntfy
is the simplest pure push notification but looks the plainest. All three will
be supported, so switching later is a one-line change.

## 7. Phases

Each phase has a check that must pass before the next starts.

### Phase 0 — Accounts (you; can start now)
- [ ] eBay developer account + Production keys + deletion-notification exemption
- [ ] Alert channel set up and receiving notifications on your phone
- [ ] (Can wait until Phase 3) Server bought
- **Done when:** you have the eBay App ID and Cert ID saved somewhere safe,
  and the Discord/Telegram/ntfy app is on your phone.

### Phase 1 — Build (me; one session)
- [ ] Project structure, config loading with strict validation
- [ ] eBay client: login token (auto-renewed every 2 hours), search, rate budget
- [ ] Seen-items database, silent first run, de-duplication, stale filter
- [ ] Filters: excluded words, max total including postage
- [ ] Alerts: Discord, Telegram, ntfy, plus problem alerts and startup message
- [ ] `run`, `check`, `test-alert` commands
- [ ] Automated tests using fake eBay/Discord responses, covering each rule in §5
- [ ] Setup guide (README) written for a non-programmer
- [ ] Committed and pushed to branch `claude/zealous-mccarthy-surmas`
- **Done when:** all tests pass and I've run the full monitor locally against
  a fake eBay server, showing alerts firing correctly.
- **Honest limit:** this cloud session can't reach eBay, Discord or Telegram
  (verified 2026-11-08: blocked). Phase 1 proves the logic is right, **not**
  that it works against the real eBay. Phase 2 proves that.

### Phase 2 — First live test (you + me; ~30 min)
- [ ] Put your keys in `.env` on the server or your own computer
- [ ] Run `test-alert` → the alert arrives on your phone
- [ ] Run `check` → real eBay listings print with correct prices and links
- [ ] Confirm the real daily call limit in the eBay developer dashboard
- [ ] Test whether OR searches work (`(carhartt, dickies) jacket`)
- **Done when:** real listings come back and a test alert reaches your phone.
  Anything that differs from my assumptions gets fixed here.

### Phase 3 — Go live on the server (you + me; ~45 min)
- [ ] Basic server security: SSH key login, automatic security updates, firewall
- [ ] Copy the project over, add `.env`, install the systemd service
- [ ] Reboot the server and confirm the startup alert arrives
- [ ] Deliberately break the eBay key and confirm the problem alert arrives,
      then fix the key
- **Done when:** it survives a reboot and you've seen both the startup alert
  and the problem alert.

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
- Quiet hours (no alerts while you sleep, or only very good deals)

## 8. Costs

| Item | Cost |
|---|---|
| eBay developer account | Free |
| Discord / Telegram / ntfy | Free |
| Server | ~£4–5/month (or £0 on hardware you own) |
| **Total** | **~£5/month** |

## 9. Risks

| Risk | How likely | What we do |
|---|---|---|
| eBay's real API behaves differently from my assumptions | Medium | Phase 2 exists to catch this before going live. |
| Searches too broad → alert spam → you stop looking | High if we skip §3 homework | Tight searches, excluded words, review in Phase 4. |
| Other resellers' bots are faster | Medium | A niche you know well beats raw speed. |
| Buying items that don't resell (dead stock) | Real | Only search for things you've price-checked. |
| eBay changes its rules or limits | Low | Official API; change log in the developer portal. |
| Server goes down silently | Low | Problem alerts plus a startup alert. |
| Keys leak | Low | Keys only in `.env` on the server, never in git or chat. |

## 10. Open questions for Max

1. Which alert channel: Discord (recommended), Telegram or ntfy?
2. Server at home (old laptop or Pi) or rented (~£5/month)? If rented, do you
   have a provider in mind?
3. Your 3 starter searches with price limits (§3 homework). I'll ship
   placeholder examples until then.
4. Should auctions alert at all? Auctions rarely end cheap at the moment
   they're listed, so I'd default to **Buy It Now only**.
5. Do you want quiet hours from day one, or alerts 24/7?

---

## Change log
- 2026-11-08 — Plan written. eBay first, Depop deferred, ~£5/month server,
  single user. Build not started.
