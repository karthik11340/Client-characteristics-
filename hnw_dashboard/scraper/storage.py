"""
Shared storage layer used by BOTH run_scraper.py (incremental/RSS) and
historical_backfill.py (2000-to-present). Keeping this in one place means
both scripts write to the exact same schema and can resume from each
other's progress — the Excel file itself is the single source of truth
for "how far have we gotten."
"""
from pathlib import Path
from datetime import timezone

import pandas as pd
from dateutil import parser as dateparser

EXCEL_PATH = Path(__file__).parent.parent / "data" / "hnw_uhnw_database.xlsx"
SAMPLE_EXCEL_PATH = Path(__file__).parent.parent / "data" / "sample_data.xlsx"
SHEET_NAME = "articles"

COLUMNS = [
    "date_collected", "source", "category", "article_title", "article_url",
    "published_date", "published_date_parsed",
    "possible_name", "age_bracket", "region", "net_worth_mentions",
    "wealth_source", "wealth_acquisition_type",
    "business_interests", "ownership_patterns",
    "lifestyle_assets", "family_structure",
    "life_event", "advisory_opportunity", "advisory_needs",
    "relevance_score",
    "llm_person_name", "llm_estimated_age", "llm_region_country",
    "llm_wealth_origin_summary", "llm_family_structure_notes",
    "llm_advisory_opportunity_notes", "raw_summary",
]


def parse_date_safe(value):
    """Best-effort parse of any date-ish string into a tz-aware UTC datetime.
    Returns None if it can't make sense of it — callers should treat that
    as 'unknown date', not crash."""
    if value is None or value == "":
        return None
    try:
        dt = dateparser.parse(str(value), fuzzy=True)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def load_existing(path=None):
    """Load a master Excel file, normalised to the current COLUMNS list
    (missing columns are added as empty so older files still work after a
    schema upgrade). Defaults to the REAL collected-data file — pass
    SAMPLE_EXCEL_PATH explicitly to load demo data instead."""
    path = path or EXCEL_PATH
    if path.exists():
        try:
            df = pd.read_excel(path, sheet_name=SHEET_NAME)
            for col in COLUMNS:
                if col not in df.columns:
                    df[col] = None
            return df[COLUMNS]
        except Exception as e:
            print(f"[warn] could not read existing Excel file ({e}) — starting fresh")
    return pd.DataFrame(columns=COLUMNS)


def save(df, path=None):
    path = path or EXCEL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[COLUMNS]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=SHEET_NAME, index=False)
    print(f"[saved] {len(df)} total rows -> {path}")
    return df


def known_urls(df):
    if df.empty or "article_url" not in df.columns:
        return set()
    return set(df["article_url"].dropna())


def last_collected_date_per_source(df):
    """{source_name: latest published_date_parsed already in the sheet}.
    This is THE resume mechanism — both scripts call this on startup and
    skip anything at or before this point for that source, so re-running
    the same command continues instead of re-processing everything."""
    if df.empty or "published_date_parsed" not in df.columns:
        return {}
    tmp = df.copy()
    tmp["published_date_parsed"] = pd.to_datetime(tmp["published_date_parsed"], errors="coerce", utc=True)
    result = {}
    for source, group in tmp.groupby("source"):
        mx = group["published_date_parsed"].max()
        if pd.notna(mx):
            result[source] = mx.to_pydatetime()
    return result


def append_and_save(existing_df, new_rows, path=None):
    """Concat new_rows onto existing_df and persist. Returns the combined
    dataframe so callers can keep passing it forward (important for the
    backfill script's incremental-save-every-N-rows behaviour)."""
    if not new_rows:
        return existing_df
    new_df = pd.DataFrame(new_rows)
    combined = pd.concat([existing_df, new_df], ignore_index=True)
    return save(combined, path=path)
