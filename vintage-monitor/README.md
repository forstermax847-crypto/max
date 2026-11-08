# Vintage Monitor

Watches **eBay UK** for new **Buy It Now** listings that match your searches,
and posts an alert to your **Discord** `#deals` channel within about a minute
of each one being listed. It runs 24/7 on a small server.

The full plan, decisions and reasoning are in [PLAN.md](PLAN.md).

- No extra software: plain Python 3.11+ (Ubuntu 24.04 ships 3.12).
- Your searches live in [`config.toml`](config.toml).
- Your keys live in a secrets file **on the server only**, never on GitHub.

---

## Everyday use (on the server)

| Command | What it does |
|---|---|
| `vmonitor status` | Is it working? When did it last check eBay? Any errors? |
| `vmonitor check` | Runs each search once and prints what eBay returns, and whether each listing would alert or why it would be skipped. Doesn't send alerts. |
| `vmonitor test-alert` | Sends a test message and a sample deal to Discord. |
| `vmonitor validate` | Checks `config.toml` for mistakes and shows how often each search runs. |
| `vmonitor logs` | Shows the last 100 lines of the log (`vmonitor logs 500` for more). |
| `systemctl restart vintage-monitor` | Restarts the monitor. |

**What you'll see in Discord**
- 🟢 **Started**: after every restart or reboot, listing your searches.
- **Deal alerts**: photo, price, postage, total, condition, how long ago it
  was listed, which search matched, seller feedback, and a link. The phone
  notification shows the total and the title.
- ✅ **Still running**: every day at 09:00 UK time, with counts for the last
  day. **If it hasn't arrived by 09:15, something is wrong.** Run
  `vmonitor status`, or ask Claude.
- ⚠️ **Problem**: a search has been failing for 15 minutes (repeated at most
  hourly), then ✅ **Recovered** when it's fixed.

## Changing your searches

1. Edit `vintage-monitor/config.toml` on GitHub (open the file, click the
   pencil icon, then **Commit changes**), or ask Claude to do it.
2. On the server run:
   ```bash
   /opt/vintage-monitor/vintage-monitor/deploy/update.sh
   ```
   It downloads the change, **checks it first**, and only then restarts. If
   there's a mistake (a typo such as `max_prise`), it says what's wrong,
   goes back to the previous version, and the monitor keeps running.

A changed or new search records the current listings silently first, so you
won't get a flood of old ones.

Each search can use:

```toml
[[search]]
name = "Barbour wax"                 # shown in alerts
query = "barbour wax jacket"         # eBay search words (max 100 characters)
max_total = 25                       # most you'll pay INCLUDING postage, in £
max_price = 22                       # (optional) most for the item alone
min_price = 5                        # (optional) skip anything cheaper
exclude = ["style", "hood only"]     # (optional) extra title words to skip
condition = "used"                   # (optional) used | new | any
location = "GB"                      # (optional) "" for anywhere
```

Excluded words match **whole words in the title**, ignoring capitals: `kids`
skips "Kids' jacket" but `boy` won't skip "boyfriend". Keep the list short,
because every word can hide a good deal.

---

## First-time setup (Phases 2 and 3 of the plan)

Do this with Claude. It takes about an hour. You'll type commands into the
MacBook's **Terminal** app. In the steps below, copy each grey box exactly.

You need: your eBay **Production** App ID and Cert ID, your Discord webhook
URL, and a DigitalOcean account. **Never paste keys into a chat.**

### 1. Make a login key on the MacBook

```bash
ssh-keygen -t ed25519 -C "macbook"
```

Press Enter at each question (choosing a passphrase is optional but
better). Then show the **public** half:

```bash
cat ~/.ssh/id_ed25519.pub
```

Copy the whole line starting `ssh-ed25519`. This half is safe to share. The
other file, `id_ed25519` without `.pub`, is private and never leaves the Mac.

### 2. Create the server on DigitalOcean

DigitalOcean calls a server a **Droplet**. Click **Create → Droplets**:
- **Region:** London
- **Image:** Ubuntu **24.04 (LTS)** x64
- **Size:** Basic → Regular → the **1 GB memory** plan. Check the price
  shown; it should be about $6 a month. The cheaper 512 MB plan can run out
  of memory during system updates, so I'd avoid it.
- **Authentication:** **SSH Key** → **New SSH Key** → paste the line from
  step 1, and name it `macbook`. Don't choose Password.
- **Hostname:** `vintage-monitor`
- Leave **backups off** and skip other paid extras.
- Click **Create Droplet**.

Note the Droplet's **ipv4 address** (four numbers like `203.0.113.10`). If
you ever get locked out, the Droplet's page has a **Console** button that
opens a terminal in your browser.

### 3. Log in and lock it down

```bash
ssh root@YOUR_SERVER_IP
```

Type `yes` the first time. You're now on the server. Run these one at a time:

```bash
apt update && apt -y upgrade
```

```bash
apt -y install unattended-upgrades git
```

```bash
ufw allow OpenSSH && ufw --force enable
```

```bash
echo "PasswordAuthentication no" > /etc/ssh/sshd_config.d/00-no-passwords.conf && systemctl restart ssh
```

(The `00-` matters: SSH uses the *first* value it finds, and Ubuntu may ship
a later file that turns passwords back on.) Confirm it worked:

```bash
sshd -T | grep -i passwordauthentication
```

It must say `passwordauthentication no`.

**Before closing this window**, open a *second* Terminal window and check you
can still log in with `ssh root@YOUR_SERVER_IP`. If you can't, don't close
the first window: ask Claude.

If `apt -y upgrade` says a restart is needed, run `reboot`, wait a minute,
and log in again.

### 4. Give the server read-only access to this repo

```bash
ssh-keygen -t ed25519 -f /root/.ssh/github_deploy -N "" -C "vintage-monitor server"
```

```bash
cat /root/.ssh/github_deploy.pub
```

On GitHub: this repo → **Settings** → **Deploy keys** → **Add deploy key**.
Title it `Monitor server`, paste the line, and **leave "Allow write access"
unticked**. Then, back on the server:

```bash
printf 'Host github.com\n  IdentityFile /root/.ssh/github_deploy\n  IdentitiesOnly yes\n' >> /root/.ssh/config
```

### 5. Download the project

```bash
git clone -b claude/zealous-mccarthy-surmas git@github.com:forstermax847-crypto/max.git /opt/vintage-monitor
```

It will ask whether to trust `github.com`. GitHub's published ED25519
fingerprint is `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`. Check it
matches (and against GitHub's "SSH key fingerprints" docs page), then type
`yes`.

### 6. Install

```bash
/opt/vintage-monitor/vintage-monitor/deploy/install.sh
```

It creates a restricted user for the monitor, the secrets file and the
service, and runs the built-in tests. It won't start the monitor until the
keys are in.

### 7. Add your keys

```bash
nano /etc/vintage-monitor/.env
```

Replace each `PASTE_...` value with the real one (paste with Cmd+V). Save
with **Ctrl+O**, Enter, then exit with **Ctrl+X**.

### 8. Test, then start

```bash
vmonitor test-alert
```

Your phone should buzz twice.

```bash
vmonitor check
```

You should see real eBay listings with prices and links. This is the first
time the code talks to the real eBay, so tell Claude about anything odd.

```bash
systemctl restart vintage-monitor && sleep 5 && vmonitor status
```

A 🟢 Started message should arrive in Discord.

### 9. Prove it recovers (Phase 3 checks)

- `reboot`, wait two minutes, and check a new 🟢 Started message arrives
  without you doing anything.
- Next morning, check the ✅ Still running message arrived around 09:00.

---

## Problems

| Message | What it means / what to do |
|---|---|
| `eBay rejected the keys` | Wrong App ID or Cert ID, or the Sandbox ones. Use the **Production** keyset. |
| `EBAY_CLIENT_ID is a Sandbox key` | Same: copy the Production keys instead. |
| `Missing in the secrets file` | A `PASTE_...` placeholder is still in `/etc/vintage-monitor/.env`. |
| `Discord rejected the webhook (HTTP 404)` | The webhook was deleted. Make a new one and put it in the secrets file. |
| `eBay says the daily allowance is used up` | Too many calls today. It pauses and retries. If it keeps happening, lower `daily_call_budget`. |
| `CERTIFICATE_VERIFY_FAILED` | Run `apt -y install ca-certificates`. |
| `CONFIG PROBLEM: ...` | A mistake in `config.toml`. The message names the search and setting. |
| No 09:00 message | Server off or monitor stopped: `vmonitor status`, then `vmonitor logs`. |

## How it avoids mistakes

- **No flood on first run:** a new or changed search records what's already
  listed, silently.
- **No duplicates:** an item matching two searches alerts once.
- **Buy It Now only:** auctions, including auctions with a Buy It Now option,
  are skipped.
- **Stale listings skipped:** anything listed more than 2 hours ago is
  ignored.
- **Within eBay's limit:** checks are spaced automatically from
  `daily_call_budget`.
- **Failed alerts retried:** if Discord is down, listings are retried on the
  next check, not lost.
- **Privacy:** it stores only eBay listing IDs, never sellers' details, and
  listing titles can't ping you or fake links in Discord.
- **Locked down:** runs as a restricted user that can't change its own code;
  secrets are readable only by that user and root.

## Files

| Path | What |
|---|---|
| `config.toml` | Your searches |
| `.env.example` | Template for the secrets file |
| `vintage_monitor/` | The code |
| `tests/` | Automated tests (`python3 -m unittest discover -s tests -t .`) |
| `deploy/` | Server scripts: `install.sh`, `update.sh`, `uninstall.sh`, the `vmonitor` helper, the service file |

On the server: code in `/opt/vintage-monitor`, secrets in
`/etc/vintage-monitor/.env`, database in `/var/lib/vintage-monitor/`.

## Stopping for good

Run `/opt/vintage-monitor/vintage-monitor/deploy/uninstall.sh --purge`, then
**destroy the Droplet in the DigitalOcean dashboard**. A server that's only switched
off still costs money. Also remove the deploy key on GitHub.
