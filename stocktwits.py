"""
Pulls trending symbols and per-symbol message streams from StockTwits'
public API. No API key, login, or approval process required — these
endpoints are open reads, and unlike Reddit, users on StockTwits often
self-tag their posts as Bullish/Bearish, which gives us higher-quality
sentiment than inferring it from raw text alone.
"""

import time
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}
BASE = "https://api.stocktwits.com/api/2"


def _get(url, retries=2):
    last_error = None
    for _ in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(8)
                continue
            last_error = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last_error = f"{type(e).__name__}: {e}"
            time.sleep(2)
    if last_error:
        print(f"  [warning] request to {url} failed: {last_error}")
    return None


def fetch_trending_symbols(limit: int = 30):
    """Returns list of ticker symbols currently trending on StockTwits."""
    data = _get(f"{BASE}/trending/symbols.json")
    if not data:
        return []
    symbols = data.get("symbols", [])[:limit]
    return [s["symbol"] for s in symbols if s.get("symbol")]


def fetch_symbol_stream(symbol: str, limit: int = 30, page_sleep: float = 0.3):
    """Returns list of recent messages for a ticker symbol. Each message
    includes 'body' text and, when the author tagged it, 'entities.sentiment.basic'
    ('Bullish' or 'Bearish'). StockTwits caps each request at 30 messages, so
    for limits above that we page backwards using the `max` param (return
    messages older than a given message id) until we hit the limit or run
    out of history."""
    messages = []
    max_id = None
    while len(messages) < limit:
        url = f"{BASE}/streams/symbol/{symbol}.json"
        if max_id is not None:
            url += f"?max={max_id}"
        data = _get(url)
        if not data:
            break
        batch = data.get("messages", [])
        if not batch:
            break
        messages.extend(batch)
        if len(batch) < 30:
            break  # fewer than a full page means no more history
        max_id = batch[-1]["id"] - 1
        time.sleep(page_sleep)
    return messages[:limit]


def collect_all(watchlist: list, trending_limit: int = 30,
                 messages_per_symbol: int = 30, sleep_between: float = 0.6):
    """Fetch trending symbols + guarantee coverage of the watchlist, then
    pull message streams for the union of both. Returns
    {symbol: [message_dicts]}."""
    trending = fetch_trending_symbols(trending_limit)
    time.sleep(sleep_between)

    all_symbols = list(dict.fromkeys(trending + list(watchlist)))  # dedupe, keep order

    result = {}
    for sym in all_symbols:
        messages = fetch_symbol_stream(sym, messages_per_symbol)
        if messages:
            result[sym] = messages
        time.sleep(sleep_between)
    return result, set(trending)
