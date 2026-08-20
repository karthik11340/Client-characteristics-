"""
Aldermere Private Client Psychology Dashboard
Reads the Excel database the scraper builds up over time, lets you filter
by client characteristics (age, region, wealth acquisition type, wealth
source, lifestyle assets, life event...), and synthesises the filtered
subset into a "possible client characteristics" profile — the common
patterns, needs, and advisory opportunities for that segment.
Run:
streamlit run dashboard/app.py
"""

from pathlib import Path
from collections import Counter
import zipfile
import pandas as pd
import streamlit as st
import plotly.express as px
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))
import storage  # noqa: E402

from pathlib import Path

REAL_DATA_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "hmw_uhmw_database.xlsx"
)
SAMPLE_DATA_PATH = storage.SAMPLE_EXCEL_PATH

st.set_page_config(
    page_title="Aldermere | Private Client Psychology Dashboard",
    layout="wide", 
    page_icon="🧭"
)

# ----------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------
@st.cache_data(ttl=300)
def load_data(path):
    if not path.exists():
        return pd.DataFrame()
    
    # Catch corrupted Excel files (EOFError / BadZipFile)
    try:
        df = pd.read_excel(path)
    except (EOFError, zipfile.BadZipFile):
        raise RuntimeError(f"CORRUPTED_EXCEL:{path.name}")
    except Exception as e:
        raise RuntimeError(f"READ_ERROR:{path.name}:{str(e)}")

    df["date_collected"] = pd.to_datetime(df["date_collected"], errors="coerce", utc=True)
    if "published_date_parsed" in df.columns:
        df["published_date_parsed"] = pd.to_datetime(df["published_date_parsed"], errors="coerce", utc=True)
    return df

def split_multi(series):
    """Fields like wealth_source hold comma-separated multi-tags — explode them
    into a flat list of individual tags for filtering / counting."""
    out = []
    for val in series.dropna():
        out.extend([v.strip() for v in str(val).split(",") if v.strip()])
    return out

def unique_multi_values(df, col):
    return sorted(set(split_multi(df[col]))) if col in df.columns else []

def row_matches_multi(cell, selected):
    if pd.isna(cell):
        return False
    cell_values = {v.strip() for v in str(cell).split(",")}
    return bool(cell_values & set(selected))

# ----------------------------------------------------------------------
# Load — REAL collected data takes priority over sample/demo data, and
# we make it unmistakable which one is on screen.
# ----------------------------------------------------------------------
real_exists = REAL_DATA_PATH.exists()
sample_exists = SAMPLE_DATA_PATH.exists()

st.title("🧭 Aldermere — Private Client Psychology Dashboard")
st.caption(
    "Filter by client characteristics to surface the likely profile, needs, and "
    "advisory opportunities for that HNW/UHNW segment, based on collected news intelligence."
)

if not real_exists and not sample_exists:
    st.warning(
        "No data yet. Run the real collectors first "
        "(`python scraper/historical_backfill.py --start-year 2000` and/or "
        "`python scraper/run_scraper.py --once`), or generate a demo preview "
        "(`python scraper/generate_sample_data.py`)."
    )
    st.stop()

if real_exists:
    DATA_PATH = REAL_DATA_PATH
else:
    DATA_PATH = SAMPLE_DATA_PATH
    st.error(
        "⚠️  Showing SAMPLE / DEMO data — this is NOT real collected news. "
        "No real collection has run yet on this machine  "
        "( `data/hnw_uhnw_database.xlsx`  doesn't exist). Run  "
        " `python scraper/historical_backfill.py --start-year 2000`  and/or  "
        " `python scraper/run_scraper.py --once`  on a machine with internet  "
        "access, then reload this page. "
    )

if real_exists and sample_exists:
    st.sidebar.caption("ℹ️ Sample demo data also exists on disk but isn't shown — "
                       "real collected data takes priority.")

# --- GRACEFUL ERROR HANDLING FOR CORRUPTED FILES ---
try:
    df = load_data(DATA_PATH)
except RuntimeError as e:
    err_msg = str(e)
    if err_msg.startswith("CORRUPTED_EXCEL:"):
        fname = err_msg.split(":")[1]
        st.error(f"❌ **Corrupted Database File:** `{fname}` is incomplete or corrupted. "
                 "This usually happens if the scraper was interrupted while writing to the file, "
                 "or if the file is currently open in Excel. "
                 "Please close Excel, delete/rename the corrupted file, and run the scraper again to regenerate it.")
    else:
        st.error(f"❌ **Error loading data:** {err_msg}")
    st.stop()
# ---------------------------------------------------

if df.empty:
    st.warning(f"`{DATA_PATH.name}` exists but has no rows yet.")
    st.stop()

# ----------------------------------------------------------------------
# Sidebar Filters
# ----------------------------------------------------------------------
st.sidebar.header("🔎 Client Filters")
st.sidebar.caption("Set any combination — results update the profile below.")

# --- Age ---
age_options = sorted(df["age_bracket"].dropna().unique().tolist())
sel_age = st.sidebar.multiselect("Client age bracket", age_options)

# --- Region ---
region_options = unique_multi_values(df, "region")
sel_region = st.sidebar.multiselect("Region", region_options)

# --- Wealth acquisition type ---
acq_options = unique_multi_values(df, "wealth_acquisition_type")
sel_acq = st.sidebar.multiselect("Wealth acquisition type", acq_options)

# --- Wealth source / industry ---
source_options = unique_multi_values(df, "wealth_source")
sel_source = st.sidebar.multiselect("Wealth source / industry", source_options)

# --- Business interests ---
business_options = unique_multi_values(df, "business_interests")
sel_business = st.sidebar.multiselect("Business interests", business_options)

# --- Ownership patterns ---
ownership_options = unique_multi_values(df, "ownership_patterns")
sel_ownership = st.sidebar.multiselect("Ownership patterns", ownership_options)

# --- Lifestyle assets ---
asset_options = unique_multi_values(df, "lifestyle_assets")
sel_assets = st.sidebar.multiselect("Lifestyle assets", asset_options)

# --- Family structure ---
family_options = unique_multi_values(df, "family_structure")
sel_family = st.sidebar.multiselect("Family structure", family_options)

# --- Life event ---
event_options = unique_multi_values(df, "life_event")
sel_event = st.sidebar.multiselect("Life / transition event", event_options)

# --- Advisory needs ---
needs_options = unique_multi_values(df, "advisory_needs")
sel_needs = st.sidebar.multiselect("Advisory needs signalled", needs_options)

# --- Date range ---
date_col = "published_date_parsed" if df["published_date_parsed"].notna().any() else "date_collected"
if df[date_col].notna().any():
    min_d, max_d = df[date_col].min().date(), df[date_col].max().date()
    date_range = st.sidebar.date_input("Event date range", (min_d, max_d), min_value=min_d, max_value=max_d)
else:
    date_range = None

# ----------------------------------------------------------------------
# Apply filters
# ----------------------------------------------------------------------
filtered = df.copy()

if sel_age:
    filtered = filtered[filtered["age_bracket"].isin(sel_age)]
if sel_region:
    filtered = filtered[filtered["region"].apply(lambda c: row_matches_multi(c, sel_region))]
if sel_acq:
    filtered = filtered[filtered["wealth_acquisition_type"].apply(lambda c: row_matches_multi(c, sel_acq))]
if sel_source:
    filtered = filtered[filtered["wealth_source"].apply(lambda c: row_matches_multi(c, sel_source))]
if sel_business:
    filtered = filtered[filtered["business_interests"].apply(lambda c: row_matches_multi(c, sel_business))]
if sel_ownership:
    filtered = filtered[filtered["ownership_patterns"].apply(lambda c: row_matches_multi(c, sel_ownership))]
if sel_assets:
    filtered = filtered[filtered["lifestyle_assets"].apply(lambda c: row_matches_multi(c, sel_assets))]
if sel_family:
    filtered = filtered[filtered["family_structure"].apply(lambda c: row_matches_multi(c, sel_family))]
if sel_event:
    filtered = filtered[filtered["life_event"].apply(lambda c: row_matches_multi(c, sel_event))]
if sel_needs:
    filtered = filtered[filtered["advisory_needs"].apply(lambda c: row_matches_multi(c, sel_needs))]

if date_range and len(date_range) == 2:
    start = pd.Timestamp(date_range[0], tz="UTC")
    end = pd.Timestamp(date_range[1], tz="UTC") + pd.Timedelta(days=1)
    filtered = filtered[(filtered[date_col] >= start) & (filtered[date_col] < end)]

st.sidebar.markdown("---")
st.sidebar.metric("Matching articles", len(filtered))

# ----------------------------------------------------------------------
# Headline profile summary
# ----------------------------------------------------------------------
def top_n(series_multi, n=5):
    counts = Counter(split_multi(series_multi))
    total = sum(counts.values()) or 1
    return [(label, cnt, cnt / total) for label, cnt in counts.most_common(n)]

st.markdown("## 👤 Possible Client Characteristics")

if filtered.empty:
    st.info("No articles match this filter combination yet. Loosen the filters, "
            "or let the scraper collect more data.")
else:
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Typical wealth source**")
        for label, cnt, pct in top_n(filtered["wealth_source"]):
            st.write(f"- {label} — {pct:.0%} ({cnt})")
            
        st.markdown("**Typical acquisition type**")
        for label, cnt, pct in top_n(filtered["wealth_acquisition_type"]):
            st.write(f"- {label} — {pct:.0%} ({cnt})")
            
        st.markdown("**Business interests**")
        biz = top_n(filtered["business_interests"])
        if biz:
            for label, cnt, pct in biz:
                st.write(f"- {label} — {pct:.0%} ({cnt})")
        else:
            st.write("_Not enough signal in this segment_")

    with col2:
        st.markdown("**Common lifestyle assets**")
        assets = top_n(filtered["lifestyle_assets"])
        if assets:
            for label, cnt, pct in assets:
                st.write(f"- {label} — {pct:.0%} ({cnt})")
        else:
            st.write("_No specific lifestyle assets flagged in this segment_")
            
        st.markdown("**Common family structure**")
        fam = top_n(filtered["family_structure"])
        if fam:
            for label, cnt, pct in fam:
                st.write(f"- {label} — {pct:.0%} ({cnt})")
        else:
            st.write("_Not enough signal in this segment_")
            
        st.markdown("**Ownership patterns**")
        own = top_n(filtered["ownership_patterns"])
        if own:
            for label, cnt, pct in own:
                st.write(f"- {label} — {pct:.0%} ({cnt})")
        else:
            st.write("_Not enough signal in this segment_")

    with col3:
        st.markdown("**Common transition / life events**")
        for label, cnt, pct in top_n(filtered["life_event"]):
            st.write(f"- {label} — {pct:.0%} ({cnt})")
            
        st.markdown("**➡️ Likely advisory opportunities for Aldermere**")
        opp_counter = Counter()
        if "advisory_opportunity" in filtered.columns:
            for val in filtered["advisory_opportunity"].dropna():
                for opp in str(val).split(";"):
                    opp_counter[opp.strip()] += 1
                    
        if opp_counter:
            for opp, cnt in opp_counter.most_common(5):
                st.write(f"- {opp} ({cnt} signals)")
        else:
            st.write("_No advisory signals detected in this segment yet_")
            
        st.markdown("**Ongoing advisory needs signalled**")
        needs = top_n(filtered["advisory_needs"])
        if needs:
            for label, cnt, pct in needs:
                st.write(f"- {label} — {pct:.0%} ({cnt})")
        else:
            st.write("_Not enough signal in this segment_")

    st.markdown("---")
    
    # --- Visual breakdown ---
    v1, v2 = st.columns(2)
    with v1:
        src_counts = Counter(split_multi(filtered["wealth_source"]))
        if src_counts:
            fig = px.pie(names=list(src_counts.keys()), values=list(src_counts.values()),
                         title="Wealth source mix in this segment", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            
    with v2:
        evt_counts = Counter(split_multi(filtered["life_event"]))
        if evt_counts:
            fig2 = px.bar(x=list(evt_counts.keys()), y=list(evt_counts.values()),
                          title="Transition events in this segment",
                          labels={"x": "Life event", "y": "Article count"})
            st.plotly_chart(fig2, use_container_width=True)

    # --- Underlying evidence ---
    with st.expander(f"📰 View the {len(filtered)} matching articles behind this profile"):
        show_cols = ["published_date", "source", "article_title", "possible_name", "age_bracket",
                     "region", "wealth_source", "wealth_acquisition_type", "business_interests",
                     "ownership_patterns", "lifestyle_assets", "family_structure", "life_event",
                     "advisory_opportunity", "advisory_needs", "article_url"]
        show_cols = [c for c in show_cols if c in filtered.columns]
        st.dataframe(filtered[show_cols].sort_values("published_date", ascending=False),
                     use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Download this filtered segment as CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        file_name="aldermere_client_segment.csv",
        mime="text/csv",
    )

# ----------------------------------------------------------------------
# Footer
# ----------------------------------------------------------------------
st.markdown("---")
coverage = ""
if df["published_date_parsed"].notna().any():
    coverage = (f" · coverage: {df['published_date_parsed'].min().date()} "
                f"to {df['published_date_parsed'].max().date()} ")

st.caption(
    f"Database: {len(df)} total collected articles{coverage} · "
    f"Last refreshed from `{DATA_PATH.name}` (cache refreshes every 5 min — "
    "use the ⋮ menu → Rerun for an instant refresh after the scraper runs). "
)
