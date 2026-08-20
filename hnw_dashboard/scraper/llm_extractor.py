"""
Optional LLM enrichment step.

The rule-based extractor.py works standalone. If you export an
ANTHROPIC_API_KEY environment variable, this module will additionally
send each already-flagged-relevant article to Claude to clean up /
confirm the harder fields (name, precise age, region, wealth origin
narrative) in a single structured call. This meaningfully improves
accuracy over pure keyword matching, especially for name extraction and
nuanced wealth-origin descriptions, at the cost of API usage.

Usage:
    from llm_extractor import enrich
    row = enrich(row, title, summary, body)   # returns the row, enriched if possible
"""
import os
import json

_client = None
_enabled = bool(os.environ.get("ANTHROPIC_API_KEY"))

if _enabled:
    try:
        import anthropic
        _client = anthropic.Anthropic()
    except ImportError:
        _enabled = False


SYSTEM_PROMPT = """You extract structured HNW/UHNW client-intelligence fields from a news
article for a private wealth management prospecting database. Respond with ONLY a JSON object,
no prose, no markdown fences. Use null for anything not stated or not reasonably inferable.
Never invent facts not supported by the text.

Schema:
{
  "person_name": string|null,
  "estimated_age": integer|null,
  "region_country": string|null,
  "wealth_origin_summary": string|null,   // 1 sentence, plain English
  "family_structure_notes": string|null,  // 1 sentence
  "advisory_opportunity_notes": string|null // 1 sentence: what a wealth manager could offer this person
}"""


def enrich(row: dict, title: str, summary: str, body: str = "") -> dict:
    """Best-effort enrichment. Silently no-ops if no API key / call fails,
    so the scraper never breaks because of this optional step."""
    if not _enabled or _client is None:
        return row

    text = f"TITLE: {title}\nSUMMARY: {summary}\nBODY: {(body or '')[:4000]}"
    try:
        resp = _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        parsed = json.loads(raw)
        row["llm_person_name"] = parsed.get("person_name")
        row["llm_estimated_age"] = parsed.get("estimated_age")
        row["llm_region_country"] = parsed.get("region_country")
        row["llm_wealth_origin_summary"] = parsed.get("wealth_origin_summary")
        row["llm_family_structure_notes"] = parsed.get("family_structure_notes")
        row["llm_advisory_opportunity_notes"] = parsed.get("advisory_opportunity_notes")
    except Exception as e:
        row["llm_enrichment_error"] = str(e)
    return row
