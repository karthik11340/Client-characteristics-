"""
Diagnostic script — checks every source in sources.py and reports
whether it's actually reachable and returning entries, BEFORE you kick
off a long historical backfill.

Why this exists: RSS feed URLs go stale, get redirected, or change
format over time, and I (the code that wrote this) has no live internet
access to news domains to verify them at build time — only you, running
this on your own machine, can confirm which feeds are currently good.

Run this first, on the machine you'll actually run the scraper from:

    python scraper/validate_sources.py

It will NOT write anything to your database — it's read-only / diagnostic.
"""
import sys
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests

sys.path.insert(0, str(Path(__file__).parent))
from sources import RSS_SOURCES, SEED_URLS  # noqa: E402


def check_feed(feed):
    print(f"\n[{feed['name']}] {feed['url']}")
    try:
        parsed = feedparser.parse(feed["url"])
    except Exception as e:
        print(f"  ❌ feedparser raised an exception: {e}")
        return False

    status = getattr(parsed, "status", None)
    bozo = getattr(parsed, "bozo", 0)
    n_entries = len(parsed.entries)

    if status and status >= 400:
        print(f"  ❌ HTTP {status} — feed URL is likely wrong or moved")
        return False
    if n_entries == 0:
        print(f"  ⚠️  0 entries returned (bozo={bozo}) — feed may be empty, "
              f"blocked, or the URL format changed")
        return False

    print(f"  ✅ {n_entries} entries found (HTTP {status or 'n/a'})")
    print(f"     Most recent: \"{parsed.entries[0].get('title', '?')[:70]}\"")
    return True


def check_domain_reachable(url):
    domain = urlparse(url).netloc
    try:
        resp = requests.head(url, timeout=10, allow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0"})
        print(f"  ✅ {domain} reachable (HTTP {resp.status_code})")
        return True
    except Exception as e:
        print(f"  ❌ {domain} unreachable: {e}")
        return False


def main():
    print("=" * 70)
    print("VALIDATING RSS SOURCES")
    print("=" * 70)
    good, bad = [], []
    for feed in RSS_SOURCES:
        if check_feed(feed):
            good.append(feed["name"])
        else:
            bad.append(feed["name"])

    if SEED_URLS:
        print("\n" + "=" * 70)
        print("CHECKING NON-RSS SEED URLS (used only as direct crawl targets)")
        print("=" * 70)
        for seed in SEED_URLS:
            print(f"\n[{seed['name']}] {seed['url']}")
            check_domain_reachable(seed["url"])

    print("\n" + "=" * 70)
    print(f"SUMMARY: {len(good)}/{len(RSS_SOURCES)} feeds working")
    print("=" * 70)
    if good:
        print("Working:    " + ", ".join(good))
    if bad:
        print("Not working:" + " " + ", ".join(bad))
        print("\nFor broken feeds: open the publication's site in a browser, look for")
        print("their current RSS link (often in the footer, or try <domain>/feed or")
        print("<domain>/rss), and update the url in scraper/sources.py. Or just remove")
        print("that entry — the rest of the system works fine with fewer sources, it")
        print("just means less coverage.")


if __name__ == "__main__":
    main()
