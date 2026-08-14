"""
Lightweight, frequent price-only refresh — separate from main.py's full
daily pipeline (sentiment, news, AI analysis). Runs every ~15 minutes via
its own GitHub Actions workflow so prices on the live dashboard feel
current without re-running anything rate-limited or LLM-backed.
"""

import json
import os
from datetime import datetime, timezone

from market_data import fetch_quotes

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.json")
QUOTES_PATH = os.path.join(ROOT, "docs", "quotes.json")


def load_tickers():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return config["watchlist"]


def main():
    tickers = load_tickers()
    raw = fetch_quotes(tickers, period="5d")
    quotes = {
        sym: {"price": q["price"], "change_pct": q["change_pct"]}
        for sym, q in raw.items()
    }
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "quotes": quotes,
    }
    os.makedirs(os.path.dirname(QUOTES_PATH), exist_ok=True)
    with open(QUOTES_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {len(quotes)} quotes to {QUOTES_PATH}")


if __name__ == "__main__":
    main()
