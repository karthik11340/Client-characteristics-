"""
Sitemap-based discovery — a SECOND way (alongside the Wayback Machine) to
find article URLs for a domain, using the site's own sitemap.xml.

Sitemaps only ever reflect pages that exist RIGHT NOW — they can't reach
back to 2000 the way Wayback Machine snapshots can — but they're often
more complete for anything still live, including articles published
very recently that the Wayback Machine hasn't crawled yet. Using both
together gives broader coverage than either alone.
"""
from datetime import datetime, timezone
from xml.etree import ElementTree

COMMON_SITEMAP_PATHS = [
    "/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml",
    "/news-sitemap.xml", "/post-sitemap.xml", "/sitemap-news.xml",
]

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _fetch_xml(url, session, timeout=15):
    try:
        resp = session.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200 or not resp.content:
            return None
        return ElementTree.fromstring(resp.content)
    except Exception:
        return None


def _extract_urls(root, start_year):
    out = []
    for url_el in root.findall(".//sm:url", NS):
        loc = url_el.find("sm:loc", NS)
        lastmod = url_el.find("sm:lastmod", NS)
        if loc is None or not loc.text:
            continue
        date = None
        if lastmod is not None and lastmod.text:
            try:
                date = datetime.fromisoformat(lastmod.text.strip().replace("Z", "+00:00"))
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
            except Exception:
                date = None
        if date and date.year < start_year:
            continue
        out.append((loc.text.strip(), date))
    return out


def discover(domain, start_year, session, max_sub_sitemaps=40):
    """Returns a list of (url, published_date_or_None) tuples found via
    the domain's sitemap(s). Best-effort — returns [] if the site has no
    discoverable sitemap at any of the common paths."""
    base = f"https://{domain}"
    results = []

    for path in COMMON_SITEMAP_PATHS:
        root = _fetch_xml(base + path, session)
        if root is None:
            continue
        tag = root.tag.lower()

        if tag.endswith("sitemapindex"):
            sub_locs = [el.text for el in root.findall(".//sm:sitemap/sm:loc", NS) if el.text]
            for sub_url in sub_locs[:max_sub_sitemaps]:
                sub_root = _fetch_xml(sub_url, session)
                if sub_root is not None:
                    results.extend(_extract_urls(sub_root, start_year))
        elif tag.endswith("urlset"):
            results.extend(_extract_urls(root, start_year))

        if results:
            break  # found a working sitemap — no need to try the other common paths too

    return results
