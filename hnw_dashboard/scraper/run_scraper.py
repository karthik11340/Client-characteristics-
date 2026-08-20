"""
Incremental HNW/UHNW news collector — covers CURRENT news going forward
via RSS. For history back to 2000, run historical_backfill.py instead
(RSS feeds only ever expose recent items, so they can't reach that far
back — that's a separate, Wayback-Machine-based script by design).

Pipeline per run:
  1. Pull every RSS feed in sources.RSS_SOURCES (feedparser).
  2. Skip anything already collected — by URL, AND by resume date (see
     RESUME BEHAVIOUR below).
  3. Pre-filter by RELEVANCE_KEYWORDS so we don't waste fetches on
     irrelevant articles (sports scores, weather, etc.).
  4. Fetch the full article body with Scrapling's Fetcher.
  5. Run extractor.analyze_article() (rule-based) and, if configured,
     llm_extractor.enrich() (Claude).
  6. Append the new rows to the shared Excel workbook.

RESUME BEHAVIOUR
-----------------
On startup this script reads the existing Excel file and finds the
latest `published_date_parsed` already stored per source. Any RSS entry
at or before that date for that source is skipped automatically — so
re-running the exact same command tomorrow, next week, or after a crash
picks up only what's genuinely new. Combined with the URL-dedup check,
this makes the script safe to run on a schedule indefinitely.

Run once:
    python run_scraper.py --once

Run forever, polling every N minutes (default 60):
    python run_scraper.py --interval 60

Requires internet access to the actual news domains — run this on your
own machine / server, not inside a sandboxed environment.
"""
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser

sys.path.insert(0, str(Path(__file__).parent))
from sources import RSS_SOURCES, RELEVANCE_KEYWORDS  # noqa: E402
import extractor  # noqa: E402
import llm_extractor  # noqa: E402
import storage  # noqa: E402


def is_relevant(title, summary):
    text = f"{title} {summary}".lower()
    return any(kw in text for kw in RELEVANCE_KEYWORDS)


def fetch_full_text(url):
    """Best-effort full article text via Scrapling. Returns '' on any failure
    so the pipeline degrades gracefully to title+summary-only extraction."""
    try:
        from scrapling.fetchers import Fetcher
        page = Fetcher.get(url, stealthy_headers=True, timeout=20)
        paragraphs = page.css("article p::text").getall() or page.css("p::text").getall()
        return " ".join(paragraphs)[:8000]
    except Exception as e:
        print(f"  [warn] full-text fetch failed for {url}: {e}")
        return ""


FLUSH_EVERY = 10


def collect_once():
    existing = storage.load_existing()
    seen_urls = storage.known_urls(existing)
    resume_dates = storage.last_collected_date_per_source(existing)
    new_rows = []
    total_added = 0
    pending = []  # buffered rows not yet flushed to Excel

    for feed in RSS_SOURCES:
        resume_from = resume_dates.get(feed["name"])
        if resume_from:
            print(f"[feed] {feed['name']} (resuming after {resume_from.date()})")
        else:
            print(f"[feed] {feed['name']} (no prior data for this source)")

        try:
            parsed = feedparser.parse(feed["url"])
        except Exception as e:
            print(f"  [error] could not parse feed: {e}")
            continue

        for entry in parsed.entries:
            url = entry.get("link")
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            if not url or url in seen_urls:
                continue

            published_dt = storage.parse_date_safe(entry.get("published") or entry.get("updated"))
            if resume_from and published_dt and published_dt <= resume_from:
                continue
            if not is_relevant(title, summary):
                continue

            seen_urls.add(url)
            body = fetch_full_text(url)
            row = extractor.analyze_article(title, summary, body)
            row = llm_extractor.enrich(row, title, summary, body)

            row.update({
                "date_collected": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": feed["name"],
                "category": feed["category"],
                "article_title": title,
                "article_url": url,
                "published_date": entry.get("published", ""),
                "published_date_parsed": published_dt.isoformat() if published_dt else None,
                "raw_summary": summary[:500],
            })
            new_rows.append(row)
            pending.append(row)
            total_added += 1
            print(f"  [+] {title[:80]}")

            # Flush to Excel every 10 new articles, not just at the very
            # end — this run is sequential (one feed/entry at a time), so
            # there's no concurrency race to worry about here.
            if len(pending) >= FLUSH_EVERY:
                existing = storage.append_and_save(existing, pending)
                pending = []

    if pending:
        existing = storage.append_and_save(existing, pending)
    if not new_rows:
        print("[info] no new relevant articles this run")
    return total_added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="run a single collection pass and exit")
    ap.add_argument("--interval", type=int, default=60, help="minutes between runs (default 60)")
    args = ap.parse_args()

    if args.once:
        collect_once()
        return

    print(f"Starting continuous collection, every {args.interval} min. Ctrl+C to stop.")
    while True:
        try:
            collect_once()
        except Exception as e:
            print(f"[error] collection pass failed: {e}")
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
