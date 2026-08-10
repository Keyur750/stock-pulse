"""
Stock Pulse — daily retail sentiment + price + news dashboard.

Run this once a day (see README for scheduling). It pulls trending +
watchlist ticker activity from StockTwits, scores sentiment, cross-checks
it against real price action, pulls financial news, and writes a fresh
dashboard.html you open in your browser.

Usage: python main.py
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from stocktwits import collect_all
from news_fetcher import fetch_news
from sentiment import score_message, label_for_score, classify_message
from market_data import fetch_quotes, fetch_market_pulse, fetch_sector_heatmap

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
# docs/index.html is what GitHub Pages serves as your live website.
DASHBOARD_PATH = os.path.join(ROOT, "docs", "index.html")
TEMPLATE_PATH = os.path.join(ROOT, "dashboard_template.html")


def load_config():
    with open(os.path.join(ROOT, "config.json")) as f:
        return json.load(f)


def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH) as f:
            return json.load(f)
    return []


def save_history(history, today_snapshot, keep_days=30):
    history.append(today_snapshot)
    history = history[-keep_days:]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
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
        })
    return results


def merge_price_data(results, quotes):
    for r in results:
        q = quotes.get(r["ticker"])
        if q:
            r["price"] = q["price"]
            r["change_pct"] = q["change_pct"]
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

    signals.sort(key=lambda s: s["magnitude"], reverse=True)
    return signals[:8]


def build_sections(results, watchlist, min_mentions):
    """Split flat results into the distinct views the dashboard needs, so
    volume, bullish, and bearish rankings stay separate."""
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
            watchlist_grid.append({
                "ticker": t, "mentions": 0, "avg_sentiment": 0,
                "label": "No chatter", "bullish_count": 0, "bearish_count": 0,
                "neutral_count": 0, "bullish_pct": 0, "bearish_pct": 0,
                "in_watchlist": True, "is_trending": False, "delta": None,
                "price": None, "change_pct": None, "examples": [],
            })

    return top_bullish, top_bearish, most_discussed, watchlist_grid


def render_dashboard(payload):
    with open(TEMPLATE_PATH) as f:
        template = f.read()
    html = template.replace("/*__DATA__*/", json.dumps(payload, indent=2))
    os.makedirs(os.path.dirname(DASHBOARD_PATH), exist_ok=True)
    with open(DASHBOARD_PATH, "w") as f:
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
    total_messages = sum(len(v) for v in symbol_messages.values())
    print(f"  collected {total_messages} messages across {len(symbol_messages)} tickers")

    history = load_history()
    prev_snapshot = history[-1]["tickers"] if history else None

    print("Scoring sentiment per ticker...")
    ticker_results = analyze(symbol_messages, trending_symbols, watchlist, prev_snapshot)

    price_symbols = sorted({r["ticker"] for r in ticker_results})
    print(f"Fetching live prices for {len(price_symbols)} tickers (this is the slow part)...")
    quotes = fetch_quotes(price_symbols)
    ticker_results = merge_price_data(ticker_results, quotes)
    print(f"  got prices for {len(quotes)}/{len(price_symbols)} tickers")

    print("Fetching market pulse (indices) and sector heatmap...")
    market_pulse = fetch_market_pulse()
    sector_heatmap = fetch_sector_heatmap()

    print("Computing signals (divergences, volume spikes)...")
    signals = compute_signals(ticker_results, history)

    top_bullish, top_bearish, most_discussed, watchlist_grid = build_sections(
        ticker_results, watchlist, min_mentions
    )

    print("Fetching financial news...")
    news_items = fetch_news(config["news_feeds"])
    print(f"  collected {len(news_items)} headlines")

    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %I:%M %p %Z")

    print("Building dashboard...")
    payload = {
        "generated_at": generated_at,
        "total_messages": total_messages,
        "total_tickers": len(symbol_messages),
        "market_pulse": market_pulse,
        "sector_heatmap": sector_heatmap,
        "signals": signals,
        "top_bullish": top_bullish,
        "top_bearish": top_bearish,
        "most_discussed": most_discussed,
        "watchlist_grid": watchlist_grid,
        "news": news_items,
    }
    render_dashboard(payload)

    save_history(history, {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "tickers": {
            t["ticker"]: {"avg_sentiment": t["avg_sentiment"], "mentions": t["mentions"]}
            for t in ticker_results
        },
    }, config.get("history_days_to_keep", 30))

    print(f"\nDone. Open {DASHBOARD_PATH} in your browser.")


if __name__ == "__main__":
    main()
