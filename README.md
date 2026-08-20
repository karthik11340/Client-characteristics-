# Aldermere Private Client Psychology Dashboard

A continuously-updating intelligence system for understanding HNW/UHNW
client profiles — wealth origins, family structures, business interests,
ownership patterns, lifestyle assets, and transition events (exits,
succession, inheritance) — to surface service and partnership
opportunities for Aldermere.

**👉 For step-by-step setup and run instructions, see [GUIDE.md](GUIDE.md).**

## ⚠️ Real data vs. sample/demo data — read this first

The two are now kept in **separate files** so they can never be confused:

| File | Written by | Contains |
|---|---|---|
| `data/hnw_uhnw_database.xlsx` | `run_scraper.py`, `historical_backfill.py` | **Real** collected news |
| `data/sample_data.xlsx` | `generate_sample_data.py` | **Fake** synthetic rows, for previewing the dashboard UI only |

The dashboard always prefers the real file. If only the sample file
exists, it shows a clear red warning banner so you can never mistake a
demo preview for actual results. **There is no row limit in the real
collectors** — `--n 500` is a flag on the *sample generator only*;
`historical_backfill.py` and `run_scraper.py` collect everything they
find that passes the relevance filter, with no cap.

## Before your first real run: validate your sources

RSS feed URLs and site structures drift over time, and this was built
without live access to verify them against the actual news domains.
Before kicking off a long backfill, run:

```bash
python scraper/validate_sources.py
```

This checks every feed in `scraper/sources.py`, tells you which ones are
live and returning entries, and which ones need their URL updated (feeds
move — check the publication's site for their current RSS link if one
shows as broken). It's read-only — doesn't touch your database.

```
hnw_dashboard/
├── scraper/
│   ├── sources.py             # RSS feeds + keyword pre-filter list
│   ├── extractor.py           # rule-based keyword tagger (no API key needed)
│   ├── llm_extractor.py       # optional Claude enrichment (used only if ANTHROPIC_API_KEY is set)
│   ├── storage.py             # shared Excel read/write + resume-point logic
│   ├── validate_sources.py    # diagnostic — checks which RSS feeds are actually reachable
│   ├── sitemap_discovery.py   # 2nd discovery method for backfill — reads each site's sitemap.xml
│   ├── run_scraper.py         # INCREMENTAL collector — current news going forward (RSS-based)
│   ├── historical_backfill.py # HISTORICAL collector — 2000 → present (Scrapling Spider-based)
│   └── generate_sample_data.py# makes fake demo data, saved SEPARATELY from real data (see below)
├── dashboard/
│   └── app.py                 # Streamlit dashboard
├── data/
│   ├── hnw_uhnw_database.xlsx # the growing REAL database (created by the real collectors)
│   ├── sample_data.xlsx       # FAKE demo data (created only by generate_sample_data.py)
│   └── .backfill_checkpoint/  # Scrapling's own in-flight crawl checkpoint (mid-run resume)
├── GUIDE.md                   # full setup/run walkthrough
└── requirements.txt
```

## Two collection modes

| | `run_scraper.py` | `historical_backfill.py` |
|---|---|---|
| Covers | Current news, going forward | 2000 → present |
| Discovery | RSS feeds | Wayback Machine CDX archive **+** each site's sitemap.xml |
| Engine | Sequential (feedparser + Scrapling `Fetcher`) | Concurrent, checkpointed (Scrapling `Spider`) |
| Speed | Fast, run hourly | Slow — hours to days for a full run |
| Resume | ✅ automatic, via Excel | ✅ automatic, via Excel **+** Scrapling's own mid-crawl checkpoint |
| Excel writes | Every 10 new articles | Every 10 new articles |

**Both write to the exact same `data/hnw_uhnw_database.xlsx` file and
schema, and both flush new rows to disk every 10 articles** (not just
at the end) so a long run never risks losing much progress. On every
run, each script reads the Excel file, finds the latest date already
collected **per source**, and only processes anything newer — so
re-running either command after an interruption, tomorrow, or on a
schedule always continues rather than starting over or duplicating
rows. `historical_backfill.py` additionally uses Scrapling's built-in
crawl checkpointing (`data/.backfill_checkpoint/`), so even a
`Ctrl+C` mid-crawl resumes the exact in-flight request queue on restart.

## Quick start

```bash
pip install -r requirements.txt
scrapling install

# Check which RSS feeds are actually working before a long run:
python scraper/validate_sources.py

# Preview the dashboard UI with fake data (optional, not required):
python scraper/generate_sample_data.py --n 500
streamlit run dashboard/app.py

# Then, on a machine with real internet access, run the REAL collectors:
python scraper/historical_backfill.py --start-year 2000   # one-time, slow, no row cap
python scraper/run_scraper.py --interval 60                 # ongoing, fast
```

See **[GUIDE.md](GUIDE.md)** for the full walkthrough, including how to
run these unattended (cron / systemd / Task Scheduler), tuning tips, and
troubleshooting.

## What the dashboard shows

Filter by any combination of:
- **Age bracket**
- **Region** (UK, US, Europe, Middle East, Asia)
- **Wealth acquisition type** — Quick (windfall/exit), Gradual (self-made), Inherited
- **Wealth source / industry** — business exit, tech, real estate, finance, family business, etc.
- **Business interests** — serial entrepreneur, board/non-exec roles, diversified holdings, angel investor
- **Ownership patterns** — sole owner, family-majority stake, PE-backed, trust-held, joint venture
- **Lifestyle assets** — yacht, art collection, private jet, country estate, supercars
- **Family structure** — married, divorced, has children, family-business-involved
- **Life / transition event** — business exit, succession, inheritance, IPO, acquisition, philanthropy, divorce
- **Advisory needs signalled** — tax planning, trust & estate structuring, family governance, philanthropy structuring, and more
- **Event date range** (spans back to 2000 once the historical backfill has run)

Whatever combination you select, the main panel synthesises the matching
articles into a **possible client characteristics profile**: typical
wealth source, acquisition type, business interests, ownership patterns,
lifestyle assets, family structure, transition events, and — most
importantly — **likely advisory opportunities for Aldermere**, plus
charts and the underlying source articles as evidence.

## Notes & limitations

- This is a **keyword/rule-based** system by default — it flags likely
  signals from news text, it does not verify facts. Treat outputs as
  research leads to validate, not confirmed client dossiers. The
  optional Claude enrichment step (see GUIDE.md Step 7) improves
  accuracy on ambiguous cases.
- Respect each publication's terms of service and `robots.txt`. RSS
  feeds are used for current news because they're the
  publisher-sanctioned way to be notified of new content. Historical
  backfill uses the Internet Archive's public Wayback Machine, a
  widely-used research and preservation resource.
- Excel is used as the store per the brief; for higher volumes (many
  thousands of articles) consider swapping `storage.py`'s
  `pandas.read_excel/to_excel` calls for a SQLite backend — nothing else
  in the system needs to change, since every other module only talks to
  `storage.py`.
