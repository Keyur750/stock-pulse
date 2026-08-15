"""
Undertow — daily retail sentiment + price + news dashboard.

Run this once a day (see README for scheduling). It pulls trending +
watchlist ticker activity from StockTwits, scores sentiment, cross-checks
it against real price action, pulls financial news, and writes a fresh
dashboard.html you open in your browser.

Usage: python main.py
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

from stocktwits import collect_all
from reddit import collect_reddit
from apewisdom import fetch_mentions as fetch_reddit_mentions
from news_fetcher import fetch_news, fetch_ticker_news
from news_ranker import rank_news
from sec_filings import fetch_recent_8ks
from sentiment import (
    classify_and_score_messages, weighted_average, score_text, label_for_score,
    MAX_SCORE_MAGNITUDE, tag_of, build_market_insight,
)
from reddit import extract_tickers
from market_data import fetch_quotes
from fundamentals import fetch_fundamentals, score_fundamentals
from market_history import build_ticker_history
from logos import ensure_logo
from wallstreet import fetch_analyst_data, score_wallstreet
from market import fetch_market_data, score_market
from trends import fetch_search_interest
from analyst import analyze_stock, MODEL as ANALYST_MODEL

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
ANALYST_HISTORY_PATH = os.path.join(DATA_DIR, "analyst_history.json")
SIGNAL_HISTORY_PATH = os.path.join(DATA_DIR, "signal_history.json")
# docs/index.html is the static marketing homepage (not touched by this
# script); the live data dashboard is served from docs/dashboard.html.
DASHBOARD_PATH = os.path.join(ROOT, "docs", "dashboard.html")
TEMPLATE_PATH = os.path.join(ROOT, "dashboard_template.html")
SENTIMENT_PAGE_PATH = os.path.join(ROOT, "docs", "sentiment.html")
SENTIMENT_TEMPLATE_PATH = os.path.join(ROOT, "sentiment_template.html")
FUNDAMENTALS_PAGE_PATH = os.path.join(ROOT, "docs", "fundamentals.html")
FUNDAMENTALS_TEMPLATE_PATH = os.path.join(ROOT, "fundamentals_template.html")


def load_config():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history, today_snapshot, keep_days=30):
    """Replaces today's entry if one already exists (re-running the same
    day — a manual re-trigger, or local testing) instead of appending a
    duplicate. Without this, multiple same-day runs silently pile up as
    distinct 'days' in history, which quietly corrupts anything that reads
    day-over-day (volume-spike baselines, sentiment deltas, the sentiment
    trend chart)."""
    if history and history[-1].get("date") == today_snapshot["date"]:
        history[-1] = today_snapshot
    else:
        history.append(today_snapshot)
    history = history[-keep_days:]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    return history


def load_analyst_history():
    if os.path.exists(ANALYST_HISTORY_PATH):
        with open(ANALYST_HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_analyst_history(history, today_snapshot, keep_days=90):
    """Same same-day dedupe as save_history, and for the same reason."""
    if history and history[-1].get("date") == today_snapshot["date"]:
        history[-1] = today_snapshot
    else:
        history.append(today_snapshot)
    history = history[-keep_days:]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ANALYST_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    return history


def load_signal_history():
    if os.path.exists(SIGNAL_HISTORY_PATH):
        with open(SIGNAL_HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_signal_history(history, today_snapshot, keep_days=365):
    """The track-record moat's raw material — see PRODUCT.md Phase 4.
    Starts recording from Phase 2, the moment pillar scores exist, not
    held back until the track-record UI itself is built. Same same-day
    dedupe as save_history. Keeps a full year by default since Phase 4
    wants 180-day maturities eventually."""
    if history and history[-1].get("date") == today_snapshot["date"]:
        history[-1] = today_snapshot
    else:
        history.append(today_snapshot)
    history = history[-keep_days:]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SIGNAL_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    return history


def prev_value(prev_snapshot, ticker, field, default=None):
    """History entries may be the old {ticker: float} format or the new
    {ticker: {"avg_sentiment":..., "mentions":...}} format — handle both."""
    if not prev_snapshot or ticker not in prev_snapshot:
        return default
    entry = prev_snapshot[ticker]
    if isinstance(entry, dict):
        return entry.get(field, default)
    if field == "avg_sentiment":
        return entry
    return default


def _sort_key(m):
    # Messages without a parseable timestamp sort as oldest, not newest,
    # so they never crowd out real recent chatter from the sample.
    return m.get("created_at") or ""


def analyze(symbol_messages: dict, trending_symbols: set, watchlist: set,
            prev_snapshot: Optional[dict], sentiment_sample_size: int = 60,
            sentiment_call_sleep_seconds: float = 3.0):
    """Aggregate mention counts, bull/bear breakdown, and sentiment per
    ticker, with day-over-day sentiment shift where history allows.

    `mentions` is the true chatter volume — every message from the
    configured time window, StockTwits + Reddit combined, uncapped except
    for stocktwits.py's own safety ceiling. Sentiment scoring runs on a
    bounded, most-recent sample of that (`sentiment_sample_size`) rather
    than the full set, since scoring is now an LLM call — bounding it
    keeps a single viral ticker from blowing up run time/cost while still
    reporting its real volume honestly."""
    results = []
    for symbol, messages in symbol_messages.items():
        if not messages:
            continue

        total = len(messages)
        sample = sorted(messages, key=_sort_key, reverse=True)[:sentiment_sample_size]

        scored = classify_and_score_messages(symbol, sample)
        avg = weighted_average(scored)
        if any(m.get("_weight") == 1.0 for m in scored):  # an LLM call was made for this ticker
            time.sleep(sentiment_call_sleep_seconds)

        bullish_count = sum(1 for m in scored if m["_sentiment"] == "bullish")
        bearish_count = sum(1 for m in scored if m["_sentiment"] == "bearish")
        neutral_count = sum(1 for m in scored if m["_sentiment"] == "neutral")
        sample_size = len(scored)
        bullish_pct = round(100 * bullish_count / sample_size) if sample_size else 0
        bearish_pct = round(100 * bearish_count / sample_size) if sample_size else 0

        # Most recent 3 from the scored sample, not cherry-picked to make
        # a case — carries real source/tag metadata so evidence can be
        # shown honestly (e.g. "self-tagged Bearish on StockTwits" vs
        # "AI-read as bullish"), not just a bare quote.
        examples = []
        for m in scored[:3]:
            tag = tag_of(m)
            examples.append({
                "title": (m.get("body") or "")[:200],
                "source": m.get("chatter_source", "stocktwits"),
                "tagged": tag if tag in ("Bullish", "Bearish") else None,
                "sentiment": m.get("_sentiment"),
                "created_at": m.get("created_at"),
            })

        prev_avg = prev_value(prev_snapshot, symbol, "avg_sentiment")
        delta = round(avg - prev_avg, 3) if prev_avg is not None else None

        source_counts = {}
        for m in messages:
            src = m.get("chatter_source", "stocktwits")
            source_counts[src] = source_counts.get(src, 0) + 1

        results.append({
            "ticker": symbol,
            "mentions": total,
            "avg_sentiment": round(avg, 3),
            "label": label_for_score(avg),
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "neutral_count": neutral_count,
            "bullish_pct": bullish_pct,
            "bearish_pct": bearish_pct,
            "in_watchlist": symbol in watchlist,
            "is_trending": symbol in trending_symbols,
            "delta": delta,
            "price": None,
            "change_pct": None,
            "examples": examples,
            "source_counts": source_counts,
            "reddit_mentions": None,
            "reddit_mentions_24h_ago": None,
            "reddit_upvotes": None,
            "media_sentiment": None,
            "media_label": None,
            "media_headline_count": None,
            "search_interest_today": None,
            "search_interest_baseline": None,
        })
    return results


def merge_price_data(results, quotes):
    for r in results:
        q = quotes.get(r["ticker"])
        if q:
            r["price"] = q["price"]
            r["change_pct"] = q["change_pct"]
    return results


def score_news(news_items):
    """Scores each headline with the same VADER pipeline used for chatter,
    so news carries a visible sentiment lean instead of just being a raw
    headline list. This is professional/media sentiment, kept distinct
    from retail chatter — the interesting signal is when they disagree."""
    for item in news_items:
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        score = score_text(text)
        item["sentiment_score"] = round(score, 3)
        item["sentiment_label"] = label_for_score(score)
    return news_items


def build_media_sentiment(news_items, known_symbols):
    """Aggregate scored headlines into a per-ticker media sentiment read,
    by matching ticker mentions in the title/summary against known
    symbols (same approach as Reddit's ticker extraction, reused here)."""
    by_ticker = {}
    for item in news_items:
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        tickers = extract_tickers(text, known_symbols)
        for t in tickers:
            by_ticker.setdefault(t, []).append(item["sentiment_score"])

    result = {}
    for ticker, scores in by_ticker.items():
        avg = sum(scores) / len(scores)
        result[ticker] = {
            "avg_sentiment": round(avg, 3),
            "label": label_for_score(avg),
            "headline_count": len(scores),
        }
    return result


def merge_media_sentiment(results, media_sentiment):
    for r in results:
        m = media_sentiment.get(r["ticker"])
        if m:
            r["media_sentiment"] = m["avg_sentiment"]
            r["media_label"] = m["label"]
            r["media_headline_count"] = m["headline_count"]
    return results


def merge_search_interest(results, search_interest):
    """Attach Google Trends' relative search-interest reading as a third,
    fully independent attention measure — a free Crowd cross-check that
    doesn't share a data source with StockTwits, Reddit, or ApeWisdom."""
    for r in results:
        s = search_interest.get(r["ticker"])
        if s:
            r["search_interest_today"] = s["interest_today"]
            r["search_interest_baseline"] = s["interest_baseline"]
    return results


def merge_reddit_mentions(results, mentions):
    """Attach ApeWisdom's Reddit mention volume as a second, independent
    attention measure alongside StockTwits-derived mentions — cross-checking
    'how much is retail talking about this' without conflating it with our
    own sentiment scoring."""
    for r in results:
        m = mentions.get(r["ticker"])
        if m:
            r["reddit_mentions"] = m["mentions"]
            r["reddit_mentions_24h_ago"] = m["mentions_24h_ago"]
            r["reddit_upvotes"] = m["upvotes"]
    return results


def compute_signals(results, history, pillar_scores=None):
    """Auto-generate analyst-style callouts: price/sentiment divergences
    and abnormal chatter-volume spikes. This is the highest-value output —
    surfacing the handful of tickers where the crowd and the tape disagree,
    or where something is unusually loud, instead of making you scan every
    row yourself."""
    pillar_scores = pillar_scores or {}
    # Build a mention-volume baseline per ticker from the last week of history.
    mention_history = {}
    for snap in history[-7:]:
        for tkr, entry in snap.get("tickers", {}).items():
            if isinstance(entry, dict) and "mentions" in entry:
                mention_history.setdefault(tkr, []).append(entry["mentions"])

    signals = []
    for r in results:
        ticker = r["ticker"]
        chg = r.get("change_pct")
        sentiment = r["avg_sentiment"]
        mentions = r["mentions"]

        if chg is not None:
            if chg <= -1.0 and sentiment >= 0.2:
                signals.append({
                    "type": "bullish_dip",
                    "ticker": ticker,
                    "headline": f"{ticker} down {abs(chg)}% but chatter stays bullish",
                    "detail": f"{r['bullish_pct']}% of {mentions} messages are bullish "
                              f"while the stock fell {abs(chg)}% today — could be dip-buying "
                              f"conviction or complacency into weakness.",
                    "magnitude": abs(chg) * max(sentiment, 0.01),
                })
            elif chg >= 1.0 and sentiment <= -0.2:
                signals.append({
                    "type": "bearish_rally",
                    "ticker": ticker,
                    "headline": f"{ticker} up {chg}% despite bearish chatter",
                    "detail": f"{r['bearish_pct']}% of {mentions} messages are bearish "
                              f"while the stock rose {chg}% today — possible skepticism "
                              f"into strength, or short covering.",
                    "magnitude": abs(chg) * abs(min(sentiment, -0.01)),
                })

        baseline = mention_history.get(ticker)
        if baseline and len(baseline) >= 3:
            avg_baseline = sum(baseline) / len(baseline)
            if avg_baseline >= 2 and mentions > avg_baseline * 2:
                ratio = round(mentions / avg_baseline, 1)
                signals.append({
                    "type": "volume_spike",
                    "ticker": ticker,
                    "headline": f"{ticker} chatter running {ratio}x normal",
                    "detail": f"{mentions} messages today vs a ~{round(avg_baseline)}-message "
                              f"recent daily average — something is drawing attention.",
                    "magnitude": ratio,
                })

        media = r.get("media_sentiment")
        media_count = r.get("media_headline_count") or 0
        if media is not None and media_count >= 2:
            if media >= 0.25 and sentiment <= -0.2:
                signals.append({
                    "type": "media_divergence",
                    "ticker": ticker,
                    "headline": f"{ticker}: press upbeat, retail chatter bearish",
                    "detail": f"News coverage ({media_count} headlines) is reading positive "
                              f"while {r['bearish_pct']}% of {mentions} retail messages are "
                              f"bearish — the crowd and the press disagree.",
                    "magnitude": abs(media - sentiment),
                })
            elif media <= -0.25 and sentiment >= 0.2:
                signals.append({
                    "type": "media_divergence",
                    "ticker": ticker,
                    "headline": f"{ticker}: press bearish, retail chatter bullish",
                    "detail": f"News coverage ({media_count} headlines) is reading negative "
                              f"while {r['bullish_pct']}% of {mentions} retail messages are "
                              f"bullish — the crowd and the press disagree.",
                    "magnitude": abs(media - sentiment),
                })

        rm = r.get("reddit_mentions")
        rm_prev = r.get("reddit_mentions_24h_ago")
        if rm and rm_prev and rm_prev >= 3 and rm > rm_prev * 2:
            ratio = round(rm / rm_prev, 1)
            signals.append({
                "type": "reddit_spike",
                "ticker": ticker,
                "headline": f"{ticker} Reddit mentions up {ratio}x in a day",
                "detail": f"{rm} mentions today vs {rm_prev} yesterday across Reddit stock "
                          f"subs — independent of StockTwits, attention is building here too.",
                "magnitude": ratio,
            })

        si_today = r.get("search_interest_today")
        si_baseline = r.get("search_interest_baseline")
        if si_today is not None and si_baseline and si_baseline >= 5 and si_today > si_baseline * 2:
            ratio = round(si_today / si_baseline, 1)
            signals.append({
                "type": "search_spike",
                "ticker": ticker,
                "headline": f"{ticker} Google search interest up {ratio}x",
                "detail": f"Search interest at {si_today}/100 today vs a ~{round(si_baseline)} "
                          f"recent daily average — independent of StockTwits and Reddit, public "
                          f"search attention is spiking too.",
                "magnitude": ratio,
            })

        # The Divergence Engine: full pairwise comparison across all four
        # pillars (Crowd/Wall Street/Business/Market), not just Crowd vs.
        # the AI's fused score. This is the actual moat, not a feature —
        # see PRODUCT.md's "The moat: Divergence + Change + Track Record."
        pillars = pillar_scores.get(ticker) if pillar_scores else None
        if pillars:
            pattern, detail_text = classify_divergence(pillars)
            if pattern:
                signals.append(_build_divergence_signal(ticker, pattern, pillars, detail_text))

    signals.sort(key=lambda s: s["magnitude"], reverse=True)
    return signals[:8]


# Wall Street pillar scores cluster structurally higher than the other
# three — sell-side analysts rarely issue Sell ratings, so a "neutral"
# Wall Street read sits well above a neutral Crowd/Business/Market read.
# Live testing (2026-08-13) showed even a stock as troubled as Boeing
# scoring 76/100 on Wall Street consensus. Using one universal threshold
# across all four pillars would make "Wall Street confirms" nearly
# always true and "Wall Street doesn't confirm" nearly never fire — so
# Wall Street gets its own, higher-calibrated bucket.
_DEFAULT_LEVEL_THRESHOLDS = (35, 65)
_WALLSTREET_LEVEL_THRESHOLDS = (55, 78)

DIVERGENCE_PATTERNS = {
    "emerging_consensus": {"label": "Emerging Consensus", "icon": "🔥"},
    "retail_euphoria": {"label": "Retail Euphoria", "icon": "⚠️"},
    "fundamental_deterioration": {"label": "Fundamental Deterioration", "icon": "🧨"},
    "under_the_radar": {"label": "Under-the-Radar", "icon": "💎"},
}


def _pillar_level(score, thresholds=_DEFAULT_LEVEL_THRESHOLDS):
    if score is None:
        return None
    lo, hi = thresholds
    if score >= hi:
        return "high"
    if score <= lo:
        return "low"
    return "mid"


def classify_divergence(pillars):
    """pillars: {"crowd", "wall_street", "business", "market"} each a
    0-100 score or None. Returns (pattern_key, None) or (None, None) if
    there isn't enough data (fewer than 3 pillars present) or nothing
    about this ticker's pillar mix matches a named pattern — most
    tickers on most days won't match anything, which is correct: this
    should flag real alignment or real disagreement, not fire on
    every ticker every day."""
    crowd = _pillar_level(pillars.get("crowd"))
    wall_street = _pillar_level(pillars.get("wall_street"), _WALLSTREET_LEVEL_THRESHOLDS)
    business = _pillar_level(pillars.get("business"))
    market = _pillar_level(pillars.get("market"))

    if sum(1 for v in (crowd, wall_street, business, market) if v is not None) < 3:
        return None, None

    if crowd == "high" and wall_street == "high" and business == "high" and market == "high":
        return "emerging_consensus", None
    if crowd == "high" and wall_street in ("mid", "low") and business in ("mid", "low"):
        return "retail_euphoria", None
    if business == "low" and (crowd == "high" or market == "high"):
        return "fundamental_deterioration", None
    if wall_street == "high" and business == "high" and crowd in ("mid", "low"):
        return "under_the_radar", None
    return None, None


def _fmt_pillar(label, score):
    return f"{label} {score}/100" if score is not None else f"{label} n/a"


def _build_divergence_signal(ticker, pattern, pillars, _unused=None):
    meta = DIVERGENCE_PATTERNS[pattern]
    crowd, ws, biz, mkt = (pillars.get("crowd"), pillars.get("wall_street"),
                            pillars.get("business"), pillars.get("market"))
    pillar_summary = ", ".join([
        _fmt_pillar("Crowd", crowd), _fmt_pillar("Wall Street", ws),
        _fmt_pillar("Business", biz), _fmt_pillar("Market", mkt),
    ])

    if pattern == "emerging_consensus":
        headline = f"{ticker}: all four pillars point the same way"
        detail = f"{pillar_summary} — rare full alignment across crowd sentiment, analysts, fundamentals, and price momentum."
    elif pattern == "retail_euphoria":
        headline = f"{ticker}: retail conviction is running ahead of the rest"
        detail = f"{pillar_summary} — the crowd is hot, but Wall Street and the business itself haven't confirmed it yet."
    elif pattern == "fundamental_deterioration":
        headline = f"{ticker}: price and chatter are up, but the business is weakening"
        detail = f"{pillar_summary} — sentiment and/or price are strong while the underlying business metrics are not."
    else:  # under_the_radar
        headline = f"{ticker}: professionals like this more than retail has noticed"
        detail = f"{pillar_summary} — Wall Street and the fundamentals are both strong, but retail attention hasn't caught up yet."

    present = [v for v in (crowd, ws, biz, mkt) if v is not None]
    spread = (max(present) - min(present)) / 100 if len(present) >= 2 else 0
    # Weighted above single-source signals (volume/reddit spikes, price
    # divergence) since this is corroborated across up to 4 independent
    # reads, not one — same reasoning as the old ai_divergence weighting.
    magnitude = spread * 2.5

    return {
        "type": pattern,
        "ticker": ticker,
        "headline": headline,
        "detail": detail,
        "magnitude": magnitude,
    }


def build_sections(results, watchlist, min_mentions, quotes=None):
    """Split flat results into the distinct views the dashboard needs, so
    volume, bullish, and bearish rankings stay separate."""
    quotes = quotes or {}
    eligible = [r for r in results if r["mentions"] >= min_mentions]

    top_bullish = sorted(
        [r for r in eligible if r["avg_sentiment"] > 0.1],
        key=lambda r: r["avg_sentiment"], reverse=True
    )[:8]

    top_bearish = sorted(
        [r for r in eligible if r["avg_sentiment"] < -0.1],
        key=lambda r: r["avg_sentiment"]
    )[:8]

    most_discussed = sorted(eligible, key=lambda r: r["mentions"], reverse=True)[:12]

    by_ticker = {r["ticker"]: r for r in results}
    watchlist_grid = []
    for t in sorted(watchlist):
        if t in by_ticker:
            watchlist_grid.append(by_ticker[t])
        else:
            # No chatter today, but still show real price/chart data if we
            # have it — a watchlist ticker shouldn't need chatter to chart.
            q = quotes.get(t) or {}
            watchlist_grid.append({
                "ticker": t, "mentions": 0, "avg_sentiment": 0,
                "label": "No chatter", "bullish_count": 0, "bearish_count": 0,
                "neutral_count": 0, "bullish_pct": 0, "bearish_pct": 0,
                "in_watchlist": True, "is_trending": False, "delta": None,
                "price": q.get("price"), "change_pct": q.get("change_pct"), "examples": [],
                "source_counts": {}, "reddit_mentions": None,
                "reddit_mentions_24h_ago": None, "reddit_upvotes": None,
                "media_sentiment": None, "media_label": None,
                "media_headline_count": None,
                "search_interest_today": None, "search_interest_baseline": None,
            })

    return top_bullish, top_bearish, most_discussed, watchlist_grid


def build_sentiment_history(history, ticker_results, watchlist):
    """Per-ticker daily avg_sentiment series (date + score), including
    today — lets the chart overlay retail mood over time against price,
    instead of leaving 'was the crowd right' as a sentence you have to
    take on faith. Days with zero chatter for a ticker are naturally
    absent (not faked as neutral), so the line can have real gaps."""
    series = {t: [] for t in watchlist}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for snap in history:
        date = snap.get("date")
        if date == today:
            # `history` was loaded before this run started, so any entry
            # already dated today is stale — this run's ticker_results
            # below is the freshest version of today and supersedes it.
            continue
        for tkr, entry in snap.get("tickers", {}).items():
            if tkr not in series:
                continue
            val = entry.get("avg_sentiment") if isinstance(entry, dict) else entry
            if val is not None:
                series[tkr].append({"date": date, "avg_sentiment": val})

    for r in ticker_results:
        if r["ticker"] in series:
            series[r["ticker"]].append({"date": today, "avg_sentiment": r["avg_sentiment"]})

    # Need at least two points to draw a line; anything thinner isn't
    # worth rendering yet and the frontend treats "missing" as "still
    # building history" rather than an error.
    return {t: v for t, v in series.items() if len(v) >= 2}


def build_signal_snapshot(pillar_scores, signals, quotes):
    """One record per flagship ticker: all four pillar scores, today's
    Divergence Engine classification if any, a data-coverage confidence
    measure, and today's price. This is the raw material Phase 4's
    track record and 'why did the score change' features will read
    from — `confidence` is a real computed value (share of the 4
    pillars with actual data), not a placeholder, per the explicit
    warning in PRODUCT.md against unexplained numbers. `market_regime`
    is intentionally omitted for now rather than faked — it needs a
    real market-wide (not per-ticker) volatility classification that
    doesn't exist yet."""
    by_ticker_pattern = {s["ticker"]: s["type"] for s in signals if s["type"] in DIVERGENCE_PATTERNS}

    snapshot = {}
    for ticker, pillars in pillar_scores.items():
        present = [v for v in pillars.values() if v is not None]
        confidence = round(len(present) / 4 * 100) if pillars else 0
        snapshot[ticker] = {
            "crowd": pillars.get("crowd"),
            "wall_street": pillars.get("wall_street"),
            "business": pillars.get("business"),
            "market": pillars.get("market"),
            "divergence": by_ticker_pattern.get(ticker),
            "confidence": confidence,
            "price": (quotes.get(ticker) or {}).get("price"),
        }
    return snapshot


def _period_change(history):
    """First-to-last % change over a price_history series, for giving the
    analyst model real recent-trend context instead of just today's move."""
    if not history or len(history) < 2:
        return None, None
    first, last = history[0]["close"], history[-1]["close"]
    if not first:
        return None, None
    return round((last - first) / first * 100, 1), len(history)


def _news_for_ticker(news_items, ticker):
    matched = []
    for n in news_items:
        text = f"{n.get('title', '')} {n.get('summary', '')}"
        if ticker in extract_tickers(text, {ticker}):
            matched.append(n)
    return matched


def _normalize_crowd_score(sentiment):
    """avg_sentiment is mathematically bounded to [-MAX_SCORE_MAGNITUDE,
    +MAX_SCORE_MAGNITUDE] (see sentiment.py), not [-1, +1] — every other
    pillar is 0-100, so normalize against the real bound. Using 1.0 here
    would silently compress the whole real range into ~20-80 and the
    score could never reach either end of the scale."""
    if not sentiment or sentiment.get("avg_sentiment") is None or not sentiment.get("mentions"):
        return None
    normalized = (sentiment["avg_sentiment"] / MAX_SCORE_MAGNITUDE + 1) * 50
    return round(max(0.0, min(100.0, normalized)), 1)


def run_analyst_pipeline(flagship_tickers, ticker_results, news_items, price_history,
                          quotes, sleep_seconds=7):
    """Runs all four pillars for a small, deliberately-scoped set of
    flagship tickers — not the whole ~50-ticker universe the rest of the
    pipeline touches, since every AI call costs quota (and eventually
    money). Feeds the AI analyst real fundamentals, sentiment, Wall
    Street data, market context, and matched news — never empty
    placeholders. Returns (analyst_results, pillar_scores, fundamentals_data):
    pillar_scores is computed independently of whether the AI call itself
    succeeds, so the Divergence Engine always has real pillar numbers to
    compare even on a day the LLM call fails for a ticker.
    fundamentals_data carries the raw metrics + per-category coverage
    that fundamentals.py already computes — previously this was fed to
    the AI prompt and then discarded, leaving only a single blended
    0-100 score reachable by the dashboard. The Fundamental Intelligence
    page needs the real numbers, not just the score derived from them.
    history_data carries every timeframe's real, pre-resolved chart data
    and performance (see market_history.py) — a ticker missing here (no
    fetchable history at all) simply has no chart system for the day,
    never a fabricated one."""
    by_ticker = {r["ticker"]: r for r in ticker_results}
    analyst_results = {}
    pillar_scores = {}
    fundamentals_data = {}
    history_data = {}

    logo_results = {}
    for i, ticker in enumerate(flagship_tickers):
        print(f"  [analyst] analyzing {ticker} ({i + 1}/{len(flagship_tickers)})...")

        logo_results[ticker] = ensure_logo(ticker)

        f = fetch_fundamentals(ticker)
        fscore = score_fundamentals(f) if f else None

        w = fetch_analyst_data(ticker)
        wscore = score_wallstreet(w) if w else None

        hist = price_history.get(ticker, [])
        m = fetch_market_data(ticker, hist)
        mscore = score_market(m) if m else None

        sentiment = by_ticker.get(ticker)
        pillar_scores[ticker] = {
            "crowd": _normalize_crowd_score(sentiment),
            "wall_street": wscore.get("overall") if wscore else None,
            "business": fscore.get("overall") if fscore else None,
            "market": mscore.get("overall") if mscore else None,
        }

        if f:
            fundamentals_data[ticker] = {
                "name": f.get("name"),
                "sector": f.get("sector"),
                "metrics": {k: v for k, v in f.items() if k not in ("name", "sector")},
                "coverage": fscore.get("coverage") if fscore else None,
                "missing_categories": [k for k, v in (fscore.get("categories") or {}).items() if v is None] if fscore else [],
            }

        q = quotes.get(ticker, {})
        period_chg, period_days = _period_change(hist)
        price_ctx = {
            "price": q.get("price"),
            "change_pct": q.get("change_pct"),
            "period_change_pct": period_chg,
            "period_days": period_days,
        }

        q_history = q.get("history") or []
        previous_close = q_history[-2]["close"] if len(q_history) >= 2 else None
        ticker_history = build_ticker_history(ticker, live_price=q.get("price"), previous_close=previous_close)
        if ticker_history:
            history_data[ticker] = ticker_history
        matched_news = _news_for_ticker(news_items, ticker)

        result = analyze_stock(
            ticker, name=f.get("name") if f else ticker, sector=f.get("sector") if f else None,
            fundamentals=f, fscore=fscore, sentiment=sentiment, price=price_ctx,
            news_items=matched_news, wallstreet=w, wscore=wscore, market=m, mscore=mscore,
        )
        if result:
            result["_fundamentals_score"] = fscore.get("overall") if fscore else None
            result["_wallstreet_score"] = wscore.get("overall") if wscore else None
            result["_market_score"] = mscore.get("overall") if mscore else None
            analyst_results[ticker] = result

        if i < len(flagship_tickers) - 1:
            time.sleep(sleep_seconds)

    print(f"  [analyst] {len(analyst_results)}/{len(flagship_tickers)} tickers analyzed successfully")
    print(f"  [logos] {sum(logo_results.values())}/{len(logo_results)} tickers have a real cached logo "
          f"(rest fall back to the letter avatar)")
    print(f"  [history] {len(history_data)}/{len(flagship_tickers)} tickers have real multi-timeframe chart data")
    return analyst_results, pillar_scores, fundamentals_data, history_data


def render_dashboard(payload):
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()
    html = template.replace("/*__DATA__*/", json.dumps(payload, indent=2))
    os.makedirs(os.path.dirname(DASHBOARD_PATH), exist_ok=True)
    with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html)


def render_sentiment_page(payload):
    """Same embed-and-write pattern as render_dashboard, same payload —
    the Sentiment Intelligence page is a new view over data the pipeline
    already computes, not a new data source."""
    with open(SENTIMENT_TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()
    html = template.replace("/*__DATA__*/", json.dumps(payload, indent=2))
    os.makedirs(os.path.dirname(SENTIMENT_PAGE_PATH), exist_ok=True)
    with open(SENTIMENT_PAGE_PATH, "w", encoding="utf-8") as f:
        f.write(html)


def render_fundamentals_page(payload):
    """Same pattern again — the Fundamental Intelligence page reads the
    same payload's `fundamentals` key, no separate data source."""
    with open(FUNDAMENTALS_TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()
    html = template.replace("/*__DATA__*/", json.dumps(payload, indent=2))
    os.makedirs(os.path.dirname(FUNDAMENTALS_PAGE_PATH), exist_ok=True)
    with open(FUNDAMENTALS_PAGE_PATH, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    config = load_config()
    watchlist = set(config["watchlist"])
    min_mentions = config.get("min_mentions_to_show", 2)

    print("Fetching StockTwits trending + watchlist activity...")
    symbol_messages, trending_symbols = collect_all(
        watchlist,
        trending_limit=config.get("trending_limit", 0),
        max_age_hours=config.get("mentions_window_hours", 24.0),
        hard_limit=config.get("mentions_hard_ceiling", 400),
    )
    st_messages = sum(len(v) for v in symbol_messages.values())
    print(f"  collected {st_messages} messages across {len(symbol_messages)} tickers")

    print("Fetching Reddit retail chatter...")
    known_symbols = set(symbol_messages.keys()) | watchlist | trending_symbols
    reddit_messages = collect_reddit(
        known_symbols, watchlist,
        subreddits=config.get("reddit_subreddits", []),
        post_limit=config.get("reddit_post_limit", 75),
        comments_per_watchlist_post=config.get("reddit_comments_per_watchlist_post", 15),
    )
    for ticker, msgs in reddit_messages.items():
        symbol_messages.setdefault(ticker, []).extend(msgs)

    total_messages = sum(len(v) for v in symbol_messages.values())
    print(f"  {total_messages} total messages across {len(symbol_messages)} tickers "
          f"({st_messages} StockTwits, {total_messages - st_messages} Reddit)")

    history = load_history()
    prev_snapshot = history[-1]["tickers"] if history else None

    print("Scoring sentiment per ticker...")
    ticker_results = analyze(
        symbol_messages, trending_symbols, watchlist, prev_snapshot,
        sentiment_sample_size=config.get("sentiment_sample_size", 60),
        sentiment_call_sleep_seconds=config.get("sentiment_call_sleep_seconds", 3.0),
    )

    # Union with the full watchlist, not just tickers with chatter today —
    # a watchlist ticker should still get a price/chart even on a quiet day.
    price_symbols = sorted({r["ticker"] for r in ticker_results} | watchlist)
    chart_period = config.get("chart_history_period", "3mo")
    print(f"Fetching live prices + {chart_period} history for {len(price_symbols)} tickers "
          f"(this is the slow part)...")
    quotes = fetch_quotes(price_symbols, period=chart_period)
    ticker_results = merge_price_data(ticker_results, quotes)
    price_history = {sym: q["history"] for sym, q in quotes.items() if q.get("history")}
    print(f"  got prices for {len(quotes)}/{len(price_symbols)} tickers")

    print("Fetching ApeWisdom Reddit mention volume (independent attention check)...")
    reddit_mentions = fetch_reddit_mentions(config.get("apewisdom_max_pages", 5))
    ticker_results = merge_reddit_mentions(ticker_results, reddit_mentions)
    print(f"  matched {sum(1 for r in ticker_results if r['reddit_mentions'] is not None)}"
          f"/{len(ticker_results)} tickers to ApeWisdom data")

    if config.get("google_trends_enabled", True):
        trend_tickers = sorted(watchlist)
        print(f"Fetching Google Trends search interest for {len(trend_tickers)} tickers "
              f"(slow — Google rate-limits aggressively)...")
        search_interest = fetch_search_interest(
            trend_tickers, sleep_seconds=config.get("google_trends_sleep_seconds", 20.0)
        )
        ticker_results = merge_search_interest(ticker_results, search_interest)
        print(f"  matched {len(search_interest)}/{len(trend_tickers)} tickers to Trends data")

    flagship_tickers = config.get("flagship_tickers", [])

    # News Intelligence System — three tiers, each answering a different
    # question, not one bigger ranked pile. See PRODUCT.md.
    print("Fetching Material Events (SEC EDGAR 8-K filings — Tier 1)...")
    material_events = fetch_recent_8ks(
        flagship_tickers, days=config.get("material_events_lookback_days", 7)
    )
    print(f"  found recent 8-K filings for {len(material_events)}/{len(flagship_tickers)} tickers")

    print("Fetching and ranking company-specific news (Tier 2)...")
    raw_company_news = fetch_ticker_news(flagship_tickers)
    company_news = {}
    for i, ticker in enumerate(flagship_tickers):
        items = raw_company_news.get(ticker)
        if not items:
            continue
        ranked = rank_news(ticker, ticker, items)
        for it in ranked:
            it["sentiment_score"] = round(score_text(it["title"]), 3)
            it["sentiment_label"] = label_for_score(it["sentiment_score"])
        kept = [it for it in ranked if it.get("keep", True)]
        kept.sort(key=lambda it: it.get("importance") or 0, reverse=True)
        if kept:
            company_news[ticker] = kept[:8]
        if i < len(flagship_tickers) - 1:
            time.sleep(config.get("news_ranker_sleep_seconds", 3))
    print(f"  kept ranked company news for {len(company_news)}/{len(flagship_tickers)} tickers")

    print("Fetching and scoring broad market news (Tier 3)...")
    news_items = score_news(fetch_news(config["news_feeds"]))
    print(f"  collected {len(news_items)} headlines")

    media_sentiment = build_media_sentiment(news_items, known_symbols)
    ticker_results = merge_media_sentiment(ticker_results, media_sentiment)
    print(f"  matched media sentiment for {len(media_sentiment)} tickers")

    analyst_results = {}
    pillar_scores = {}
    fundamentals_data = {}
    history_data = {}
    if flagship_tickers:
        print(f"Running the 4-pillar engine + AI analyst on {len(flagship_tickers)} flagship tickers...")
        analyst_results, pillar_scores, fundamentals_data, history_data = run_analyst_pipeline(
            flagship_tickers, ticker_results, news_items, price_history, quotes,
            sleep_seconds=config.get("analyst_call_sleep_seconds", 7),
        )

    print("Computing signals (divergences, volume spikes, the Divergence Engine)...")
    signals = compute_signals(ticker_results, history, pillar_scores)

    top_bullish, top_bearish, most_discussed, watchlist_grid = build_sections(
        ticker_results, watchlist, min_mentions, quotes
    )

    print("Generating today's market insight (one real LLM call, not a template)...")
    market_insight = build_market_insight(watchlist_grid)
    print(f"  {'generated' if market_insight else 'unavailable — will show an honest empty state'}")

    sentiment_history = build_sentiment_history(history, ticker_results, watchlist)

    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %I:%M %p %Z")

    print("Building dashboard...")
    payload = {
        "generated_at": generated_at,
        "total_messages": total_messages,
        "total_tickers": len(symbol_messages),
        "signals": signals,
        "top_bullish": top_bullish,
        "top_bearish": top_bearish,
        "most_discussed": most_discussed,
        "watchlist_grid": watchlist_grid,
        "news": news_items,
        "price_history": price_history,
        "sentiment_history": sentiment_history,
        "analyst": analyst_results,
        "pillar_scores": pillar_scores,
        "fundamentals": fundamentals_data,
        "timeframe_history": history_data,
        "market_insight": market_insight,
        "material_events": material_events,
        "company_news": company_news,
    }
    render_dashboard(payload)
    render_sentiment_page(payload)
    render_fundamentals_page(payload)

    save_history(history, {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "tickers": {
            t["ticker"]: {"avg_sentiment": t["avg_sentiment"], "mentions": t["mentions"]}
            for t in ticker_results
        },
    }, config.get("history_days_to_keep", 30))

    if analyst_results:
        analyst_history = load_analyst_history()
        save_analyst_history(analyst_history, {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "model": ANALYST_MODEL,
            "tickers": analyst_results,
        }, config.get("analyst_history_days_to_keep", 90))

    if pillar_scores:
        signal_history = load_signal_history()
        save_signal_history(signal_history, {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "tickers": build_signal_snapshot(pillar_scores, signals, quotes),
        }, config.get("signal_history_days_to_keep", 365))

    print(f"\nDone. Open {DASHBOARD_PATH} in your browser.")


if __name__ == "__main__":
    main()
