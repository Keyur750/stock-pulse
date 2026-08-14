"""
Pulls trending symbols and per-symbol message streams from StockTwits'
public API. No API key, login, or approval process required — these
endpoints are open reads, and unlike Reddit, users on StockTwits often
self-tag their posts as Bullish/Bearish, which gives us higher-quality
sentiment than inferring it from raw text alone.
"""

import time
from datetime import datetime, timedelta, timezone

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


def _parse_created_at(msg):
    ts = msg.get("created_at")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_symbol_stream(symbol: str, max_age_hours: float = 24.0, hard_limit: int = 400,
                         page_sleep: float = 0.3):
    """Returns every message for a ticker from the last `max_age_hours` —
    a real volume count, not a fixed sample. Pages backwards using the
    `max` param (return messages older than a given message id) until a
    message older than the window shows up, history runs out, or
    `hard_limit` is hit (safety valve so one viral ticker can't blow up
    the run). Some tickers will come back with 20 messages, others 400 —
    that's the point; a flat cap was hiding real differences in chatter
    volume behind an identical number for every actively-traded ticker."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    messages = []
    max_id = None
    while len(messages) < hard_limit:
        url = f"{BASE}/streams/symbol/{symbol}.json"
        if max_id is not None:
            url += f"?max={max_id}"
        data = _get(url)
        if not data:
            break
        batch = data.get("messages", [])
        if not batch:
            break

        ran_out_of_window = False
        for m in batch:
            created = _parse_created_at(m)
            if created is not None and created < cutoff:
                ran_out_of_window = True
                break
            messages.append(m)

        if ran_out_of_window or len(batch) < 30:
            break  # crossed the time window, or fewer than a full page means no more history
        max_id = batch[-1]["id"] - 1
        time.sleep(page_sleep)
    return messages[:hard_limit]


def collect_all(watchlist: list, trending_limit: int = 0,
                 max_age_hours: float = 24.0, hard_limit: int = 400,
                 sleep_between: float = 0.6):
    """Fetch trending symbols + guarantee coverage of the watchlist, then
    pull every message from the last `max_age_hours` for the union of
    both. Returns {symbol: [message_dicts]}."""
    trending = fetch_trending_symbols(trending_limit) if trending_limit else []
    if trending:
        time.sleep(sleep_between)

    all_symbols = list(dict.fromkeys(trending + list(watchlist)))  # dedupe, keep order

    result = {}
    for sym in all_symbols:
        messages = fetch_symbol_stream(sym, max_age_hours=max_age_hours, hard_limit=hard_limit)
        if messages:
            result[sym] = messages
        time.sleep(sleep_between)
    return result, set(trending)
