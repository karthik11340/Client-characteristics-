"""
Historical backfill crawler (2000 -> present) - built on Scrapling's own
Spider framework (scrapling.spiders.Spider) for concurrent, checkpointed
crawling, instead of a hand-rolled request loop.

TWO DISCOVERY METHODS, USED TOGETHER FOR EACH SOURCE
------------------------------------------------------
1. Wayback Machine CDX API - the primary method for reaching back to
   2000. It can list essentially every URL a domain has ever had
   archived, with a timestamp. Candidates are fetched from their
   ARCHIVED SNAPSHOT (not the live page), since that's the article as it
   actually appeared at the time - more historically accurate, and
   doesn't depend on the live page still existing 20 years later.
2. Each site's own sitemap.xml (see sitemap_discovery.py) - picks up
   current/recent articles the Wayback Machine hasn't crawled yet.
   Sitemap URLs are fetched live, since a sitemap only ever lists pages
   that still exist today.

TWO LAYERS OF RESUME
---------------------
1. Cross-run (the important one): on startup, this reads the Excel file
   and finds the latest `published_date_parsed` already stored PER
   SOURCE. Both discovery methods start from that point forward - so
   re-running the exact same command tomorrow, next week, or after a
   crash only looks for what's genuinely new. No separate progress file
   needed; the Excel sheet IS the checkpoint. This is what "start from
   the last entry date" means in practice.
2. Mid-run (a bonus from using Scrapling's Spider class): --crawldir is
   on by default, and the Spider engine itself persists its in-flight
   request queue to disk periodically and on Ctrl+C. If a run gets
   interrupted partway through, restarting the SAME command resumes the
   in-progress crawl queue too, not just the cross-run date checkpoint.

Every 10 newly-scraped articles are flushed to the Excel file (not just
at the end), so a long crawl never risks losing much progress even if it
dies unexpectedly.

Usage:
    python historical_backfill.py --start-year 2000
    python historical_backfill.py --start-year 2000 --end-year 2015
    python historical_backfill.py --source "Spear's"
    python historical_backfill.py --delay 2 --concurrency 4

Run this somewhere with normal internet access - not inside a sandboxed
environment.
"""
import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from scrapling.spiders import Spider, Response, Request

sys.path.insert(0, str(Path(__file__).parent))
from sources import RSS_SOURCES, RELEVANCE_KEYWORDS  # noqa: E402
import extractor  # noqa: E402
import llm_extractor  # noqa: E402
import storage  # noqa: E402
import sitemap_discovery  # noqa: E402

CDX_ENDPOINT = "http://web.archive.org/cdx/search/cdx"
FLUSH_EVERY = 10

URL_PATH_HINTS = [
    "wealth", "rich-list", "richlist", "billionaire", "millionaire", "fortune",
    "family-office", "net-worth", "inherit", "succession", "philanthrop",
    "yacht", "estate", "private-jet", "art-collection", "hnw", "uhnw",
    "entrepreneur", "exit", "acquisition", "ipo",
]


def domain_for(source):
    return urlparse(source["url"]).netloc.replace("www.", "")


def looks_like_article(url):
    low = url.lower()
    return any(hint in low for hint in URL_PATH_HINTS)


def is_relevant_text(title, body):
    text = f"{title} {body}".lower()
    return any(kw in text for kw in RELEVANCE_KEYWORDS)


def fetch_cdx(domain, start_year, end_year, session):
    """Blocking call (wrapped in asyncio.to_thread by the caller) - hits
    the Wayback Machine's CDX index for every archived URL on `domain`
    between start_year and end_year, collapsed to ~1 snapshot per URL."""
    params = {
        "url": domain,
        "matchType": "domain",
        "from": f"{start_year}0101",
        "to": f"{end_year}1231",
        "output": "json",
        "filter": "statuscode:200",
        "collapse": "urlkey",
        "limit": 100000,
        "fl": "timestamp,original",
    }
    try:
        resp = session.get(CDX_ENDPOINT, params=params, timeout=60)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        print(f"  [error] CDX lookup failed for {domain}: {e}")
        return []
    if not rows or len(rows) < 2:
        return []
    header, *data_rows = rows
    return [dict(zip(header, r)) for r in data_rows]


class BackfillSpider(Spider):
    name = "hnw_historical_backfill"
    concurrent_requests = 6
    concurrent_requests_per_domain = 2
    download_delay = 1.5

    def __init__(self, sources, start_year, end_year, resume_dates, seen_urls, **kwargs):
        super().__init__(**kwargs)
        self.sources_to_crawl = sources
        self.start_year = start_year
        self.end_year = end_year
        self.resume_dates = resume_dates
        self.seen_urls = seen_urls
        self._buffer = []
        self._existing_df = storage.load_existing()
        self._http = requests.Session()
        self._http.headers.update({"User-Agent": "Aldermere-HNW-Research-Bot/1.0"})
        self.stats_checked = 0
        self.stats_added = 0
        # Concurrent requests mean on_scraped_item can be called from
        # multiple in-flight coroutines at once. Without this lock, two
        # near-simultaneous flushes can race on writing the same Excel
        # file and corrupt it (confirmed by testing) — every access to
        # self._buffer / the save call is serialized through this lock.
        self._flush_lock = asyncio.Lock()

    async def on_start(self, resuming: bool = False):
        if resuming:
            print(">>> Resuming an interrupted crawl from its in-progress checkpoint...")
        else:
            print(">>> Starting a fresh crawl...")

    async def start_requests(self):
        for src in self.sources_to_crawl:
            domain = domain_for(src)
            resume_from = self.resume_dates.get(src["name"])
            effective_start_year = max(self.start_year, resume_from.year) if resume_from else self.start_year

            if resume_from:
                print(f"\n[{src['name']}] resuming - already have data through {resume_from.date()}")
            else:
                print(f"\n[{src['name']}] no existing data yet - starting fresh from {self.start_year}")

            print(f"[{src['name']}] querying Wayback Machine CDX for {domain}...")
            cdx_records = await asyncio.to_thread(
                fetch_cdx, domain, effective_start_year, self.end_year, self._http
            )
            print(f"[{src['name']}] {len(cdx_records)} archived URLs in range, filtering...")

            n_yielded = 0
            for record in cdx_records:
                url = record.get("original")
                ts = record.get("timestamp")
                if not url or not ts or url in self.seen_urls:
                    continue
                try:
                    snap_dt = datetime.strptime(ts[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if resume_from and snap_dt <= resume_from:
                    continue
                if not looks_like_article(url):
                    continue

                self.seen_urls.add(url)
                snapshot_url = f"https://web.archive.org/web/{ts}/{url}"
                n_yielded += 1
                yield Request(
                    snapshot_url,
                    callback=self.parse,
                    meta={"source": src, "original_url": url,
                          "published_date": snap_dt, "discovery": "wayback"},
                )
            print(f"[{src['name']}] {n_yielded} Wayback candidates queued")

            print(f"[{src['name']}] checking sitemap.xml for additional articles...")
            sitemap_urls = await asyncio.to_thread(
                sitemap_discovery.discover, domain, effective_start_year, self._http
            )
            n_sitemap_yielded = 0
            for url, date in sitemap_urls:
                if url in self.seen_urls:
                    continue
                if resume_from and date and date <= resume_from:
                    continue
                if not looks_like_article(url):
                    continue

                self.seen_urls.add(url)
                n_sitemap_yielded += 1
                yield Request(
                    url, callback=self.parse,
                    meta={"source": src, "original_url": url,
                          "published_date": date, "discovery": "sitemap"},
                )
            print(f"[{src['name']}] {n_sitemap_yielded} sitemap candidates queued "
                  f"({len(sitemap_urls)} total sitemap URLs found)")

    async def parse(self, response: Response):
        self.stats_checked += 1
        meta = response.meta
        title = (response.css("h1::text").get() or response.css("title::text").get() or "").strip()
        paragraphs = response.css("article p::text").getall() or response.css("p::text").getall()
        body = " ".join(paragraphs)[:8000]

        if not is_relevant_text(title, body):
            return

        row = extractor.analyze_article(title, "", body)
        row = llm_extractor.enrich(row, title, "", body)

        published_dt = meta.get("published_date")
        src = meta["source"]
        row.update({
            "date_collected": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": src["name"],
            "category": src["category"],
            "article_title": title or "(untitled)",
            "article_url": meta["original_url"],
            "published_date": published_dt.date().isoformat() if published_dt else "",
            "published_date_parsed": published_dt.isoformat() if published_dt else None,
            "raw_summary": body[:500],
        })
        self.stats_added += 1
        print(f"  [+] ({meta['discovery']}) {src['name']}: {title[:65]}")
        yield row

    async def on_scraped_item(self, item):
        async with self._flush_lock:
            self._buffer.append(item)
            if len(self._buffer) >= FLUSH_EVERY:
                await self._flush_locked()
        return item

    async def on_close(self):
        async with self._flush_lock:
            if self._buffer:
                await self._flush_locked()
        print(f"\n{'=' * 70}\nDone - {self.stats_checked} candidate pages fetched & checked, "
              f"{self.stats_added} relevant articles added.\n{'=' * 70}")

    async def _flush_locked(self):
        """Caller must already hold self._flush_lock."""
        rows, self._buffer = self._buffer, []
        self._existing_df = await asyncio.to_thread(storage.append_and_save, self._existing_df, rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2000)
    ap.add_argument("--end-year", type=int, default=datetime.now().year)
    ap.add_argument("--source", type=str, default=None, help="only backfill this one source (by name)")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests, per domain")
    ap.add_argument("--concurrency", type=int, default=6, help="global concurrent requests")
    ap.add_argument("--concurrency-per-domain", type=int, default=2)
    ap.add_argument("--crawldir", type=str,
                     default=str(Path(__file__).parent.parent / "data" / ".backfill_checkpoint"),
                     help="where Scrapling persists its in-flight request queue for Ctrl+C resume; "
                          "pass an empty string to disable mid-run checkpointing")
    args = ap.parse_args()

    sources = RSS_SOURCES if not args.source else [s for s in RSS_SOURCES if s["name"] == args.source]
    if not sources:
        print(f"[error] no matching source for '{args.source}'")
        return

    existing = storage.load_existing()
    resume_dates = storage.last_collected_date_per_source(existing)
    seen_urls = storage.known_urls(existing)

    BackfillSpider.download_delay = args.delay
    BackfillSpider.concurrent_requests = args.concurrency
    BackfillSpider.concurrent_requests_per_domain = args.concurrency_per_domain

    spider = BackfillSpider(
        sources=sources,
        start_year=args.start_year,
        end_year=args.end_year,
        resume_dates=resume_dates,
        seen_urls=seen_urls,
        crawldir=(args.crawldir or None),
    )
    result = spider.start()
    print(f"\nCrawl {'completed' if result.completed else 'paused (interrupted -- rerun the same command to resume)'}.")


if __name__ == "__main__":
    main()
