"""
Pulls retail sentiment from Reddit via the official Reddit API (praw),
read-only. Reddit is arguably the highest-signal home of retail chatter
(r/wallstreetbets, r/stocks, r/investing, r/StockMarket), and unlike
scraping the site directly, the official API keeps this on solid ToS
footing.

Requires free API credentials from https://www.reddit.com/prefs/apps
(create a "script" app) passed via environment variables:
  REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT

If credentials aren't set, collect_reddit() returns {} and the rest of
the pipeline just runs on StockTwits alone — Reddit is additive, not
required.
"""

import os
import re

_CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,5})\b")
_BARE_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")

_client = None
_client_checked = False


def _get_client():
    """Returns a read-only praw.Reddit client, or None if credentials are
    missing or praw isn't installed. Cached after first call."""
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True

    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT", "stock-pulse/1.0")

    if not client_id or not client_secret:
        print("  [reddit] REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET not set — skipping Reddit.")
        return None

    try:
        import praw
    except ImportError:
        print("  [reddit] praw not installed — skipping Reddit.")
        return None

    try:
        _client = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        _client.read_only = True
    except Exception as e:
        print(f"  [reddit] failed to authenticate: {type(e).__name__}: {e}")
        _client = None
    return _client


def extract_tickers(text: str, known_symbols: set) -> set:
    """Find ticker mentions in text, restricted to a known symbol set to
    avoid false positives from ordinary capitalized words/acronyms (e.g.
    "DD", "IT", "ATH"). Cashtags ($NVDA) are unambiguous; bare uppercase
    words are only counted if they match a known symbol."""
    if not text:
        return set()
    found = set()
    for m in _CASHTAG_RE.findall(text):
        sym = m.upper()
        if sym in known_symbols:
            found.add(sym)
    for m in _BARE_TICKER_RE.findall(text):
        if m in known_symbols:
            found.add(m)
    return found


def collect_reddit(known_symbols: set, watchlist: set, subreddits: list,
                    post_limit: int = 75, comments_per_watchlist_post: int = 15):
    """Fetch hot posts from each subreddit, tag ticker mentions against
    known_symbols, and pull top-level comments on posts that mention a
    watchlist ticker for extra depth where it matters most. Returns
    {ticker: [message_dicts]} shaped like stocktwits' output (a 'body'
    key is all sentiment.py needs) so the two sources merge cleanly."""
    reddit = _get_client()
    if reddit is None:
        return {}

    result = {}
    total_posts = 0
    total_comments = 0

    for sub_name in subreddits:
        try:
            submissions = list(reddit.subreddit(sub_name).hot(limit=post_limit))
        except Exception as e:
            print(f"  [reddit] failed to fetch r/{sub_name}: {type(e).__name__}: {e}")
            continue

        for post in submissions:
            text = f"{post.title}\n{post.selftext or ''}"
            tickers = extract_tickers(text, known_symbols)
            if not tickers:
                continue

            total_posts += 1
            msg = {
                "body": text[:500],
                "chatter_source": "reddit",
                "score": post.score,
                "id": post.id,
            }
            for t in tickers:
                result.setdefault(t, []).append(msg)

            watchlist_hits = tickers & watchlist
            if watchlist_hits and comments_per_watchlist_post:
                try:
                    post.comments.replace_more(limit=0)
                    for c in post.comments[:comments_per_watchlist_post]:
                        body = getattr(c, "body", None)
                        if not body:
                            continue
                        total_comments += 1
                        cmsg = {
                            "body": body[:500],
                            "chatter_source": "reddit",
                            "score": getattr(c, "score", 0),
                            "id": c.id,
                        }
                        for t in watchlist_hits:
                            result.setdefault(t, []).append(cmsg)
                except Exception:
                    pass

    print(f"  [reddit] {total_posts} ticker-tagged posts, {total_comments} comments "
          f"across {len(subreddits)} subreddits")
    return result
