"""
Lightweight, frequent price-only refresh — separate from main.py's full
daily pipeline (sentiment, news, AI analysis). Runs every ~15 minutes via
its own GitHub Actions workflow so prices on the live dashboard feel
current without re-running anything rate-limited or LLM-backed.

Also carries previous_close (the exact prior-session close, for 1D chart
math that must never drift from what the daily pipeline separately
computed) and a real market_status, computed from the actual NYSE
calendar via pandas_market_calendars — not a hardcoded holiday list that
would silently go stale year over year.
"""

import json
import os
from datetime import datetime, timezone

import pandas as pd
import pandas_market_calendars as mcal

from market_data import MACRO_INSTRUMENTS, fetch_quotes

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.json")
QUOTES_PATH = os.path.join(ROOT, "docs", "quotes.json")

_NYSE = mcal.get_calendar("NYSE")

# Pre-market conventionally opens around 4:00am ET, 5.5 hours before the
# 9:30am regular open; after-hours runs to about 8:00pm ET, 4 hours after
# the 4:00pm close. Everything else on a real trading day is "closed"
# (overnight), and a day with no NYSE session at all is "weekend" or
# "holiday" depending on which it actually is.
def market_status(now_utc: datetime) -> str:
    sched = _NYSE.schedule(start_date=now_utc.date(), end_date=now_utc.date())
    if sched.empty:
        return "weekend" if now_utc.weekday() >= 5 else "holiday"
    open_t = sched.iloc[0]["market_open"].to_pydatetime()
    close_t = sched.iloc[0]["market_close"].to_pydatetime()
    now = pd.Timestamp(now_utc)
    if now < open_t - pd.Timedelta(hours=5.5):
        return "closed"
    if now < open_t:
        return "pre-market"
    if now <= close_t:
        return "open"
    if now <= close_t + pd.Timedelta(hours=4):
        return "after-hours"
    return "closed"


def load_tickers():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return config["watchlist"]


def main():
    tickers = load_tickers()
    raw = fetch_quotes(tickers, period="5d")
    status = market_status(datetime.now(timezone.utc))
    quotes = {}
    for sym, q in raw.items():
        hist = q.get("history") or []
        previous_close = hist[-2]["close"] if len(hist) >= 2 else None
        quotes[sym] = {
            "price": q["price"],
            "change_pct": q["change_pct"],
            "previous_close": previous_close,
            "market_status": status,
        }
    # Macro instruments (indices, crypto, commodities, global markets) have
    # no once-daily source the way the flagship watchlist does (they're not
    # part of main.py's pipeline at all), so this file is their only
    # supplier — history is kept (unlike the flagship quotes above) so the
    # dashboard's Markets strip has something to sparkline.
    macro_raw = fetch_quotes([m[0] for m in MACRO_INSTRUMENTS], period="1mo")
    macro = {}
    for sym, name, category in MACRO_INSTRUMENTS:
        q = macro_raw.get(sym)
        if not q:
            continue
        m_hist = q.get("history") or []
        macro[sym] = {
            "name": name,
            "category": category,
            "price": q["price"],
            "change_pct": q["change_pct"],
            "previous_close": m_hist[-2]["close"] if len(m_hist) >= 2 else None,
            "history": q["history"],
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "quotes": quotes,
        "macro": macro,
    }
    os.makedirs(os.path.dirname(QUOTES_PATH), exist_ok=True)
    with open(QUOTES_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {len(quotes)} quotes + {len(macro)} macro instruments to {QUOTES_PATH} (market_status={status})")


if __name__ == "__main__":
    main()
