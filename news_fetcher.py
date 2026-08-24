"""Fetches financial news. Three sources: generic RSS feeds + Finnhub's
general-news endpoint (Market News, Tier 3 — broad, unranked, ambient
context) and per-company news via yfinance + Finnhub (Company News,
Tier 2's raw material before ranking — see news_ranker.py and
PRODUCT.md's "News Intelligence System"). yfinance and the RSS feeds
need no API key; Finnhub is additive and optional (FINNHUB_API_KEY env
var) — PRODUCT.md flagged it back on 2026-08-13 as "a clean fast-follow
once wanted, as a second independent source for corroboration" and it
was never built until now. Same graceful-skip contract as Reddit/
Bluesky/Gemini: missing the key just means one fewer source, never a
broken pipeline.

Running two independent aggregators over the same real-world events
means real duplicate stories — confirmed by this project's own research
into how news aggregation actually works (a major event routinely gets
covered by hundreds of outlets within the hour; Google's and
Newscatcher's own dedup writeups both start from that fact). See
dedupe_news_items() below."""

import os
import re
import time
from datetime import date, datetime, timedelta, timezone

import feedparser
import requests
import yfinance as yf

FINNHUB_BASE = "https://finnhub.io/api/v1"

# Small, deliberately permissive stopword list — this only needs to
# strip words common enough to cause false-positive overlap between
# genuinely different stories, not model real language.
_TITLE_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "in", "on", "and", "or", "is",
    "are", "was", "were", "with", "as", "at", "by", "its", "it's",
    "after", "before", "than", "into", "over", "up", "down", "vs",
}


def _title_tokens(title):
    words = re.findall(r"[a-z0-9]+", (title or "").lower())
    return {w for w in words if w not in _TITLE_STOPWORDS and len(w) > 2}


def dedupe_news_items(items: list, title_key: str = "title", threshold: float = 0.6) -> list:
    """Drops near-duplicate stories — the same event reported by two
    independent aggregators (yfinance + Finnhub) or two RSS feeds that
    happen to share a wire story. A plain word-overlap (Jaccard) check on
    normalized titles is proportionate at this scale (dozens of items per
    run, not a firehose of thousands) — the MinHash/LSH machinery real
    news aggregators use at scale would be solving a problem this
    pipeline doesn't have. Keeps the first occurrence of each story (so
    callers should list their most-trusted/most-complete source first)
    and drops later near-duplicates; items with no usable title tokens
    (empty/junk titles) are never compared against anything and always
    kept, since "no signal" isn't evidence of a duplicate."""
    kept, kept_tokens = [], []
    for it in items:
        tokens = _title_tokens(it.get(title_key))
        if not tokens:
            kept.append(it)
            kept_tokens.append(None)
            continue
        is_dup = False
        for existing in kept_tokens:
            if not existing:
                continue
            overlap = len(tokens & existing) / len(tokens | existing)
            if overlap >= threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(it)
            kept_tokens.append(tokens)
    return kept


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


def _finnhub_key():
    return os.environ.get("FINNHUB_API_KEY")


def _finnhub_get(path, params, timeout=15):
    params = dict(params, token=_finnhub_key())
    r = requests.get(f"{FINNHUB_BASE}/{path}", params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_finnhub_company_news(tickers, days=3, sleep_seconds=1.1):
    """Company News, Tier 2 — a second, independent aggregator alongside
    yfinance's own. Free tier: 60 calls/min, real outlets in the
    `source` field (marketwatch, reuters, etc. — not "Finnhub" itself),
    unix-epoch timestamps normalized to ISO 8601 here so they sort
    correctly alongside every other source's timestamps downstream.
    Returns {} immediately (not an error) when FINNHUB_API_KEY isn't
    set — additive/optional, same contract as Reddit/Bluesky/Gemini.
    `sleep_seconds` keeps a full 30-ticker run well under the 60
    calls/min free-tier ceiling without needing to track a rolling
    window."""
    if not _finnhub_key():
        return {}

    frm = (date.today() - timedelta(days=days)).isoformat()
    to = date.today().isoformat()
    out = {}
    for i, ticker in enumerate(tickers):
        try:
            items = _finnhub_get("company-news", {"symbol": ticker, "from": frm, "to": to}) or []
        except Exception as e:
            is_rate_limit = "429" in str(e)
            print(f"  [finnhub] {ticker} failed: {type(e).__name__}: {e}")
            if is_rate_limit:
                print("  [finnhub] rate-limited — stopping early this run, will resume next run")
                break
            continue

        parsed = []
        for it in items:
            title = (it.get("headline") or "").strip()
            link = it.get("url") or ""
            if not title or not link:
                continue
            ts = it.get("datetime")
            published = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else ""
            parsed.append({
                "title": title, "link": link,
                "publisher": it.get("source") or "Finnhub", "published": published,
            })
        if parsed:
            out[ticker] = parsed
        if i < len(tickers) - 1:
            time.sleep(sleep_seconds)
    return out


def fetch_finnhub_market_news(category="general", max_items=25):
    """Market News, Tier 3 — one call, not per-ticker, so it costs
    nothing extra against the free-tier rate limit regardless of
    watchlist size. Broadens Tier 3 beyond the 4 configured RSS feeds
    with a real fifth, independently-sourced stream, using the same
    key already added for Company News above. Same optional/graceful
    contract as every other Finnhub call — returns [] if no key is set
    or the call fails."""
    if not _finnhub_key():
        return []
    try:
        items = _finnhub_get("news", {"category": category}) or []
    except Exception as e:
        print(f"  [finnhub] market news failed: {type(e).__name__}: {e}")
        return []

    out = []
    for it in items[:max_items]:
        title = (it.get("headline") or "").strip()
        link = it.get("url") or ""
        if not title or not link:
            continue
        ts = it.get("datetime")
        published = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else ""
        out.append({
            "source": it.get("source") or "Finnhub",
            "title": title, "link": link, "published": published,
            "summary": (it.get("summary") or "")[:200],
        })
    return out
