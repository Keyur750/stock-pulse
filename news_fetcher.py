"""Fetches financial news. Two sources: generic RSS feeds (Market News,
Tier 3 of the News Intelligence System — broad, unranked, ambient
context) and per-company news via yfinance (Company News, Tier 2's raw
material before ranking — see news_ranker.py and PRODUCT.md's "News
Intelligence System"). No API key needed for either."""

import feedparser
import yfinance as yf


def fetch_news(feeds: dict, max_per_feed: int = 10):
    """feeds: {source_name: rss_url}. Returns list of headline dicts,
    newest-looking first within each source."""
    all_items = []
    for source, url in feeds.items():
        try:
            parsed = feedparser.parse(url)
        except Exception:
            continue
        for entry in parsed.entries[:max_per_feed]:
            all_items.append({
                "source": source,
                "title": entry.get("title", "").strip(),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "summary": entry.get("summary", "")[:200] if entry.get("summary") else "",
            })
    return all_items


def fetch_ticker_news(tickers, max_per_ticker=12):
    """Returns {ticker: [{"title", "link", "publisher", "published"}]}
    from yfinance's own per-company news aggregation — real outlets
    (Reuters, Bloomberg, Motley Fool, etc.) already curated per company,
    not a generic top-stories feed matched to a ticker after the fact.
    Handles both the older and newer yfinance news item shapes
    defensively, since this changed between versions during testing."""
    out = {}
    for ticker in tickers:
        try:
            items = yf.Ticker(ticker).news or []
        except Exception as e:
            print(f"  [ticker_news] {ticker} failed: {type(e).__name__}: {e}")
            continue

        parsed = []
        for item in items[:max_per_ticker]:
            c = item.get("content", item) if isinstance(item.get("content"), dict) else item
            title = (c.get("title") or item.get("title") or "").strip()
            if not title:
                continue

            link = None
            for key in ("canonicalUrl", "clickThroughUrl"):
                v = c.get(key)
                if isinstance(v, dict) and v.get("url"):
                    link = v["url"]
                    break
            link = link or item.get("link") or ""

            publisher = None
            provider = c.get("provider")
            if isinstance(provider, dict):
                publisher = provider.get("displayName")
            publisher = publisher or item.get("publisher") or "Unknown"

            published = c.get("pubDate") or item.get("providerPublishTime") or ""

            parsed.append({"title": title, "link": link, "publisher": publisher, "published": published})

        if parsed:
            out[ticker] = parsed
    return out
