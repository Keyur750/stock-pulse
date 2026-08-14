"""
Company News filter + ranking — Tier 2's second stage. yfinance's
per-ticker news (news_fetcher.fetch_ticker_news) is genuinely more
relevant than a generic top-stories feed, but it isn't perfectly
scoped either: live testing on BA returned a real Boeing/Archer
Aviation deal right alongside an unrelated Lumen Technologies board
appointment and a generic "Defense ETFs to buy" listicle. This module
tells the two apart.

One batched Gemini call per ticker — not one call per headline. Same
"batch before you pay" principle already used elsewhere in this
project: ~12 headlines/ticker × 15 tickers as individual calls would
be 180 calls/day; batched, it's 15. Reuses the same client/model as the
AI analyst via llm_client.py.
"""

import json
import re
import time

from llm_client import get_client, MODEL

RANK_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "The number of the headline this decision is for."},
                    "keep": {"type": "boolean", "description": "True only for real, specific news about this company itself — a deal, earnings, a lawsuit, a product, an executive change, a regulatory action. False for generic investing advice, listicles ('N stocks to buy'), opinion columns, or headlines that only mention the company in passing while really being about something else."},
                    "importance": {"type": "integer", "description": "1-5, only meaningful when keep=true. 5 = major/market-moving (M&A, guidance change, a major partnership). 3 = notable but routine. 1 = minor mention."},
                },
                "required": ["index", "keep", "importance"],
            },
        },
    },
    "required": ["items"],
}

PROMPT = """You are filtering news headlines for a retail investor's dashboard about {ticker} \
({name}). For each numbered headline below, decide:

- keep=true ONLY for real, specific news about {ticker} itself — a deal, earnings, a lawsuit, \
a product launch, an executive change, a regulatory action, something that actually happened. \
keep=false for generic investing advice, "N stocks to buy" listicles, opinion columns, or \
headlines where {ticker} is only mentioned in passing while the story is really about a \
different company or the sector broadly.
- importance 1-5 for kept items only: 5 = major/market-moving (M&A, guidance change, a major \
partnership), 3 = notable but routine, 1 = minor mention.

HEADLINES:
{headlines_block}

Respond with a decision for every numbered item, using its number as "index"."""


def _extract_retry_delay(exc, default=45):
    m = re.search(r"retry in (\d+(?:\.\d+)?)s", str(exc))
    return float(m.group(1)) + 2 if m else default


def rank_news(ticker: str, name: str, items: list) -> list:
    """items: list of {"title", ...} dicts. Returns the same list, each
    with `keep` (bool) and `importance` (int|None) added. If no API
    key/client is available, or the call fails, returns every item with
    keep=True and importance=None — degrade to "show everything
    unranked" rather than "show nothing," same contract as the rest of
    the AI-dependent pipeline."""
    if not items:
        return items

    client = get_client()
    if client is None:
        for it in items:
            it["keep"], it["importance"] = True, None
        return items

    headlines_block = "\n".join(f"{i}. {it['title']}" for i, it in enumerate(items))
    prompt = PROMPT.format(ticker=ticker, name=name or ticker, headlines_block=headlines_block)

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": RANK_SCHEMA,
                    "temperature": 0.1,
                    "max_output_tokens": 1500,
                },
            )
            decisions = {d["index"]: d for d in json.loads(response.text)["items"]}
            for i, it in enumerate(items):
                d = decisions.get(i)
                it["keep"] = d["keep"] if d else True
                it["importance"] = d.get("importance") if d else None
            return items
        except Exception as e:
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            if is_rate_limit and attempt == 0:
                wait = _extract_retry_delay(e)
                print(f"  [news_ranker] {ticker} rate-limited, waiting {wait:.0f}s and retrying once...")
                time.sleep(wait)
                continue
            print(f"  [news_ranker] {ticker} ranking failed: {type(e).__name__}: {e}")
            for it in items:
                it["keep"], it["importance"] = True, None
            return items
    return items
