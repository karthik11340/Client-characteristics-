# GUIDE — How to Run the Aldermere Private Client Psychology Dashboard

This walks through everything from zero to a working dashboard, in order.
Total first-time setup: ~15 minutes. The historical backfill itself
(2000 → present) is the slow part — see Step 4.

---

## Step 0 — Prerequisites

- **Python 3.10 or newer.** Check with `python3 --version`.
- A machine with **normal internet access** (your laptop, a small VPS,
  a Raspberry Pi — anything that isn't a locked-down sandbox). The
  scraper and backfill scripts need to reach real news sites and
  web.archive.org.
- ~500MB free disk space (mostly for the browser binaries Scrapling installs).

---

## Step 1 — Unzip and install dependencies

```bash
unzip hnw_dashboard.zip
cd hnw_dashboard

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
scrapling install                 # downloads browser binaries — one-time, ~2-3 min
```

If `scrapling install` fails or is slow, you can skip it: the scraper
uses `Fetcher` (plain HTTP), which doesn't need a browser. The browser
install is only a fallback for sites with heavier anti-bot protection.

---

## Step 2 — See it working immediately (sample data) — optional

Before running any real collection, you can generate realistic fake data
so you can try the dashboard right away:

```bash
python scraper/generate_sample_data.py --n 500
streamlit run dashboard/app.py
```

**This writes to `data/sample_data.xlsx` — a completely separate file
from the real database (`data/hnw_uhnw_database.xlsx`).** The dashboard
will show a clear red banner whenever it's displaying sample data
instead of real collected news, so the two can never be confused. Once
you run the real scraper (Steps 3-4), its output automatically takes
priority and the banner disappears.

`--n 500` only controls how many *fake* rows to generate for this
preview — it has no relationship to how much real data the actual
collectors will gather. `historical_backfill.py` and `run_scraper.py`
have no row cap at all; they collect everything that passes the
relevance filter.

---

## Step 2.5 — Validate your sources before a real run

RSS feeds and site structures drift over time. Before kicking off a long
backfill, check which sources in `scraper/sources.py` are actually
reachable and returning results:

```bash
python scraper/validate_sources.py
```

This is read-only — it won't touch your database. Fix or remove any
feed it flags as broken (open the publication's site, find their
current RSS link — often in the footer or at `<domain>/feed` — and
update the URL in `scraper/sources.py`) before running the backfill, so
you're not wasting time backfilling against dead feeds.

---

## Step 3 — Run the incremental scraper (current news, going forward)

This checks each RSS feed in `scraper/sources.py`, keeps anything
relevant, and appends new rows to `data/hnw_uhnw_database.xlsx`.

**One-off run** (good for testing):
```bash
python scraper/run_scraper.py --once
```

**Continuous** (polls every 60 minutes, forever — leave this running):
```bash
python scraper/run_scraper.py --interval 60
```

Every re-run automatically skips articles it's already collected
(by URL) and anything older than the latest date already stored per
source — so it's always safe to stop and restart.

---

## Step 4 — Run the historical backfill (2000 → present)

RSS feeds only ever show recent items, so reaching back to 2000 uses a
different method: the **Internet Archive's Wayback Machine**, which has
archived snapshots of most of these sites going back decades.

```bash
python scraper/historical_backfill.py --start-year 2000
```

**How it finds articles from 2000.** RSS can't reach back that far, so
this script discovers historical URLs two ways for every source:
1. **The Wayback Machine's CDX index** — it can list nearly every URL a
   domain has ever had archived, with a timestamp, back to 2000+. Each
   candidate is fetched from its **archived snapshot** (the page as it
   looked at the time), so historical accuracy doesn't depend on the
   live page still existing decades later.
2. **The site's own sitemap.xml** — picks up current/recent articles
   the Wayback Machine hasn't indexed yet.

It's built on Scrapling's own `Spider` crawling framework (concurrent
requests, per-domain throttling, built-in checkpointing) rather than a
simple one-at-a-time loop — this is meaningfully faster than fetching
pages one by one, while still being polite to each individual site.

**This is slow regardless — plan for it.** A full 2000-to-present run
across every source can still take anywhere from a few hours to a
couple of days, simply because each domain may have thousands of
archived URLs to check, and the crawl deliberately throttles itself per
domain (default: 2 concurrent requests per domain, 1.5s apart) so it
doesn't hammer any single site or the Wayback Machine.

**Two layers of resume, so nothing is ever wasted:**
- **Cross-run (the main one):** every run reads the Excel file, finds
  the latest date already collected **per source**, and only looks for
  articles after that point — both discovery methods respect this. Just
  run the *exact same command* again after stopping:
  ```bash
  python scraper/historical_backfill.py --start-year 2000
  ```
- **Mid-run (a bonus):** while a crawl is actively running, Scrapling
  itself periodically saves its in-flight request queue to
  `data/.backfill_checkpoint/`. If you `Ctrl+C` partway through, the
  *same* command picks the crawl queue back up where it left off — not
  just from the last saved article, but from the exact in-progress
  batch of requests. (Delete that folder if you ever want to force a
  completely clean re-crawl instead.)

Every 10 new articles are saved to the Excel file as they're found —
not just at the end — so even an interrupted run keeps almost
everything it found.

Other useful options:
- Run it in the background so it survives closing your terminal:
  ```bash
  nohup python scraper/historical_backfill.py --start-year 2000 > backfill.log 2>&1 &
  ```
  Check progress any time with `tail -f backfill.log`.
- Split it into chunks by year:
  ```bash
  python scraper/historical_backfill.py --start-year 2000 --end-year 2010
  python scraper/historical_backfill.py --start-year 2010 --end-year 2020
  python scraper/historical_backfill.py --start-year 2020
  ```
- Do it source-by-source, to prioritise the sources that matter most:
  ```bash
  python scraper/historical_backfill.py --source "Spear's" --start-year 2000
  python scraper/historical_backfill.py --source "Family Capital" --start-year 2000
  ```
- Tune speed/politeness:
  ```bash
  python scraper/historical_backfill.py --delay 3 --concurrency 4 --concurrency-per-domain 1   # slower, more polite
  python scraper/historical_backfill.py --delay 0.5 --concurrency 12 --concurrency-per-domain 3  # faster, more aggressive
  ```

Once it's done (or even partway through), refresh the dashboard and
the date-range filter will show real coverage back toward 2000.

---

## Step 5 — Run the dashboard for real

```bash
streamlit run dashboard/app.py
```

The dashboard auto-refreshes its view of the Excel file every 5
minutes, or use Streamlit's `⋮` menu → **Rerun** for an instant refresh
right after a scraper/backfill run finishes.

---

## Step 6 — Keep it running unattended (optional but recommended)

You want two things running continuously in the background:
1. `run_scraper.py --interval 60` (or similar) — stays current
2. `historical_backfill.py` — runs once until it catches up to today, then you're done with it (only needed again if you add new sources)

### macOS / Linux — cron
```bash
crontab -e
```
Add (adjust paths):
```
# Incremental scraper — every hour
0 * * * * cd /path/to/hnw_dashboard && venv/bin/python scraper/run_scraper.py --once >> logs/scraper.log 2>&1
```

### macOS / Linux — systemd (better for long-running processes)
Create `/etc/systemd/system/hnw-scraper.service`:
```ini
[Unit]
Description=HNW/UHNW incremental news scraper
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/hnw_dashboard
ExecStart=/path/to/hnw_dashboard/venv/bin/python scraper/run_scraper.py --interval 60
Restart=always

[Install]
WantedBy=multi-user.target
```
Then:
```bash
sudo systemctl enable --now hnw-scraper
```

### Windows — Task Scheduler
Create a Basic Task → Trigger: **Daily, repeat every 1 hour** → Action:
**Start a program** → Program: `path\to\venv\Scripts\python.exe` →
Arguments: `scraper\run_scraper.py --once` → Start in:
`path\to\hnw_dashboard`.

### Running the dashboard as a persistent service
Same pattern as above but pointing at:
```
streamlit run dashboard/app.py --server.headless true --server.port 8501
```
Then access it at `http://<machine-ip>:8501` from any browser on your
network (or put it behind a reverse proxy if you want it reachable
externally).

---

## Step 7 — (Optional) Better extraction accuracy with Claude

The system works fully standalone using keyword rules. For meaningfully
better name/age/region/wealth-origin extraction on ambiguous articles:

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # Windows: set ANTHROPIC_API_KEY=sk-ant-...
python scraper/run_scraper.py --once
```

Both `run_scraper.py` and `historical_backfill.py` will automatically
pick this up (via `llm_extractor.py`) and enrich each relevant article
with an extra structured pass. No key set = it just skips this step
silently.

---

## Troubleshooting

| Problem | Likely cause / fix |
|---|---|
| `ModuleNotFoundError` on run | You forgot to `source venv/bin/activate`, or `pip install -r requirements.txt` didn't finish — re-run it. |
| Backfill finds very few articles for a source | That domain may not be well-archived by the Wayback Machine, or its article URLs don't contain the path-keywords in `URL_PATH_HINTS` (`scraper/historical_backfill.py`) — add more hints for that domain's URL style. |
| Backfill is very slow | Expected — increase parallelism at your own risk (the script is intentionally sequential + polite), or split by `--source`/`--start-year`/`--end-year` and run several terminals in parallel across *different* sources. |
| Dashboard shows "No data found" | Run Step 2 (sample data) or Step 3/4 (real scraper) first — the Excel file doesn't exist until one of those has run. |
| Dashboard shows a red "SAMPLE / DEMO data" banner | This is correct/expected until you actually run `historical_backfill.py` and/or `run_scraper.py` for real — only `data/sample_data.xlsx` exists so far, not `data/hnw_uhnw_database.xlsx`. Run the real collectors (Steps 3-4) to replace it. |
| Getting rate-limited / blocked by a news site | Increase `--delay` in the relevant script; some sites may need to be dropped from `scraper/sources.py` if they actively block automated access. |
| Excel file looks "stuck" / not updating in dashboard | The dashboard caches for 5 minutes — use `⋮` → Rerun, or restart the Streamlit process. |

---

## Tuning the system over time

- **Add/remove sources:** edit `RSS_SOURCES` in `scraper/sources.py`
  (used by both the incremental scraper and the historical backfill).
- **Add keyword categories or refine matching:** edit the dictionaries
  at the top of `scraper/extractor.py`.
- **Add a new dashboard filter:** any field you add to
  `extractor.analyze_article()`'s return dict becomes a column
  automatically (via `storage.COLUMNS` — add it there too) — then add a
  matching `st.sidebar.multiselect(...)` block in `dashboard/app.py`.
