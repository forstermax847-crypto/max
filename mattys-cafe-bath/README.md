# Matty's Cafe — Bath

One-page website for Matty's Cafe, 15 St Peter's Terrace, Lower Bristol Road, Bath BA2 3BT.

- `index.html` — the whole site (self-contained HTML/CSS/JS, no build step)
- `fonts.css` — self-hosted fonts (Young Serif, Work Sans, IBM Plex Mono; SIL OFL licensed)
- `img/` — photos and the Matty's logo

## Publishing

Serve the repo root with any static host. For GitHub Pages:
Settings → Pages → Deploy from a branch → `main` / root.

To point a custom domain (e.g. mattyscafe.com) at it: add the domain in the
Pages settings, set a CNAME record for `www` to `forstermax847-crypto.github.io`,
and A records on the bare domain to GitHub Pages IPs
(185.199.108.153, .109.153, .110.153, .111.153). Keep existing MX records
untouched so email keeps working.

## SEO and AI-search files

- `robots.txt` — allows all search crawlers and explicitly welcomes AI answer engines
  (GPTBot, ClaudeBot, PerplexityBot, Google-Extended and others). Points to the sitemap.
- `sitemap.xml` — one URL plus image entries. Update `lastmod` when the page changes.
- `llms.txt` — a plain-text summary of the cafe for large language models.
- Structured data (schema.org) is embedded in `index.html` as JSON-LD: the business, its
  opening hours, the full menu with prices, and the FAQ.

**If the domain changes from `mattyscafe.com`,** update it in these places:
`robots.txt`, `sitemap.xml`, `llms.txt`, and in `index.html` the canonical link,
the `og:` tags and the JSON-LD block.

## Contact form

The form posts to [FormSubmit](https://formsubmit.co) at `matt@mattyscafe.com` — no account
or server needed. **FormSubmit sends a one-off confirmation email to that address the first
time the form is used; the link in it must be clicked before any messages come through.**
To change the destination, edit the address in the form `action` and in the `fetch` call
near the bottom of `index.html`.

## Making sure form emails arrive

Form messages are relayed by FormSubmit from **their** servers, not from `mattyscafe.com`.
That has two consequences worth understanding:

1. **SPF, DKIM and DMARC records on `mattyscafe.com` make no difference to these emails.**
   They would only matter if the mail were sent *as* `@mattyscafe.com`, which would require
   a different setup (see below). Publishing a DMARC record is still worth doing for general
   anti-spoofing, but it is not a fix for this.
2. **Deliverability depends on the receiving mailbox trusting FormSubmit.** For a single known
   recipient this is easy to guarantee with a filter rule.

### Do this once, in the inbox that receives enquiries

**Gmail / Google Workspace**
1. Settings (gear) → See all settings → **Filters and Blocked Addresses**
2. **Create a new filter**, in the *From* box enter: `formsubmit.co`
3. Click **Create filter**, then tick:
   - **Never send it to Spam**
   - **Always mark it as important**
   - Optionally **Apply the label**: `Website enquiries`
4. **Create filter**

**Outlook / Microsoft 365**
Settings → Mail → Junk email → **Safe senders and domains** → Add `formsubmit.co`

That makes the messages effectively immune to the spam folder for that mailbox. If anything did
land in spam beforehand, open it and choose **Not spam** so the mailbox learns.

### A caveat about the destination address

The form currently sends to `matt@mattyscafe.com`. Before relying on it, confirm that mailbox
actually exists and is monitored — the address was taken from the previous website and has not
been verified. If it is dead, FormSubmit's activation email never arrives and the form silently
never works. A Gmail address is a safer destination if there is any doubt.

### If guaranteed delivery is required

Sending from the cafe's own domain, with full authentication, needs all of the following:

- A host that can run server-side code (Cloudflare Pages/Workers, Netlify, Vercel — GitHub Pages cannot)
- An account with a transactional email provider (Resend, Amazon SES, Mailgun, SendGrid)
- **DNS control of `mattyscafe.com`**, to publish the provider's DKIM keys, amend SPF, and set DMARC
- A small serverless function to receive the POST, validate server-side, and call the provider's API

This is a different piece of work rather than a change to the current form, and it introduces an
account, a cost, and something to maintain.
