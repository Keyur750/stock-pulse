"""
Pulls retail/finance chatter from Bluesky via the official AT Protocol API,
authenticated with a free account + app password. Additive, same as
reddit.py: if credentials aren't set, collect_bluesky() returns {} and the
rest of the pipeline runs on StockTwits/Reddit alone.

Two things learned from live testing before wiring this in (see PRODUCT.md
for the full writeup) that shape every design choice below:

1. Plain keyword search (`q=$TICKER`) is unreliable — it matches the bare
   word anywhere in a post, so "$SBUX" pulled in people talking about the
   coffee shop, not the stock. Bluesky posts get a real, structured
   `app.bsky.richtext.facet#tag` when a `$TICKER` cashtag is composed —
   searching with the `tag=` param (exact facet match) instead of relying
   on `q=` alone is what actually filters to genuine ticker mentions.
   `q=` is still sent alongside `tag=` (required by the endpoint), but
   `tag=` is what does the real filtering.

2. Even with exact-tag matching, a couple of failure modes survive and
   were confirmed by hand against all 30 watchlist tickers:
   - `$T` (AT&T) collides structurally with people writing "$T" to mean
     "trillion dollars" in unrelated political/spending posts — the
     poster's own client tags it as a `$T` cashtag either way, so no
     query-side filter can separate the two. Excluded outright.
   - Two accounts (`trendtags.bsky.social`, `toptags.bsky.social`) post
     rolling "trending hashtags" digests that happen to include `$dis`
     or `$META` as one of dozens of unrelated tags. Blocklisted by handle
     rather than excluding the tickers, since the rest of both tickers'
     real chatter is genuine.

Search requires an authenticated session even though most other AT Proto
reads are open — `public.api.bsky.app` also proved unreliable to reach
directly in testing (consistent 403s); routing through `bsky.social`
(the same host used for authentication) is what actually works.
"""

import os
import time
from datetime import datetime, timedelta, timezone

import requests

PDS_HOST = "https://bsky.social"
HEADERS = {"Accept": "application/json"}

# See module docstring point 2. Revisit only if re-tested by hand the same
# way — a symbol that collides with common usage doesn't announce itself
# via an error, it just quietly pollutes the sentiment sample.
EXCLUDED_TICKERS = {"T"}
BLOCKED_AUTHORS = {"trendtags.bsky.social", "toptags.bsky.social"}

_session = None
_session_checked = False


def _get_session():
    """Returns {"accessJwt": ...} or None if credentials are missing or
    auth fails. Cached after first call — a single access token is good
    for the whole pipeline run, no need to re-authenticate per ticker."""
    global _session, _session_checked
    if _session_checked:
        return _session
    _session_checked = True

    handle = os.environ.get("BSKY_HANDLE")
    app_password = os.environ.get("BSKY_APP_PASSWORD")
    if not handle or not app_password:
        print("  [bluesky] BSKY_HANDLE/BSKY_APP_PASSWORD not set — skipping Bluesky.")
        return None

    try:
        r = requests.post(
            f"{PDS_HOST}/xrpc/com.atproto.server.createSession",
            json={"identifier": handle, "password": app_password},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=10,
        )
        if r.status_code != 200:
            print(f"  [bluesky] authentication failed: HTTP {r.status_code}")
            return None
        _session = r.json()
    except requests.RequestException as e:
        print(f"  [bluesky] authentication failed: {type(e).__name__}: {e}")
        _session = None
    return _session


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def search_ticker(ticker: str, token: str, max_age_hours: float = 24.0,
                   limit: int = 100, retries: int = 2) -> list:
    """Every post carrying an exact `$TICKER` cashtag facet in the last
    `max_age_hours`, newest first. Paginates via cursor until the window
    is exhausted or `limit` is hit — same safety-valve shape as
    stocktwits.py's hard_limit, so one viral ticker can't blow up the run."""
    tag = f"${ticker}"
    since = _iso(datetime.now(timezone.utc) - timedelta(hours=max_age_hours))
    posts = []
    cursor = None

    while len(posts) < limit:
        params = {
            "q": tag, "tag": tag, "sort": "latest", "since": since,
            "limit": min(100, limit - len(posts)),
        }
        if cursor:
            params["cursor"] = cursor

        for attempt in range(retries + 1):
            try:
                r = requests.get(
                    f"{PDS_HOST}/xrpc/app.bsky.feed.searchPosts",
                    params=params, headers={**HEADERS, "Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                break
            except requests.RequestException:
                if attempt == retries:
                    return posts
                time.sleep(2)

        if r.status_code == 429:
            time.sleep(5)
            continue
        if r.status_code != 200:
            break

        data = r.json()
        batch = data.get("posts", [])
        if not batch:
            break
        posts.extend(p for p in batch if p.get("author", {}).get("handle") not in BLOCKED_AUTHORS)

        cursor = data.get("cursor")
        if not cursor:
            break

    return posts[:limit]


def collect_bluesky(watchlist: list, max_age_hours: float = 24.0,
                     limit_per_ticker: int = 100, sleep_between: float = 0.5) -> dict:
    """Fetch cashtag-tagged posts for every watchlist ticker (minus
    EXCLUDED_TICKERS). Returns {ticker: [message_dicts]} shaped like
    stocktwits.py's output (a 'body' key is all sentiment.py needs) so
    all three sources merge cleanly in main.py."""
    session = _get_session()
    if session is None:
        return {}
    token = session["accessJwt"]

    result = {}
    total_posts = 0
    for ticker in watchlist:
        if ticker in EXCLUDED_TICKERS:
            continue
        try:
            posts = search_ticker(ticker, token, max_age_hours=max_age_hours, limit=limit_per_ticker)
        except Exception as e:
            print(f"  [bluesky] failed to fetch ${ticker}: {type(e).__name__}: {e}")
            continue

        if posts:
            result[ticker] = [
                {
                    "body": (p.get("record", {}).get("text") or "")[:500],
                    "chatter_source": "bluesky",
                    "score": p.get("likeCount", 0),
                    "id": p.get("cid"),
                    "created_at": p.get("record", {}).get("createdAt"),
                }
                for p in posts
            ]
            total_posts += len(posts)
        time.sleep(sleep_between)

    print(f"  [bluesky] {total_posts} cashtag-tagged posts across {len(result)} tickers")
    return result
