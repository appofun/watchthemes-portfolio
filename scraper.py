#!/usr/bin/env python3
"""
scraper.py — WatchThemes Portfolio Scraper
Scrapes Google Play developer page, builds premium cards, writes index.html.
"""

import os, re, sys
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
DEVELOPER_PLAY_ID = "6227709911907968502"
USE_NUMERIC_ID    = True

PORTFOLIO_TITLE   = "WatchThemes"
PORTFOLIO_TAGLINE = "Premium Watch Faces & Themes"
CONTACT_EMAIL     = "contact@watchthemes.com"
PLAY_STORE_URL    = f"https://play.google.com/store/apps/dev?id={DEVELOPER_PLAY_ID}"

FALLBACK_APPS: List[dict] = [
    {
        "title":    "Kawaii Watch Face",
        "url":      "https://play.google.com/store/apps/details?id=com.watchfacestudio.my4watchface",
        "icon":     "https://placehold.co/240x240/0e0e16/c8922a?text=KW",
        "rating":   "4.5",
        "price":    "FREE",
        "platform": "Wear OS",
    },
    {
        "title":    "Love Duck Wear OS Watch Face",
        "url":      "https://play.google.com/store/apps/details?id=com.watchfacestudio.FREE",
        "icon":     "https://placehold.co/240x240/0e0e16/c8922a?text=LD",
        "rating":   "4.3",
        "price":    "FREE",
        "platform": "Wear OS",
    },
    {
        "title":    "Skull Dark Watch Face",
        "url":      "https://play.google.com/store/apps/details?id=com.watchfacestudio.faceme3",
        "icon":     "https://placehold.co/240x240/0e0e16/c8922a?text=SD",
        "rating":   "4.6",
        "price":    "$0.99",
        "platform": "Wear OS",
    },
]

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
BASE_URL      = "https://play.google.com"
DEV_PAGE_URL  = f"{BASE_URL}/store/apps/dev?id={DEVELOPER_PLAY_ID}"
ICON_SUFFIX   = "=w240-h240-rw"
TEMPLATE_FILE = "template.html"
OUTPUT_FILE   = "index.html"
PLACEHOLDER   = "<!-- {{APPS_PLACEHOLDER}} -->"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

# Patterns that are noise, not app names
_JUNK = re.compile(
    r"^\s*(\$[\d.]+|€[\d.]+|free|install|rated|[\d,]+\+?|[\d.]+\s*stars?)\s*$",
    re.I,
)
# Price embedded in title
_PRICE = re.compile(r"\s*\$[\d.]+\s*$")


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def clean_icon(raw: str) -> str:
    if not raw:
        return ""
    cleaned = re.sub(r"=[a-zA-Z]?\d+[-=].*$", "", raw.strip())
    cleaned = re.sub(r"=[a-zA-Z]\d+$", "", cleaned)
    return cleaned + ICON_SUFFIX


def detect_platform(title: str, pkg: str) -> str:
    t = title.lower()
    if "wear os" in t or "wear" in t:
        return "Wear OS"
    if "samsung" in t or "galaxy" in t:
        return "Samsung"
    if "watchfacestudio" in pkg:
        return "Watch Face"
    return "Android"


def extract_title(link_tag) -> str:
    label = link_tag.get("aria-label", "").strip()
    if label and len(label) < 120:
        cleaned = _PRICE.sub("", label).strip()
        return cleaned if len(cleaned) > 2 else ""

    candidates = []
    for el in link_tag.find_all(["span", "div"]):
        txt = el.get_text(separator=" ", strip=True)
        if 3 < len(txt) < 120 and not _JUNK.match(txt) and "\n" not in txt:
            candidates.append(txt)

    if candidates:
        filtered = [c for c in candidates if 4 <= len(c) <= 70]
        best = sorted(filtered or candidates, key=len)[0]
        return _PRICE.sub("", best).strip()

    return ""


def extract_icon(link_tag) -> str:
    for img in link_tag.find_all("img"):
        for attr in ("src", "data-src"):
            val = img.get(attr, "")
            if "googleusercontent" in val:
                return clean_icon(val)
        ss = img.get("srcset", "")
        if ss:
            first = ss.split(",")[0].strip().split(" ")[0]
            if "googleusercontent" in first:
                return clean_icon(first)
    return ""


def extract_rating(element) -> Optional[str]:
    node = element
    for _ in range(7):
        if node is None:
            break
        hit = node.find(attrs={"aria-label": re.compile(r"Rated\s+\d", re.I)})
        if hit:
            m = re.search(r"(\d+\.?\d*)", hit.get("aria-label", ""))
            if m:
                return m.group(1)
        node = getattr(node, "parent", None)
    return None


def fetch_missing_icon(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, params={"hl": "en"}, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "play-lh.googleusercontent" in src:
                return clean_icon(src)
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════════════
#  SCRAPER
# ══════════════════════════════════════════════════════════════════════════════

def scrape_apps() -> Optional[List[dict]]:
    print(f"[scraper] Fetching: {DEV_PAGE_URL}")
    try:
        session = requests.Session()
        session.get(BASE_URL, headers=HEADERS, timeout=10)
        resp = session.get(DEV_PAGE_URL, headers=HEADERS, params={"hl": "en", "gl": "US"}, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[scraper] ✗ Network error: {e}")
        return None

    print(f"[scraper]   HTTP {resp.status_code} — {len(resp.text):,} bytes")
    if "play.google.com" not in resp.url or len(resp.text) < 5000:
        print("[scraper] ✗ Blocked or redirected")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    apps: List[dict] = []
    seen: set = set()

    for link in soup.find_all("a", href=re.compile(r"/store/apps/details\?id=")):
        href = link.get("href", "")
        qs = parse_qs(urlparse(href).query)
        pkg = qs.get("id", [None])[0]
        if not pkg or pkg in seen:
            continue
        seen.add(pkg)

        full_url = urljoin(BASE_URL, href)
        title    = extract_title(link)
        icon     = extract_icon(link)
        rating   = extract_rating(link)

        # Extract price from raw aria-label / title before cleaning
        raw_label = link.get("aria-label", "")
        price_m   = re.search(r"\$[\d.]+", raw_label)
        price     = price_m.group(0) if price_m else "FREE"

        if not title:
            title = pkg.split(".")[-1].replace("_", " ").title()

        platform = detect_platform(title, pkg)

        apps.append({
            "title":    title,
            "url":      full_url,
            "icon":     icon,
            "rating":   rating,
            "price":    price,
            "platform": platform,
        })

    if apps:
        print(f"[scraper] ✓ Found {len(apps)} apps")
        for app in apps:
            if not app["icon"] and app["url"]:
                print(f"[scraper]   Fetching icon for: {app['title']}")
                app["icon"] = fetch_missing_icon(app["url"])
        return apps

    print("[scraper] ✗ No apps found")
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  CARD GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def _star_svg():
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" '
            'class="w-3 h-3"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77'
            ' 5.82 21.02 7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>')


def _play_svg():
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" '
            'class="w-3.5 h-3.5 flex-shrink-0"><path d="M3 22V2l19 10L3 22z"/></svg>')


def generate_card(app: dict) -> str:
    title    = app.get("title") or "Watch Face"
    url      = app.get("url")   or "#"
    icon     = app.get("icon")  or "https://placehold.co/80x80/0e0e16/c8922a?text=WF"
    rating   = app.get("rating")
    price    = app.get("price", "FREE")
    platform = app.get("platform", "Watch Face")
    safe     = title.replace('"', '&quot;')
    letter   = title[0].upper() if title else "W"

    # Rating
    rating_html = ""
    if rating:
        try:
            rating_html = f"""
            <div class="flex items-center gap-1 text-amber-400">
              {_star_svg()}
              <span class="text-xs font-semibold">{float(rating):.1f}</span>
            </div>"""
        except ValueError:
            pass

    # Price badge
    is_free   = price.upper() == "FREE"
    price_cls = "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" if is_free else "bg-amber-500/15 text-amber-400 border-amber-500/25"
    price_html = f'<span class="text-[10px] font-bold tracking-widest border px-2 py-0.5 rounded-sm {price_cls}">{price}</span>'

    # Platform badge
    plat_html = f'<span class="text-[10px] text-slate-500 tracking-wider font-medium">{platform.upper()}</span>'

    return f"""
        <div class="card-item group relative flex flex-col bg-[#0e0e16] border border-white/5 rounded-2xl overflow-hidden transition-all duration-300 ease-out hover:-translate-y-1.5 hover:border-amber-500/25 hover:shadow-[0_12px_48px_rgba(200,146,42,0.10)]">

          <!-- Gold top accent line -->
          <div class="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-amber-500/0 to-transparent transition-all duration-500 group-hover:via-amber-500/60"></div>

          <!-- Icon area -->
          <div class="relative p-5 pb-0 flex items-start justify-between gap-3">
            <div class="relative flex-shrink-0">
              <img
                src="{icon}"
                alt="{safe}"
                width="72" height="72"
                loading="lazy"
                class="w-[72px] h-[72px] rounded-xl object-cover ring-1 ring-white/8 shadow-lg"
                onerror="this.onerror=null;this.src='https://placehold.co/72x72/0e0e16/c8922a?text={letter}'"
              >
            </div>
            <div class="flex flex-col items-end gap-1.5 pt-0.5">
              {price_html}
              {plat_html}
            </div>
          </div>

          <!-- Info -->
          <div class="flex flex-col flex-1 p-5 pt-3 gap-4">
            <div>
              <h3 class="text-white font-semibold text-sm leading-snug line-clamp-2 mb-1.5">{title}</h3>
              {rating_html}
            </div>

            <div class="mt-auto">
              <a
                href="{url}"
                target="_blank"
                rel="noopener noreferrer"
                class="flex items-center justify-center gap-2 w-full rounded-lg border border-amber-500/20 bg-amber-500/8 text-amber-400 hover:bg-amber-500 hover:border-amber-500 hover:text-zinc-900 text-xs font-semibold py-2.5 px-3 transition-all duration-200 active:scale-95"
              >
                {_play_svg()}
                View on Google Play
              </a>
            </div>
          </div>
        </div>"""


def build_cards(apps: List[dict]) -> str:
    if not apps:
        return '<p class="col-span-full text-center text-slate-600 py-20 text-sm">No apps found.</p>'
    return "\n".join(generate_card(app) for app in apps)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    apps   = scrape_apps()
    source = "live"
    if not apps:
        print("[scraper] ⚠ Using fallback apps")
        apps, source = FALLBACK_APPS, "fallback"

    print(f"[scraper] Building with {len(apps)} apps ({source})")

    if not os.path.isfile(TEMPLATE_FILE):
        print(f"[scraper] ✗ {TEMPLATE_FILE} not found", file=sys.stderr)
        sys.exit(1)

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        tpl = f.read()

    if PLACEHOLDER not in tpl:
        print(f"[scraper] ✗ Placeholder not found in {TEMPLATE_FILE}", file=sys.stderr)
        sys.exit(1)

    updated_at = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    out = tpl
    out = out.replace("{{PORTFOLIO_TITLE}}",   PORTFOLIO_TITLE)
    out = out.replace("{{PORTFOLIO_TAGLINE}}", PORTFOLIO_TAGLINE)
    out = out.replace("{{DEVELOPER_PLAY_ID}}", DEVELOPER_PLAY_ID)
    out = out.replace("{{CONTACT_EMAIL}}",     CONTACT_EMAIL)
    out = out.replace("{{PLAY_STORE_URL}}",    PLAY_STORE_URL)

    injection = (
        f"\n        <!-- AUTO-GENERATED | {updated_at} | {len(apps)} apps -->\n"
        + build_cards(apps)
        + "\n        <!-- /AUTO-GENERATED -->"
    )
    out = out.replace(PLACEHOLDER, injection)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(out)

    print(f"[scraper] ✓ {OUTPUT_FILE} written ({len(out):,} bytes, {len(apps)} cards)")


if __name__ == "__main__":
    main()
