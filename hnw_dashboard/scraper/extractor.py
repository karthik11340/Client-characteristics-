"""
Rule-based extraction of HNW/UHNW client characteristics from article text.

This is a keyword/regex tagger — no external API required, so the scraper
works out of the box. If you set an ANTHROPIC_API_KEY environment variable,
`llm_extractor.enrich()` will additionally ask Claude to double-check /
fill in gaps (name, age, region, wealth source) for higher accuracy. See
llm_extractor.py.

Every function returns plain Python types so a row can be appended
directly to the Excel sheet.
"""
import re

# ---------------------------------------------------------------------
# Keyword dictionaries — tune these over time as you see what the
# scraper is missing or mis-tagging.
# ---------------------------------------------------------------------

WEALTH_SOURCE_KEYWORDS = {
    "Business Exit / Sale": ["sold his stake", "sold her stake", "sold the company", "acquired by",
                              "acquisition of", "sale of the business", "trade sale", "exit"],
    "IPO / Public Listing": ["ipo", "initial public offering", "listed on the stock exchange", "went public"],
    "Inheritance": ["inherited", "inheritance", "heir to", "heiress", "family fortune", "passed down"],
    "Tech / Startup": ["tech founder", "startup", "software company", "app maker", "silicon valley", "fintech founder"],
    "Real Estate": ["property developer", "real estate mogul", "property portfolio", "developer of"],
    "Finance / Investment": ["hedge fund", "private equity", "investment banker", "fund manager", "asset manager"],
    "Entertainment / Sport": ["footballer", "musician", "actor", "actress", "athlete", "celebrity"],
    "Family Business / Generational": ["family business", "family-run", "third generation", "fourth generation",
                                        "generational wealth", "family dynasty"],
    "Retail / Consumer Brand": ["retail chain", "brand founder", "e-commerce founder"],
    "Energy / Resources": ["oil fortune", "mining magnate", "energy tycoon", "commodities"],
}

# "Quick" = sudden liquidity event; "Gradual" = built or received over time
ACQUISITION_TYPE_KEYWORDS = {
    "Quick (Windfall/Exit)": ["sold his stake", "sold her stake", "ipo", "windfall", "overnight",
                               "acquired by", "cashed out", "lottery", "sudden wealth"],
    "Gradual (Self-Made)": ["built the business", "grew the company", "over three decades",
                             "self-made", "years of hard work", "started from scratch"],
    "Inherited": ["inherited", "inheritance", "heir", "heiress", "passed down", "family fortune"],
}

REGION_KEYWORDS = {
    "UK": ["uk", "united kingdom", "britain", "british", "london", "england", "scotland", "wales",
           "manchester", "edinburgh"],
    "US": ["united states", "america", "u.s.", "usa", "new york", "california", "silicon valley",
           "los angeles", "texas", "miami"],
    "Europe": ["europe", "france", "germany", "switzerland", "monaco", "italy", "spain", "paris",
               "geneva", "zurich"],
    "Middle East": ["dubai", "uae", "saudi", "qatar", "abu dhabi", "middle east"],
    "Asia": ["china", "hong kong", "singapore", "india", "japan", "asia"],
}

LIFESTYLE_ASSET_KEYWORDS = {
    "Yacht": ["yacht", "superyacht", "megayacht"],
    "Art Collection": ["art collection", "art collector", "painting sold", "auctioned artwork"],
    "Private Jet / Aviation": ["private jet", "private plane", "private aircraft"],
    "Country Estate / Luxury Property": ["country estate", "mansion", "luxury property", "manor house",
                                          "private island", "penthouse"],
    "Supercar Collection": ["supercar", "car collection", "classic car collection"],
}

BUSINESS_INTERESTS_KEYWORDS = {
    "Serial Entrepreneur": ["serial entrepreneur", "founded multiple", "several ventures",
                             "multiple startups", "his third company", "her third company"],
    "Board / Non-Executive Roles": ["non-executive director", "board member", "sits on the board",
                                     "chairman of", "non-exec"],
    "Single Core Business": ["sole business", "flagship company", "core business", "his main company"],
    "Diversified Holdings / Conglomerate": ["diversified holdings", "conglomerate",
                                             "portfolio of companies", "holding company"],
    "Investor / Angel": ["angel investor", "venture investor", "invests in startups",
                          "backs early-stage"],
}

OWNERSHIP_PATTERN_KEYWORDS = {
    "Sole Owner": ["sole owner", "wholly owned", "100% owned", "sole proprietor"],
    "Family-Owned Majority Stake": ["majority stake", "family-owned", "controlling stake",
                                     "family controls"],
    "Private Equity Backed": ["private equity backed", "pe-backed", "backed by private equity"],
    "Publicly Listed / Minority Stake": ["publicly listed", "minority stake", "listed company",
                                          "shareholder in"],
    "Trust-Held Assets": ["held in trust", "family trust", "trust structure",
                           "assets held through a trust"],
    "Joint Venture / Partnership": ["joint venture", "in partnership with", "co-owned"],
}

# Broader, always-on advisory signal detection — distinct from
# ADVISORY_OPPORTUNITY_MAP below, which is specifically triggered by a
# detected life EVENT. This catches ongoing needs even with no single
# triggering event in the article.
ADVISORY_NEEDS_KEYWORDS = {
    "Tax Planning": ["tax planning", "tax efficient", "tax mitigation", "inheritance tax"],
    "Trust & Estate Structuring": ["trust structure", "estate planning", "will and testament",
                                    "estate structuring"],
    "Family Governance": ["family governance", "family constitution", "family council"],
    "Philanthropy Structuring": ["charitable foundation", "philanthropic", "giving pledge",
                                  "donor advised fund"],
    "Multi-Jurisdictional / Cross-Border": ["cross-border", "multiple jurisdictions",
                                             "offshore structure", "international assets"],
    "Concierge / Lifestyle Management": ["lifestyle management", "concierge service",
                                          "personal assistant to"],
    "Asset Management (Yacht/Art/Property)": ["yacht management", "art advisory",
                                                "property management company"],
    "Succession Planning": ["succession plan", "next generation leadership",
                             "handover of the business"],
}

FAMILY_STRUCTURE_KEYWORDS = {
    "Married": ["his wife", "her husband", "married to"],
    "Divorced": ["divorce", "ex-wife", "ex-husband", "divorce settlement"],
    "Has Children / Next Generation": ["his children", "her children", "his son", "his daughter",
                                        "her son", "her daughter", "next generation"],
    "Family Business Involvement": ["family business", "family-run", "sibling", "siblings",
                                     "family dynasty"],
}

LIFE_EVENT_KEYWORDS = {
    "Business Exit": ["sold his stake", "sold her stake", "sale of the business", "trade sale", "exit"],
    "Succession": ["succession", "handed over the reins", "stepped down as ceo", "next generation takes over"],
    "Inheritance / Wealth Transfer": ["inherited", "inheritance", "estate planning", "wealth transfer"],
    "IPO / Listing": ["ipo", "went public", "listed on the stock exchange"],
    "Acquisition (Buyer)": ["acquired", "acquisition of", "bought a stake in"],
    "Philanthropy": ["donated", "philanthropist", "charitable foundation", "giving pledge"],
    "Divorce Settlement": ["divorce settlement", "divorce"],
}

# Maps a detected life event to a plain-English advisory opportunity —
# this is the "so what" column for the dashboard.
ADVISORY_OPPORTUNITY_MAP = {
    "Business Exit": "Post-exit wealth structuring, investment strategy, tax planning",
    "Succession": "Succession & family governance advisory, family office setup",
    "Inheritance / Wealth Transfer": "Estate planning, trust structuring, inheritance tax planning",
    "IPO / Listing": "Liquidity event planning, diversification strategy, philanthropic structuring",
    "Acquisition (Buyer)": "Deal financing advisory, holding structure planning",
    "Philanthropy": "Philanthropic / foundation structuring advisory",
    "Divorce Settlement": "Asset re-structuring, new estate & trust planning post-settlement",
}

AGE_REGEX = re.compile(r"\b(\d{2})[- ]year[- ]old\b|\baged (\d{2})\b|\(\s*(\d{2})\s*\)")
NET_WORTH_REGEX = re.compile(
    r"[£$€]\s?\d+(?:\.\d+)?\s?(?:billion|million|bn|m)\b", re.IGNORECASE
)
NAME_HINT_REGEX = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2})\b")


def _match_keywords(text_lower, keyword_map):
    """Return list of category labels whose keywords appear in text_lower."""
    hits = []
    for label, kws in keyword_map.items():
        if any(kw in text_lower for kw in kws):
            hits.append(label)
    return hits


def extract_age_bracket(text):
    m = AGE_REGEX.search(text)
    if not m:
        return None
    age_str = next(g for g in m.groups() if g)
    age = int(age_str)
    if age < 18:
        return None
    bracket_start = (age // 10) * 10
    return f"{bracket_start}-{bracket_start + 9}"


def extract_net_worth_mentions(text):
    return NET_WORTH_REGEX.findall(text)


def guess_name(title):
    """Very rough heuristic: first capitalised 2–3 word span in the title."""
    m = NAME_HINT_REGEX.search(title)
    return m.group(1) if m else None


def analyze_article(title: str, summary: str, body: str = ""):
    """
    Main entry point. Combines title + summary + (optional) full body,
    runs every keyword tagger, and returns a dict ready to become one
    Excel row.
    """
    full_text = " ".join([title or "", summary or "", body or ""])
    text_lower = full_text.lower()

    wealth_sources = _match_keywords(text_lower, WEALTH_SOURCE_KEYWORDS)
    acquisition_types = _match_keywords(text_lower, ACQUISITION_TYPE_KEYWORDS)
    regions = _match_keywords(text_lower, REGION_KEYWORDS)
    lifestyle_assets = _match_keywords(text_lower, LIFESTYLE_ASSET_KEYWORDS)
    family_structure = _match_keywords(text_lower, FAMILY_STRUCTURE_KEYWORDS)
    life_events = _match_keywords(text_lower, LIFE_EVENT_KEYWORDS)
    business_interests = _match_keywords(text_lower, BUSINESS_INTERESTS_KEYWORDS)
    ownership_patterns = _match_keywords(text_lower, OWNERSHIP_PATTERN_KEYWORDS)
    advisory_needs = _match_keywords(text_lower, ADVISORY_NEEDS_KEYWORDS)

    advisory_opportunities = sorted({
        ADVISORY_OPPORTUNITY_MAP[ev] for ev in life_events if ev in ADVISORY_OPPORTUNITY_MAP
    })

    return {
        "possible_name": guess_name(title or ""),
        "age_bracket": extract_age_bracket(full_text),
        "region": ", ".join(regions) if regions else None,
        "net_worth_mentions": ", ".join(extract_net_worth_mentions(full_text)) or None,
        "wealth_source": ", ".join(wealth_sources) if wealth_sources else None,
        "wealth_acquisition_type": ", ".join(acquisition_types) if acquisition_types else None,
        "business_interests": ", ".join(business_interests) if business_interests else None,
        "ownership_patterns": ", ".join(ownership_patterns) if ownership_patterns else None,
        "lifestyle_assets": ", ".join(lifestyle_assets) if lifestyle_assets else None,
        "family_structure": ", ".join(family_structure) if family_structure else None,
        "life_event": ", ".join(life_events) if life_events else None,
        "advisory_opportunity": "; ".join(advisory_opportunities) if advisory_opportunities else None,
        "advisory_needs": ", ".join(advisory_needs) if advisory_needs else None,
        "relevance_score": (
            len(wealth_sources) + len(acquisition_types) + len(lifestyle_assets)
            + len(family_structure) + len(life_events) + len(business_interests)
            + len(ownership_patterns) + len(advisory_needs)
        ),
    }
