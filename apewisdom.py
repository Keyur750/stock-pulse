"""
Pulls Reddit mention-volume data from ApeWisdom (apewisdom.io), a free,
keyless, third-party aggregator that tracks ticker mentions across
r/wallstreetbets and other stock subreddits. Unlike StockTwits, this has
no bullish/bearish direction — it's a pure attention/volume signal, used
here to corroborate (or contradict) the volume-spike detection already
built on StockTwits history, with an independent second source.

No API key or login required. Since it's a third-party service rather
than Reddit itself, failures are handled the same way as every other
source here: log a warning and continue with what we have.
"""

import requests

BASE = "https://apewisdom.io/api/v1.0/filter/all-stocks/page"
HEADERS = {"Accept": "application/json"}


def fetch_mentions(max_pages: int = 5, timeout: int = 10) -> dict:
    """Returns {ticker: {"mentions": int, "upvotes": int, "rank": int,
    "mentions_24h_ago": int|None}}. Pages are ordered by mention count
    descending, so max_pages caps how far into the long tail we go —
    the tickers we actually care about (trending or watchlisted) show up
    early if they're being discussed at all."""
    out = {}
    for page in range(1, max_pages + 1):
        try:
            r = requests.get(f"{BASE}/{page}", headers=HEADERS, timeout=timeout)
            if r.status_code != 200:
                print(f"  [apewisdom] page {page} returned HTTP {r.status_code}")
                break
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"  [apewisdom] page {page} failed: {type(e).__name__}: {e}")
            break

        results = data.get("results", [])
        if not results:
            break
        for row in results:
            ticker = row.get("ticker")
            if not ticker:
                continue
            out[ticker] = {
                "mentions": row.get("mentions", 0),
                "upvotes": row.get("upvotes", 0),
                "rank": row.get("rank"),
                "mentions_24h_ago": row.get("mentions_24h_ago"),
            }
        if page >= data.get("pages", page):
            break
    return out
