"""
Multi-timeframe market data — the "MarketDataService" for the chart
system. Ticker-agnostic and config-driven (same shape as fundamentals.py
and logos.py): give it a symbol, get back a fully-resolved record with
every supported timeframe (1D/1W/1M/3M/6M/1Y/5Y/10Y/20Y) already computed
against real trading-session data. Adding a ticker to the watchlist never
requires touching this module.

This runs at batch time (once/day, inside main.py's pipeline), not as a
live request-time service — there is no runtime backend in this app to
host one. Everything here is deterministic given real fetched history,
so precomputing it is not a downgrade: the "live" 1D price on top of
this is handled separately by refresh_quotes.py's 15-minute cron, the
same mechanism the dashboard already polls.

Price-return, not total-return: fetch_full_history() uses
auto_adjust=False and reads the "Close" column (not "Adj Close"), which
is split-adjusted but not dividend-adjusted. This avoids fake price
jumps at split dates without blending in dividend reinvestment. If a
future feature wants total return, that's a deliberate, separate choice
using "Adj Close" instead — never mix the two.

Never fabricates: a timeframe with insufficient real history gets
data_available=False and an empty series, not an extrapolated or zeroed
value. See build_ticker_history()'s docstring for the exact shape.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

TIMEFRAMES = ["1D", "1W", "1M", "3M", "6M", "1Y", "5Y", "10Y", "20Y"]

# Calendar-day lookback used to find each timeframe's period-start target
# date, before resolve_period_start() snaps it to the nearest real prior
# trading session. 1D isn't here — it's handled separately against
# previous_close, not a lookback.
_LOOKBACK_DAYS = {
    "1W": 7, "1M": 30, "3M": 91, "6M": 182,
    "1Y": 365, "5Y": 365 * 5, "10Y": 365 * 10, "20Y": 365 * 20,
}


def fetch_full_history(ticker: str) -> pd.DataFrame | None:
    """Full available daily history, split-adjusted only (see module
    docstring). Returns None if the ticker has no usable history at all
    (bad symbol, delisted, network failure) — callers must treat that as
    "no data," never substitute anything."""
    try:
        df = yf.Ticker(ticker).history(period="max", interval="1d", auto_adjust=False)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
    return df if not df.empty else None


def fetch_intraday(ticker: str) -> pd.DataFrame | None:
    """Today's session shape for the 1D chart. 5-minute bars — yfinance
    only serves intraday data for a limited recent window, which is fine
    since this is only ever used for the current/most recent session."""
    try:
        df = yf.Ticker(ticker).history(period="1d", interval="5m", auto_adjust=False)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    return df if not df.empty else None


def resolve_period_start(daily_df: pd.DataFrame, target_date: datetime):
    """Market-aware lookup: the real trading session at or before
    target_date, found by searching the actual fetched index — never by
    assuming a row exists on an arbitrary calendar date. This is what
    makes weekend/holiday/missing-session handling automatic: a Saturday
    target simply isn't in the index, so the search naturally lands on
    the preceding Friday's real close.

    Returns (actual_date, close_price) or None if target_date is before
    the earliest data this ticker has (i.e. the requested timeframe
    genuinely exceeds available history)."""
    idx = daily_df.index
    eligible = idx[idx <= pd.Timestamp(target_date)]
    if len(eligible) == 0:
        return None
    actual_date = eligible[-1]
    return actual_date, float(daily_df.loc[actual_date, "Close"])


def _direction(pct_change: float) -> str:
    if pct_change > 0:
        return "up"
    if pct_change < 0:
        return "down"
    return "flat"


def compute_timeframe_performance(daily_df: pd.DataFrame, live_price: float | None,
                                   previous_close: float | None, as_of: datetime) -> dict:
    """Independently computes {period_start_date, period_start_price,
    current_price, abs_change, pct_change, direction, data_available} for
    every timeframe in TIMEFRAMES. Each is a self-contained comparison —
    1Y's color has nothing to do with 1D's, by construction."""
    latest_date = daily_df.index[-1]
    latest_close = float(daily_df.loc[latest_date, "Close"])
    current_price = live_price if live_price is not None else latest_close

    out = {}

    # 1D: current/live price vs the last COMPLETE prior session's close —
    # not intraday-vs-intraday, and not "today's close" (which wouldn't
    # exist yet while the market's open).
    prev_close = previous_close
    if prev_close is None and len(daily_df) >= 2:
        prev_close = float(daily_df.iloc[-2]["Close"])
    if prev_close:
        abs_change = current_price - prev_close
        pct_change = (abs_change / prev_close) * 100
        out["1D"] = {
            "period_start_date": None,
            "period_start_price": round(prev_close, 4),
            "current_price": round(current_price, 4),
            "abs_change": round(abs_change, 4),
            "pct_change": round(pct_change, 4),
            "direction": _direction(pct_change),
            "data_available": True,
        }
    else:
        out["1D"] = {"data_available": False}

    for tf in TIMEFRAMES:
        if tf == "1D":
            continue
        target = as_of - timedelta(days=_LOOKBACK_DAYS[tf])
        resolved = resolve_period_start(daily_df, target)
        if resolved is None:
            out[tf] = {"data_available": False}
            continue
        start_date, start_price = resolved
        if start_price == 0:
            out[tf] = {"data_available": False}
            continue
        abs_change = current_price - start_price
        pct_change = (abs_change / start_price) * 100
        out[tf] = {
            "period_start_date": start_date.strftime("%Y-%m-%d"),
            "period_start_price": round(start_price, 4),
            "current_price": round(current_price, 4),
            "abs_change": round(abs_change, 4),
            "pct_change": round(pct_change, 4),
            "direction": _direction(pct_change),
            "data_available": True,
        }
    return out


def _ohlcv_records(df: pd.DataFrame) -> list:
    return [
        {
            "date": idx.strftime("%Y-%m-%d %H:%M") if idx.time() != datetime.min.time() else idx.strftime("%Y-%m-%d"),
            "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
            "volume": int(row["Volume"]) if pd.notna(row["Volume"]) else None,
        }
        for idx, row in df.iterrows()
    ]


def downsample_for_display(daily_df: pd.DataFrame, intraday_df: pd.DataFrame | None,
                            timeframe: str, start_date) -> list:
    """Real OHLCV at the resolution appropriate for the timeframe — never
    thousands of daily points for a 20-year chart. 1D uses the real
    intraday bars; 1W-1Y use daily bars unmodified; 5Y aggregates to
    weekly; 10Y/20Y aggregate to monthly. Aggregation uses real
    high/low/volume sums within each bucket, not fabricated smoothing.

    `start_date` must be the SAME resolved period-start date
    compute_timeframe_performance() used for this timeframe (not an
    independently-recomputed lookback window) — otherwise the chart's
    first plotted point and the displayed period-start price could land
    on different real trading days and silently disagree."""
    if timeframe == "1D":
        return _ohlcv_records(intraday_df) if intraday_df is not None else []

    window = daily_df[daily_df.index >= pd.Timestamp(start_date)]
    if window.empty:
        window = daily_df

    if timeframe in ("1W", "1M", "3M", "6M", "1Y"):
        return _ohlcv_records(window)

    freq = "W" if timeframe == "5Y" else "ME"
    agg = window.resample(freq).agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum",
    }).dropna(subset=["Close"])
    return _ohlcv_records(agg)


def build_ticker_history(ticker: str, live_price: float | None = None,
                          previous_close: float | None = None) -> dict:
    """The single entry point: fetches real history for `ticker` and
    returns every timeframe pre-resolved and ready to embed in the page
    payload.

    {
      "years_available": 12.4,          # real span of daily_df, computed
      "has_full_20y": False,
      "timeframes": {
        "1D": {"series": [...], "performance": {...}},
        "1W": {...}, ..., "20Y": {...}
      }
    }

    A timeframe whose performance dict has data_available=False also gets
    an empty "series": [] — the UI shows the honest "N years available"
    message instead of a chart for that tab, never a fake or empty-looking
    chart pretending to have data.

    Returns None if no history could be fetched for this ticker at all —
    callers should treat that ticker as having no chart system today
    rather than substituting anything.
    """
    daily_df = fetch_full_history(ticker)
    if daily_df is None:
        return None
    intraday_df = fetch_intraday(ticker)

    as_of = datetime.now(timezone.utc).replace(tzinfo=None)
    years_available = (daily_df.index[-1] - daily_df.index[0]).days / 365.25

    performance = compute_timeframe_performance(daily_df, live_price, previous_close, as_of)

    timeframes = {}
    for tf in TIMEFRAMES:
        perf = performance[tf]
        if not perf.get("data_available"):
            timeframes[tf] = {"series": [], "performance": perf}
            continue
        # 1D's "period_start_date" is None (it's previous_close, not a
        # daily_df row) — the intraday series doesn't need a start-date
        # bound, so pass today's date as a harmless placeholder.
        start_date = perf["period_start_date"] or as_of.date().isoformat()
        series = downsample_for_display(daily_df, intraday_df, tf, start_date)
        timeframes[tf] = {"series": series, "performance": perf}

    return {
        "years_available": round(years_available, 1),
        "has_full_20y": years_available >= 19.5,
        "timeframes": timeframes,
    }
