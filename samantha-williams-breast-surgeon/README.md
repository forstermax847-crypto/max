# Samantha Williams Breast Surgeon — website

Static multi-page site. Upload the whole folder (except `tools/`) to any web host.

## Editing content

Page content lives in `tools/pages/*.html` (an HTML fragment with a small front-matter block).
Shared header, footer, nav, SEO tags and structured data are applied by the generator:

    python3 tools/build.py

Re-run after any change to `tools/pages/` or the CONFIG block. Never edit the generated
`*.html` files directly — they are overwritten on the next build.

## Before going live — settings in `tools/build.py` → CONFIG

| Setting | What to put there |
|---|---|
| `site_url` | The real domain, e.g. `https://www.example.co.uk`. Until set, canonical/og:url tags are omitted and the sitemap carries a placeholder. |
| `ga_measurement_id` | Google Analytics 4 ID (`G-XXXXXXXXXX`). Analytics only loads after the visitor accepts cookies. |
| `form_endpoint` | Form-handling endpoint (e.g. Formspree: create a form, paste its URL). Until set, the enquiry form shows a "not connected" message instead of submitting. |
| `doctify_url`, `bupa_url`, `circle_url` | Exact profile URLs. Links appear in the footer and in structured data only when filled in. |
| `show_article_draft_notice` | Set to `False` once Miss Williams has clinically reviewed the four articles. |

Also complete the two placeholders marked "To complete before publication" in
`tools/pages/privacy-policy.html` (ICO registration) and `tools/pages/complaints.html`
(hospital complaints contact details).

## Assets

- `assets/css/styles.css` — all styling (light theme only)
- `assets/js/site.js` — nav, carousel, cookie consent, analytics loader, enquiry form
- `assets/fonts/` — Libre Caslon Display (OFL licence), woff2 + ttf
- `assets/img/` — monogram logo (`logo-mark.svg`), favicon, touch icon, social preview (`og-image.png`), portrait

## Recommended next steps

1. Register the domain and set `site_url`; submit `sitemap.xml` in Google Search Console.
2. Create a Google Business Profile for the private practice using exactly the name, address and
   phone number shown on the contact page (consistency matters for local search).
3. Replace `assets/img/samantha-williams.png` with a professional headshot (same filename, square).
4. Have Miss Williams review all clinical copy, then set `show_article_draft_notice = False`.
