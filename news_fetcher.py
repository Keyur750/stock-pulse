"""Fetches financial news headlines from RSS feeds. No API key needed."""

import feedparser


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
