"""
Google Trends — a free, independent Crowd-attention cross-check via
`pytrends` (unofficial, scrapes the public Trends UI, no API key).
Search interest isn't a bullish/bearish signal — like ApeWisdom, it's
pure attention volume, used here to detect a genuine spike in public
interest independent of StockTwits/Reddit chatter.

pytrends is known to be rate-limited and occasionally flaky (Google
changes its backend without notice) — every call is wrapped so one
ticker failing doesn't take down the run, same graceful-degradation
pattern as reddit.py and apewisdom.py.
"""

import time

QUERY_SUFFIX = " stock"


def fetch_search_interest(tickers: list[str], sleep_seconds: float = 20.0) -> dict:
    """Returns {ticker: {"interest_today": int, "interest_baseline": float}}
    from Google Trends' 0-100 relative interest scale over the last 3
    months, daily resolution. `interest_baseline` is the trailing
    7-day average (excluding today), so the caller can compute a spike
    ratio the same way apewisdom.py's mention data already does.

    Google's unofficial Trends backend rate-limits aggressively — a
    live test hit HTTP 429 after a single request with only a 1.5s
    gap. `sleep_seconds` defaults much higher than every other source
    in this project for that reason, and each ticker gets one retry
    with a longer backoff before being skipped. Even so, some tickers
    failing on a given run is expected, not a bug — same
    graceful-degradation contract as every other source here."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("  [trends] pytrends not installed — skipping Google Trends.")
        return {}

    try:
        pt = TrendReq(hl="en-US", tz=360)
    except Exception as e:
        print(f"  [trends] failed to init pytrends client: {type(e).__name__}: {e}")
        return {}

    out = {}
    for i, ticker in enumerate(tickers):
        query = f"{ticker}{QUERY_SUFFIX}"
        for attempt in range(2):
            try:
                pt.build_payload([query], timeframe="today 3-m")
                df = pt.interest_over_time()
                if df is not None and not df.empty and query in df.columns:
                    values = df[query].tolist()
                    if len(values) >= 8:
                        latest = values[-1]
                        baseline = sum(values[-8:-1]) / 7
                        out[ticker] = {
                            "interest_today": int(latest),
                            "interest_baseline": round(baseline, 1),
                        }
                break
            except Exception as e:
                is_rate_limit = "429" in str(e) or "TooManyRequests" in str(e)
                if is_rate_limit and attempt == 0:
                    print(f"  [trends] {ticker} rate-limited, waiting {sleep_seconds * 2:.0f}s and retrying once...")
                    time.sleep(sleep_seconds * 2)
                    continue
                print(f"  [trends] {ticker} failed: {type(e).__name__}: {e}")
                break

        if i < len(tickers) - 1:
            time.sleep(sleep_seconds)

    return out
