"""
Source list for HNW / UHNW client-intelligence collection.

Each entry is an RSS/Atom feed. RSS is used for discovery (title, link,
summary, published date) because it is stable and doesn't require fighting
anti-bot systems. The full article body is then optionally fetched with
Scrapling for deeper keyword extraction.

Add / remove feeds freely — the scraper treats this list as the single
source of truth. If a publication doesn't offer RSS, you can still add it
under SEED_URLS and the scraper will crawl it directly with Scrapling's
StealthyFetcher instead of feedparser.
"""

RSS_SOURCES = [
    # Wealth / private banking trade press
    {"name": "Spear's", "url": "https://www.spearswms.com/feed/", "category": "wealth_press"},
    {"name": "Wealth Briefing", "url": "https://www.wealthbriefing.com/rss/wealthbriefing.xml", "category": "wealth_press"},
    {"name": "Family Capital", "url": "https://familycapital.com/feed/", "category": "family_office"},
    {"name": "Campden FB", "url": "https://www.campdenfb.com/rss.xml", "category": "family_office"},
    {"name": "Private Banker International", "url": "https://www.privatebankerinternational.com/feed/", "category": "wealth_press"},
    {"name": "Citywire Wealth Manager", "url": "https://citywire.com/wealth-manager/rss", "category": "wealth_press"},

    # Business / entrepreneurship (wealth-creation events: exits, IPOs, sales)
    {"name": "Sky News Business", "url": "https://feeds.skynews.com/feeds/rss/business.xml", "category": "business_news"},
    {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "category": "business_news"},
    {"name": "The Guardian - Business", "url": "https://www.theguardian.com/uk/business/rss", "category": "business_news"},
    {"name": "The Guardian - Money", "url": "https://www.theguardian.com/money/rss", "category": "personal_finance"},
    {"name": "FT Adviser", "url": "https://www.ftadviser.com/rss", "category": "wealth_press"},

    # Lifestyle assets (yachts, art, property, private aviation)
    {"name": "Robb Report", "url": "https://robbreport.com/feed/", "category": "lifestyle_assets"},
    {"name": "Property Week", "url": "https://www.propertyweek.com/rss", "category": "luxury_property"},

    # Rich lists / profiles
    {"name": "Forbes - Billionaires", "url": "https://www.forbes.com/billionaires/feed/", "category": "rich_list"},
]

# Sites without usable RSS — crawled directly (best-effort; may need
# StealthyFetcher if they run anti-bot protection).
SEED_URLS = [
    {"name": "Sunday Times Rich List", "url": "https://www.thetimes.co.uk/sunday-times-rich-list", "category": "rich_list"},
]

# Keywords used purely to PRE-FILTER which articles are even worth pulling
# full text for — keeps the scraper fast and on-topic. Matching is
# case-insensitive substring matching against title+summary.
RELEVANCE_KEYWORDS = [
    "net worth", "fortune", "billionaire", "millionaire", "family office",
    "wealth manager", "private bank", "inheritance", "inherited", "heir",
    "succession", "trust fund", "exit", "sold his stake", "sold her stake",
    "ipo", "acquisition", "acquired by", "yacht", "superyacht", "art collection",
    "private jet", "country estate", "luxury property", "philanthropist",
    "entrepreneur", "self-made", "old money", "generational wealth",
    "estate planning", "wealth transfer", "hnw", "uhnw", "high-net-worth",
    "ultra-high-net-worth", "rich list", "wealth management",
]
