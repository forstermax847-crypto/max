#!/usr/bin/env python3
"""
Static site generator for samantha-williams-breast-surgeon.

Usage:  python3 tools/build.py          (run from the site folder or anywhere)

- Page content lives in tools/pages/*.html as HTML fragments with a small
  front-matter block at the top (between two '---' lines).
- Shared layout (head, nav, footer, cookie banner, JSON-LD) is applied here.
- Output is written next to this tools/ folder: index.html, about.html,
  procedures/*.html, articles/*.html, sitemap.xml, robots.txt.

Edit the CONFIG block below (domain, analytics ID, form endpoint, profile
URLs) and re-run to regenerate every page consistently.
"""
import datetime
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_DIR = os.path.join(ROOT, "tools", "pages")

# --------------------------------------------------------------------------
# CONFIG — the only values that normally need editing
# --------------------------------------------------------------------------
CONFIG = {
    # Set to the real domain (no trailing slash) once decided. While it still
    # contains "REPLACE", canonical/og:url/sitemap URLs are left out or marked.
    "site_url": "https://REPLACE-WITH-DOMAIN.co.uk",
    "ga_measurement_id": "G-XXXXXXXXXX",            # Google Analytics 4
    "form_endpoint": "https://formspree.io/f/REPLACE_WITH_FORM_ID",
    "doctify_url": "",                               # paste exact profile URL
    "bupa_url": "",                                  # paste exact profile URL
    "circle_url": "",                                # paste exact profile URL
    "show_article_draft_notice": True,               # remove after clinical review
}

SITE = {
    "name": "Samantha Williams Breast Surgeon",
    "surgeon": "Miss Samantha Williams",
    "short": "Samantha Williams",
    "title_suffix": " | Samantha Williams Breast Surgeon, Swindon",
    "secretary": "Tracy Greenside",
    "phone_display": "07354 658365",
    "phone_e164": "+447354658365",
    "whatsapp": "447354658365",
    "email": "swilliamsbreastsurgeon@gmail.com",
    "hospital": "BMI The Ridgeway Hospital",
    "street": "Moormead Road",
    "locality": "Wroughton",
    "region": "Swindon",
    "county": "Wiltshire",
    "postcode": "SN4 9DD",
    "gmc": "6130038",
    "lang": "en-GB",
}

TODAY = datetime.date.today().isoformat()


def site_url_ready():
    return "REPLACE" not in CONFIG["site_url"]


def abs_url(path):
    """Absolute URL for a page path, or None while the domain is unset."""
    if not site_url_ready():
        return None
    base = CONFIG["site_url"].rstrip("/")
    if path == "index.html":
        return base + "/"
    return base + "/" + path


# --------------------------------------------------------------------------
# Front matter + fragments
# --------------------------------------------------------------------------
def parse_fragment(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError("Fragment missing front matter")
    meta = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, m.group(2)


def load_pages():
    pages = []
    for name in sorted(os.listdir(PAGES_DIR)):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(PAGES_DIR, name), encoding="utf-8") as f:
            meta, body = parse_fragment(f.read())
        meta["_source"] = name
        meta["body"] = body
        pages.append(meta)
    return pages


def root_prefix(path):
    depth = path.count("/")
    return "../" * depth


# --------------------------------------------------------------------------
# Shared chrome
# --------------------------------------------------------------------------
LOGO_MARK = (
    '<svg class="nav__logo" viewBox="0 0 200 200" aria-hidden="true" focusable="false">'
    '<use href="{root}assets/img/logo-mark.svg#mark"/></svg>'
)


def logo_inline(root):
    # Inline the SVG so it needs no extra request and inherits currentColor.
    with open(os.path.join(ROOT, "assets", "img", "logo-mark.svg"), encoding="utf-8") as f:
        svg = f.read()
    svg = svg.replace('<svg ', '<svg class="nav__logo" aria-hidden="true" focusable="false" ', 1)
    svg = re.sub(r' role="img" aria-label="[^"]*"', "", svg)
    svg = svg.replace("#6E2A38", "currentColor")
    return svg


NAV_ITEMS = [
    ("procedures", "Procedures", "procedures/index.html"),
    ("about", "The Surgeon", "about.html"),
    ("articles", "Articles", "articles/index.html"),
    ("contact", "Contact", "contact.html"),
]

MOBILE_ITEMS = NAV_ITEMS + [
    ("faq", "Questions", "index.html#faq"),
    ("location", "Location", "contact.html#location"),
]


def render_nav(page, root):
    current = page.get("nav", "")
    links = "".join(
        '<a class="nav__link{cur}" href="{root}{href}"{aria}>{label}</a>'.format(
            cur=" is-current" if key == current else "",
            root=root, href=href, label=label,
            aria=' aria-current="page"' if key == current else "",
        )
        for key, label, href in NAV_ITEMS
    )
    mobile = "".join(
        '<a href="{root}{href}">{label}</a>'.format(root=root, href=href, label=label)
        for key, label, href in MOBILE_ITEMS
    )
    return f"""<a class="skip-link" href="#main">Skip to content</a>
<nav class="nav" id="siteNav" aria-label="Main">
  <a class="nav__mark" href="{root}index.html">
    {logo_inline(root)}
    <span class="nav__mark-full">Samantha Williams Breast Surgeon</span>
    <span class="nav__mark-short">Samantha Williams</span>
  </a>
  <div class="nav__links">
    {links}
    <a class="btn" href="{root}contact.html">
      <span class="btn-full">Request a Consultation</span>
      <span class="btn-short">Consult</span>
    </a>
    <button type="button" class="nav__toggle" id="navToggle" aria-expanded="false" aria-controls="mobileMenu" aria-label="Open menu">
      <span></span><span></span><span></span>
    </button>
  </div>
  <div class="mobile-menu" id="mobileMenu">
    {mobile}
  </div>
</nav>"""


PROCEDURE_LINKS = [
    ("Breast augmentation", "procedures/breast-augmentation.html"),
    ("Breast reduction", "procedures/breast-reduction.html"),
    ("Breast uplift", "procedures/breast-uplift.html"),
    ("Breast lump assessment", "procedures/breast-lump-assessment.html"),
    ("Breast cancer surgery", "procedures/breast-cancer-surgery.html"),
    ("Breast reconstruction", "procedures/breast-reconstruction.html"),
]


def profile_links(root):
    items = []
    if CONFIG["doctify_url"]:
        items.append(f'<li><a href="{CONFIG["doctify_url"]}" rel="noopener" target="_blank">Doctify reviews</a></li>')
    if CONFIG["bupa_url"]:
        items.append(f'<li><a href="{CONFIG["bupa_url"]}" rel="noopener" target="_blank">Bupa profile</a></li>')
    if CONFIG["circle_url"]:
        items.append(f'<li><a href="{CONFIG["circle_url"]}" rel="noopener" target="_blank">Circle Health Group profile</a></li>')
    return "".join(items)


def render_footer(root):
    procs = "".join(f'<li><a href="{root}{href}">{label}</a></li>' for label, href in PROCEDURE_LINKS)
    profiles = profile_links(root)
    year = datetime.date.today().year
    return f"""<footer class="footer">
  <div class="wrap">
    <div class="footer__cols">
      <div class="footer__brand">
        <a class="nav__mark" href="{root}index.html">{logo_inline(root)}<span>Samantha Williams Breast Surgeon</span></a>
        <p>{SITE['surgeon']}, Consultant Oncoplastic Breast Surgeon. Private practice at {SITE['hospital']}, {SITE['street']}, {SITE['locality']}, {SITE['region']} {SITE['postcode']}.</p>
        <p>GMC number {SITE['gmc']}</p>
      </div>
      <div>
        <p class="footer__heading">Procedures</p>
        <ul class="footer__links">{procs}</ul>
      </div>
      <div>
        <p class="footer__heading">Practice</p>
        <ul class="footer__links">
          <li><a href="{root}about.html">The surgeon</a></li>
          <li><a href="{root}articles/index.html">Patient articles</a></li>
          <li><a href="{root}index.html#faq">Common questions</a></li>
          <li><a href="{root}index.html#insurers">Fees &amp; insurance</a></li>
          <li><a href="{root}contact.html">Contact &amp; location</a></li>
          {profiles}
        </ul>
      </div>
      <div>
        <p class="footer__heading">Get in touch</p>
        <ul class="footer__links">
          <li><a href="tel:{SITE['phone_e164']}">{SITE['phone_display']}</a></li>
          <li><a href="mailto:{SITE['email']}">{SITE['email']}</a></li>
          <li><a href="https://wa.me/{SITE['whatsapp']}" rel="noopener" target="_blank">WhatsApp {SITE['secretary']}</a></li>
          <li><a href="{root}contact.html#enquiry">Send an enquiry</a></li>
        </ul>
      </div>
    </div>
    <p class="footer__disclaimer">The information on this website is provided for general guidance and does not replace a consultation with a qualified clinician. Every patient is different; suitability, risks and expected outcomes of any procedure can only be assessed in person. If you have a new or worsening breast symptom, please arrange an assessment rather than relying on online information.</p>
    <div class="footer__legal">
      <span>&copy; {year} {SITE['surgeon']}. All rights reserved.</span>
      <span><a href="{root}privacy-policy.html">Privacy &amp; cookies</a> &middot; <a href="{root}complaints.html">Complaints procedure</a></span>
    </div>
  </div>
</footer>

<div class="cookie-banner" id="cookieBanner" role="region" aria-label="Cookie consent">
  <p>We use Google Analytics cookies to understand how the site is used. They are only set if you accept. See our <a href="{root}privacy-policy.html#cookies">privacy &amp; cookie policy</a>.</p>
  <div class="cookie-banner__actions">
    <button type="button" class="btn btn--ghost" id="cookieDecline">Decline</button>
    <button type="button" class="btn" id="cookieAccept">Accept</button>
  </div>
</div>"""


# --------------------------------------------------------------------------
# Structured data
# --------------------------------------------------------------------------
def physician_schema(root):
    data = {
        "@type": "Physician",
        "@id": (abs_url("index.html") or "") + "#physician" if site_url_ready() else "#physician",
        "name": SITE["surgeon"],
        "alternateName": SITE["name"],
        "description": "Consultant Oncoplastic Breast Surgeon offering cosmetic breast surgery, breast lump assessment, breast cancer surgery and reconstruction in private practice at BMI The Ridgeway Hospital, Swindon.",
        "medicalSpecialty": ["Surgical", "Oncologic", "PlasticSurgery"],
        "telephone": SITE["phone_e164"],
        "email": SITE["email"],
        "address": {
            "@type": "PostalAddress",
            "streetAddress": f"{SITE['hospital']}, {SITE['street']}",
            "addressLocality": SITE["locality"],
            "addressRegion": SITE["county"],
            "postalCode": SITE["postcode"],
            "addressCountry": "GB",
        },
        "areaServed": ["Swindon", "Wiltshire", "Oxfordshire", "Gloucestershire", "Bath and North East Somerset", "Berkshire"],
        "hospitalAffiliation": [
            {"@type": "Hospital", "name": "BMI The Ridgeway Hospital", "address": {"@type": "PostalAddress", "addressLocality": "Wroughton", "addressRegion": "Swindon", "postalCode": "SN4 9DD", "addressCountry": "GB"}},
            {"@type": "Hospital", "name": "Great Western Hospital", "address": {"@type": "PostalAddress", "addressLocality": "Swindon", "addressCountry": "GB"}},
        ],
        "memberOf": [
            {"@type": "Organization", "name": "Royal College of Surgeons of England"},
            {"@type": "Organization", "name": "Association of Breast Surgery"},
        ],
        "availableService": [
            {"@type": "MedicalProcedure", "name": label} for label, _ in PROCEDURE_LINKS
        ],
        "isAcceptingNewPatients": True,
    }
    url = abs_url("index.html")
    if url:
        data["url"] = url
        data["image"] = CONFIG["site_url"].rstrip("/") + "/assets/img/og-image.png"
    same_as = [u for u in (CONFIG["doctify_url"], CONFIG["bupa_url"], CONFIG["circle_url"]) if u]
    if same_as:
        data["sameAs"] = same_as
    return data


def breadcrumb_schema(page):
    items = [{"@type": "ListItem", "position": 1, "name": "Home"}]
    if abs_url("index.html"):
        items[0]["item"] = abs_url("index.html")
    pos = 2
    if page.get("parent_title"):
        crumb = {"@type": "ListItem", "position": pos, "name": page["parent_title"]}
        if abs_url(page["parent_path"]):
            crumb["item"] = abs_url(page["parent_path"])
        items.append(crumb)
        pos += 1
    last = {"@type": "ListItem", "position": pos, "name": page.get("h1", page["title"])}
    if abs_url(page["path"]):
        last["item"] = abs_url(page["path"])
    items.append(last)
    return {"@type": "BreadcrumbList", "itemListElement": items}


def faq_schema(body):
    qas = re.findall(r"<details class=\"faq-item\">\s*<summary>(.*?)</summary>\s*(.*?)</details>", body, re.S)
    if not qas:
        return None
    def strip_tags(s):
        return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
    return {
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": strip_tags(q),
             "acceptedAnswer": {"@type": "Answer", "text": strip_tags(a)}}
            for q, a in qas
        ],
    }


def page_schema(page, body):
    graph = []
    ptype = page.get("type", "page")
    if ptype in ("home", "about", "contact"):
        graph.append(physician_schema(root_prefix(page["path"])))
    if ptype == "home" and site_url_ready():
        graph.append({"@type": "WebSite", "name": SITE["name"], "url": abs_url("index.html")})
    if ptype == "about":
        person = {
            "@type": "Person",
            "name": SITE["surgeon"],
            "honorificPrefix": "Miss",
            "jobTitle": "Consultant Oncoplastic Breast Surgeon",
            "worksFor": {"@type": "Hospital", "name": "Great Western Hospital"},
            "alumniOf": {"@type": "CollegeOrUniversity", "name": "Imperial College School of Medicine"},
            "memberOf": [
                {"@type": "Organization", "name": "Royal College of Surgeons of England"},
                {"@type": "Organization", "name": "Association of Breast Surgery"},
                {"@type": "Organization", "name": "Medical Defence Union"},
            ],
            "identifier": {"@type": "PropertyValue", "propertyID": "GMC", "value": SITE["gmc"]},
        }
        graph.append(person)
    if ptype == "procedure":
        proc = {
            "@type": "MedicalProcedure",
            "name": page.get("procedure_name", page.get("h1")),
            "description": page["description"],
            "procedureType": "https://schema.org/SurgicalProcedure" if page.get("surgical", "yes") == "yes" else "https://schema.org/NoninvasiveProcedure",
            "bodyLocation": "Breast",
            "provider": {"@type": "Physician", "name": SITE["surgeon"]},
        }
        if page.get("how_performed"):
            proc["howPerformed"] = page["how_performed"]
        graph.append(proc)
    if ptype == "article":
        art = {
            "@type": "MedicalWebPage",
            "headline": page.get("h1", page["title"]),
            "description": page["description"],
            "datePublished": page.get("published", TODAY),
            "dateModified": TODAY,
            "author": {"@type": "Person", "name": SITE["surgeon"], "jobTitle": "Consultant Oncoplastic Breast Surgeon"},
            "inLanguage": SITE["lang"],
        }
        if abs_url(page["path"]):
            art["url"] = abs_url(page["path"])
        graph.append(art)
    if ptype != "home":
        graph.append(breadcrumb_schema(page))
    faq = faq_schema(body)
    if faq:
        graph.append(faq)
    return {"@context": "https://schema.org", "@graph": graph}


# --------------------------------------------------------------------------
# Page assembly
# --------------------------------------------------------------------------
def render_breadcrumb(page, root):
    if page.get("type") == "home":
        return ""
    crumbs = [f'<li><a href="{root}index.html">Home</a></li>']
    if page.get("parent_title"):
        crumbs.append(f'<li><a href="{root}{page["parent_path"]}">{page["parent_title"]}</a></li>')
    crumbs.append(f'<li aria-current="page">{html.escape(page.get("crumb", page.get("h1", page["title"])))}</li>')
    return '<ol class="breadcrumb">' + "".join(crumbs) + "</ol>"


def render_aside(page, root):
    related = ""
    if page.get("related"):
        items = []
        for pair in page["related"].split(";"):
            label, _, href = pair.strip().partition("|")
            if label and href:
                items.append(f'<li><a href="{root}{href.strip()}">{label.strip()}</a></li>')
        if items:
            related = ('<p class="footer__heading" style="margin-top:0.5rem">Related</p>'
                       f'<ul class="aside-card__links">{"".join(items)}</ul>')
    return f"""<aside class="aside-card" aria-label="Contact and related pages">
  <p class="aside-card__title">Talk it through</p>
  <p>Consultations are unhurried and free of obligation. {SITE['secretary']}, Miss Williams's medical secretary, will arrange a time that suits you.</p>
  <a class="btn" href="{root}contact.html#enquiry">Request a Consultation</a>
  <div class="aside-card__contact">
    <a href="tel:{SITE['phone_e164']}">{SITE['phone_display']}</a>
    <a href="https://wa.me/{SITE['whatsapp']}" rel="noopener" target="_blank">WhatsApp {SITE['secretary']}</a>
    <a href="mailto:{SITE['email']}">{SITE['email']}</a>
  </div>
  {related}
</aside>"""


def render_page(page):
    path = page["path"]
    root = root_prefix(path)
    title = page["title"]
    if not title.endswith("Swindon") and "|" not in title:
        title = title + SITE["title_suffix"]
    desc = page["description"]
    body = page["body"].replace("{{root}}", root)
    body = body.replace("{{breadcrumb}}", render_breadcrumb(page, root))
    body = body.replace("{{aside}}", render_aside(page, root))
    body = body.replace("{{phone_display}}", SITE["phone_display"]).replace("{{phone_e164}}", SITE["phone_e164"])
    body = body.replace("{{email}}", SITE["email"]).replace("{{whatsapp}}", SITE["whatsapp"])
    body = body.replace("{{secretary}}", SITE["secretary"])
    draft = ""
    if page.get("type") == "article" and CONFIG["show_article_draft_notice"]:
        draft = ('<div class="notice notice--muted"><p><strong>Draft for clinical review.</strong> '
                 'This article was prepared for Miss Williams to review and approve before publication.</p></div>')
    body = body.replace("{{draft_notice}}", draft)

    canonical = abs_url(path)
    og_image = (CONFIG["site_url"].rstrip("/") + "/assets/img/og-image.png") if site_url_ready() else None

    head_extra = []
    if canonical:
        head_extra.append(f'<link rel="canonical" href="{canonical}" />')
        head_extra.append(f'<meta property="og:url" content="{canonical}" />')
    if og_image:
        head_extra.append(f'<meta property="og:image" content="{og_image}" />')
        head_extra.append('<meta property="og:image:width" content="1200" />')
        head_extra.append('<meta property="og:image:height" content="630" />')
        head_extra.append('<meta name="twitter:card" content="summary_large_image" />')
    else:
        head_extra.append('<meta name="twitter:card" content="summary" />')
    if page.get("type") == "article":
        head_extra.append('<meta property="og:type" content="article" />')
        head_extra.append(f'<meta property="article:published_time" content="{page.get("published", TODAY)}" />')
    else:
        head_extra.append('<meta property="og:type" content="website" />')

    schema = json.dumps(page_schema(page, body), ensure_ascii=False, indent=None)
    config_js = json.dumps({
        "gaMeasurementId": CONFIG["ga_measurement_id"],
        "formEndpoint": CONFIG["form_endpoint"],
    })

    return f"""<!DOCTYPE html>
<html lang="{SITE['lang']}">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc, quote=True)}" />
<meta name="robots" content="index, follow" />
<meta name="theme-color" content="#ECE6DC" />
<meta property="og:site_name" content="{SITE['name']}" />
<meta property="og:title" content="{html.escape(title, quote=True)}" />
<meta property="og:description" content="{html.escape(desc, quote=True)}" />
<meta property="og:locale" content="en_GB" />
{chr(10).join(head_extra)}
<link rel="icon" type="image/svg+xml" href="{root}assets/img/favicon.svg" />
<link rel="apple-touch-icon" href="{root}assets/img/apple-touch-icon.png" />
<link rel="preload" href="{root}assets/fonts/LibreCaslonDisplay-Regular.woff2" as="font" type="font/woff2" crossorigin />
<link rel="stylesheet" href="{root}assets/css/styles.css" />
<script type="application/ld+json">{schema}</script>
</head>
<body>
{render_nav(page, root)}

<main id="main">
{body}
</main>

{render_footer(root)}

<script>window.SITE_CONFIG = {config_js};</script>
<script src="{root}assets/js/site.js" defer></script>
</body>
</html>
"""


def write(path, content):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def build():
    pages = load_pages()
    for page in pages:
        write(page["path"], render_page(page))
        print("wrote", page["path"])

    # sitemap + robots
    base = CONFIG["site_url"].rstrip("/")
    urls = []
    for page in pages:
        loc = base + "/" if page["path"] == "index.html" else base + "/" + page["path"]
        prio = {"home": "1.0", "procedure": "0.9", "contact": "0.8", "about": "0.8", "article": "0.6"}.get(page.get("type", "page"), "0.4")
        urls.append(f"  <url><loc>{loc}</loc><lastmod>{TODAY}</lastmod><priority>{prio}</priority></url>")
    note = "" if site_url_ready() else "<!-- NOTE: set CONFIG['site_url'] in tools/build.py to the real domain and rebuild before submitting this sitemap. -->\n"
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n' + note +
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n")
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n")
    print("wrote sitemap.xml, robots.txt")


if __name__ == "__main__":
    build()
