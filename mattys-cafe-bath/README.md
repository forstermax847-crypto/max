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
