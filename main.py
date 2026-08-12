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
from news_fetcher import fetch_news
from sentiment import score_message, score_text, label_for_score, classify_message
from reddit import extract_tickers
from market_data import fetch_quotes
from fundamentals import fetch_fundamentals, score_fundamentals
from analyst import analyze_stock, MODEL as ANALYST_MODEL

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
ANALYST_HISTORY_PATH = os.path.join(DATA_DIR, "analyst_history.json")
# docs/index.html is the static marketing homepage (not touched by this
# script); the live data dashboard is served from docs/dashboard.html.
DASHBOARD_PATH = os.path.join(ROOT, "docs", "dashboard.html")
TEMPLATE_PATH = os.path.join(ROOT, "dashboard_template.html")


def load_config():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history, today_snapshot, keep_days=30):
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
    history.append(today_snapshot)
    history = history[-keep_days:]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ANALYST_HISTORY_PATH, "w", encoding="utf-8") as f:
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


def analyze(symbol_messages: dict, trending_symbols: set, watchlist: set,
            prev_snapshot: Optional[dict]):
    """Aggregate mention counts, bull/bear breakdown, and sentiment per
    ticker, with day-over-day sentiment shift where history allows."""
    results = []
    for symbol, messages in symbol_messages.items():
        if not messages:
            continue

        scores = [score_message(m) for m in messages]
        avg = sum(scores) / len(scores)

        classes = [classify_message(m) for m in messages]
        bullish_count = classes.count("bullish")
        bearish_count = classes.count("bearish")
        neutral_count = classes.count("neutral")
        total = len(classes)
        bullish_pct = round(100 * bullish_count / total) if total else 0
        bearish_pct = round(100 * bearish_count / total) if total else 0

        examples = []
        for m in messages[:3]:
            examples.append({"title": (m.get("body") or "")[:120]})

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


def compute_signals(results, history):
    """Auto-generate analyst-style callouts: price/sentiment divergences
    and abnormal chatter-volume spikes. This is the highest-value output —
    surfacing the handful of tickers where the crowd and the tape disagree,
    or where something is unusually loud, instead of making you scan every
    row yourself."""
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

    signals.sort(key=lambda s: s["magnitude"], reverse=True)
    return signals[:8]


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
            })

    return top_bullish, top_bearish, most_discussed, watchlist_grid


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


def run_analyst_pipeline(flagship_tickers, ticker_results, news_items, price_history,
                          quotes, sleep_seconds=7):
    """Runs the AI analyst model for a small, deliberately-scoped set of
    flagship tickers — not the whole ~50-ticker universe the rest of the
    pipeline touches, since every call costs quota (and eventually money).
    Feeds it real fundamentals, real sentiment, real recent price action,
    and real matched news — never empty placeholders."""
    by_ticker = {r["ticker"]: r for r in ticker_results}
    results = {}

    for i, ticker in enumerate(flagship_tickers):
        print(f"  [analyst] analyzing {ticker} ({i + 1}/{len(flagship_tickers)})...")

        f = fetch_fundamentals(ticker)
        fscore = score_fundamentals(f) if f else None

        sentiment = by_ticker.get(ticker)
        q = quotes.get(ticker, {})
        period_chg, period_days = _period_change(price_history.get(ticker, []))
        price_ctx = {
            "price": q.get("price"),
            "change_pct": q.get("change_pct"),
            "period_change_pct": period_chg,
            "period_days": period_days,
        }
        matched_news = _news_for_ticker(news_items, ticker)

        result = analyze_stock(
            ticker, name=f.get("name") if f else ticker, sector=f.get("sector") if f else None,
            fundamentals=f, fscore=fscore, sentiment=sentiment, price=price_ctx,
            news_items=matched_news,
        )
        if result:
            result["_fundamentals_score"] = fscore.get("overall") if fscore else None
            results[ticker] = result

        if i < len(flagship_tickers) - 1:
            time.sleep(sleep_seconds)

    print(f"  [analyst] {len(results)}/{len(flagship_tickers)} tickers analyzed successfully")
    return results


def render_dashboard(payload):
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()
    html = template.replace("/*__DATA__*/", json.dumps(payload, indent=2))
    os.makedirs(os.path.dirname(DASHBOARD_PATH), exist_ok=True)
    with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    config = load_config()
    watchlist = set(config["watchlist"])
    min_mentions = config.get("min_mentions_to_show", 2)

    print("Fetching StockTwits trending + watchlist activity...")
    symbol_messages, trending_symbols = collect_all(
        watchlist,
        trending_limit=config.get("trending_limit", 30),
        messages_per_symbol=config.get("messages_per_symbol", 30),
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
    ticker_results = analyze(symbol_messages, trending_symbols, watchlist, prev_snapshot)

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

    print("Fetching and scoring financial news...")
    news_items = score_news(fetch_news(config["news_feeds"]))
    print(f"  collected {len(news_items)} headlines")

    media_sentiment = build_media_sentiment(news_items, known_symbols)
    ticker_results = merge_media_sentiment(ticker_results, media_sentiment)
    print(f"  matched media sentiment for {len(media_sentiment)} tickers")

    flagship_tickers = config.get("flagship_tickers", [])
    analyst_results = {}
    if flagship_tickers:
        print(f"Running AI analyst model on {len(flagship_tickers)} flagship tickers...")
        analyst_results = run_analyst_pipeline(
            flagship_tickers, ticker_results, news_items, price_history, quotes,
            sleep_seconds=config.get("analyst_call_sleep_seconds", 7),
        )

    print("Computing signals (divergences, volume spikes)...")
    signals = compute_signals(ticker_results, history)

    top_bullish, top_bearish, most_discussed, watchlist_grid = build_sections(
        ticker_results, watchlist, min_mentions, quotes
    )

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
        "analyst": analyst_results,
    }
    render_dashboard(payload)

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

    print(f"\nDone. Open {DASHBOARD_PATH} in your browser.")


if __name__ == "__main__":
    main()
