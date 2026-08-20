"""
Creates data/hnw_uhnw_database.xlsx pre-populated with realistic synthetic
rows spanning 2000-present, matching exactly the schema the real scraper
produces (storage.COLUMNS). Use this to demo/test the dashboard before
your real backfill + incremental scraper have collected live data.

    python generate_sample_data.py --n 500
"""
import argparse
import random
from datetime import datetime, timedelta, timezone

import storage
from extractor import (WEALTH_SOURCE_KEYWORDS, ACQUISITION_TYPE_KEYWORDS,
                        REGION_KEYWORDS, LIFESTYLE_ASSET_KEYWORDS,
                        FAMILY_STRUCTURE_KEYWORDS, LIFE_EVENT_KEYWORDS,
                        BUSINESS_INTERESTS_KEYWORDS, OWNERSHIP_PATTERN_KEYWORDS,
                        ADVISORY_NEEDS_KEYWORDS, ADVISORY_OPPORTUNITY_MAP)

random.seed(42)

SOURCES = ["Spear's", "Wealth Briefing", "Family Capital", "Campden FB",
           "Citywire Wealth Manager", "Robb Report", "FT Adviser", "Forbes - Billionaires"]
FIRST = ["James", "Oliver", "Charlotte", "Amara", "Wei", "Sofia", "Henry", "Isabella",
         "Rashid", "Elena", "Thomas", "Priya", "William", "Grace", "Mohammed", "Anna"]
LAST = ["Whitfield", "Hartley", "Osei", "Chen", "Abernathy", "Rossi", "Kensington",
        "Nakamura", "Al-Farsi", "Beaumont", "Sinclair", "Moretti", "Sørensen", "Delacroix"]

AGE_BRACKETS = ["20-29", "30-39", "40-49", "50-59", "60-69", "70-79"]
START = datetime(2000, 1, 1, tzinfo=timezone.utc)
END = datetime.now(timezone.utc)
SPAN_DAYS = (END - START).days


def rand_row():
    name = f"{random.choice(FIRST)} {random.choice(LAST)}"
    published_dt = START + timedelta(days=random.randint(0, SPAN_DAYS))

    age_bracket = random.choice(AGE_BRACKETS)
    region = random.choice(list(REGION_KEYWORDS.keys()))
    wealth_source = random.choice(list(WEALTH_SOURCE_KEYWORDS.keys()))
    acquisition = random.choice(list(ACQUISITION_TYPE_KEYWORDS.keys()))
    business_interest = random.choice(list(BUSINESS_INTERESTS_KEYWORDS.keys()))
    ownership = random.choice(list(OWNERSHIP_PATTERN_KEYWORDS.keys()))

    n_assets = random.randint(0, 3)
    lifestyle_assets = ", ".join(random.sample(list(LIFESTYLE_ASSET_KEYWORDS.keys()), k=n_assets)) or None
    n_family = random.randint(0, 2)
    family = ", ".join(random.sample(list(FAMILY_STRUCTURE_KEYWORDS.keys()), k=n_family)) or None
    n_needs = random.randint(0, 2)
    advisory_needs = ", ".join(random.sample(list(ADVISORY_NEEDS_KEYWORDS.keys()), k=n_needs)) or None

    life_event = random.choice(list(LIFE_EVENT_KEYWORDS.keys()))
    advisory = ADVISORY_OPPORTUNITY_MAP.get(life_event)
    net_worth = f"£{random.choice([15, 40, 80, 150, 300, 600])}million"
    date_collected = min(published_dt + timedelta(days=random.randint(0, 30)), END).isoformat(timespec="seconds")

    title = f"{name} {random.choice(['sells stake in', 'inherits control of', 'steps back from', 'lists', 'expands'])} " \
            f"{random.choice(['family business', 'tech venture', 'property empire', 'investment firm'])}"

    return {
        "date_collected": date_collected,
        "source": random.choice(SOURCES),
        "category": "wealth_press",
        "article_title": title,
        "article_url": f"https://example-news.com/article/{random.randint(10000,999999)}",
        "published_date": published_dt.date().isoformat(),
        "published_date_parsed": published_dt.isoformat(),
        "possible_name": name,
        "age_bracket": age_bracket,
        "region": region,
        "net_worth_mentions": net_worth,
        "wealth_source": wealth_source,
        "wealth_acquisition_type": acquisition,
        "business_interests": business_interest,
        "ownership_patterns": ownership,
        "lifestyle_assets": lifestyle_assets,
        "family_structure": family,
        "life_event": life_event,
        "advisory_opportunity": advisory,
        "advisory_needs": advisory_needs,
        "relevance_score": random.randint(1, 8),
        "llm_person_name": None, "llm_estimated_age": None, "llm_region_country": None,
        "llm_wealth_origin_summary": None, "llm_family_structure_notes": None,
        "llm_advisory_opportunity_notes": None,
        "raw_summary": f"{name} has been in the news regarding their financial affairs.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    args = ap.parse_args()

    rows = [rand_row() for _ in range(args.n)]
    import pandas as pd
    df = pd.DataFrame(rows)[storage.COLUMNS]
    storage.save(df, path=storage.SAMPLE_EXCEL_PATH)
    print()
    print("=" * 70)
    print(f"Generated {len(df)} FAKE / SYNTHETIC demo rows spanning 2000-{END.year}")
    print(f"Saved to: {storage.SAMPLE_EXCEL_PATH}")
    print("This is NOT real collected news — it's for previewing the dashboard")
    print("UI only. Run historical_backfill.py / run_scraper.py for real data,")
    print(f"which is saved separately to: {storage.EXCEL_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    main()
