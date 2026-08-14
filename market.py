"""
Market pillar — "where does the market already have this priced?" Free
via yfinance (52-week range, moving averages, beta, short interest) plus
realized volatility computed from price history already fetched
elsewhere in the pipeline. Same shape as fundamentals.py: raw metrics
always carried alongside the score, categories + weighted overall.

This score is deliberately NOT a "good/bad" verdict the way the
Business pillar is — a high score means "strong, stable upward
momentum, near highs," which can mean genuine strength OR that a
bullish thesis is already priced in. That distinction is exactly what
this pillar exists to let the Divergence Engine and the AI reason
about — see PRODUCT.md's "everyone agrees, but the stock is already up
150%" example.
"""

import statistics

import yfinance as yf


def fetch_market_data(symbol: str, price_history: list | None = None) -> dict | None:
    """Raw market/momentum metrics for a ticker, or None if the data
    couldn't be fetched. `price_history` is the same {date, close} list
    already fetched by market_data.py — reused here for realized
    volatility instead of a second API call."""
    try:
        info = yf.Ticker(symbol).info
    except Exception:
        return None
    if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
        return None

    def g(key):
        v = info.get(key)
        return v if isinstance(v, (int, float)) else None

    price = g("currentPrice") or g("regularMarketPrice")
    high_52w = g("fiftyTwoWeekHigh")
    low_52w = g("fiftyTwoWeekLow")
    avg_50d = g("fiftyDayAverage")
    avg_200d = g("twoHundredDayAverage")

    pct_from_high = ((price - high_52w) / high_52w * 100) if (price and high_52w) else None
    pct_from_low = ((price - low_52w) / low_52w * 100) if (price and low_52w) else None
    pct_from_50d = ((price - avg_50d) / avg_50d * 100) if (price and avg_50d) else None
    pct_from_200d = ((price - avg_200d) / avg_200d * 100) if (price and avg_200d) else None

    daily_volatility = None
    if price_history and len(price_history) >= 10:
        closes = [h["close"] for h in price_history if h.get("close")]
        returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1] * 100
            for i in range(1, len(closes)) if closes[i - 1]
        ]
        if len(returns) >= 5:
            daily_volatility = statistics.stdev(returns)

    return {
        "price": price,
        "fifty_two_week_high": high_52w,
        "fifty_two_week_low": low_52w,
        "fifty_day_avg": avg_50d,
        "two_hundred_day_avg": avg_200d,
        "pct_from_52w_high": round(pct_from_high, 1) if pct_from_high is not None else None,
        "pct_from_52w_low": round(pct_from_low, 1) if pct_from_low is not None else None,
        "pct_from_50d_avg": round(pct_from_50d, 1) if pct_from_50d is not None else None,
        "pct_from_200d_avg": round(pct_from_200d, 1) if pct_from_200d is not None else None,
        "daily_volatility_pct": round(daily_volatility, 2) if daily_volatility is not None else None,
        "beta": g("beta"),
        "short_percent_of_float": g("shortPercentOfFloat"),
        "short_ratio": g("shortRatio"),
    }


def _scale(value, points):
    """Same piecewise-linear interpolation as fundamentals.py."""
    if value is None:
        return None
    if value <= points[0][0]:
        return points[0][1]
    if value >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= value <= x1:
            return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
    return points[-1][1]


def _avg(scores):
    present = [s for s in scores if s is not None]
    return round(sum(present) / len(present), 1) if present else None


# Distance from 52-week high, in percent (always <= 0): closer to the
# high scores higher.
_EXTENSION_PTS = [(-60, 5), (-40, 22), (-25, 42), (-12, 62), (-4, 82), (0, 100)]
# Distance from moving averages, in percent (can be +/-): centered at 0
# = "at the average" = neutral (50).
_MA_50D_PTS = [(-25, 12), (-10, 32), (0, 50), (10, 70), (25, 90), (45, 100)]
_MA_200D_PTS = [(-35, 12), (-15, 32), (0, 50), (15, 70), (35, 90), (65, 100)]
# Daily realized volatility, in percentage points: calmer scores higher
# (this pillar rewards stable trends, not wild swings in either direction).
_VOLATILITY_PTS = [(0.5, 95), (1.0, 80), (1.75, 60), (2.75, 38), (4.0, 18), (6.0, 5)]


def score_market(m: dict) -> dict:
    """Turns raw market metrics into three 0-100 sub-scores plus a
    weighted overall. Missing data (e.g. no 52-week high on a fresh
    IPO) drops that category rather than guessing — `coverage` reports
    how many of the 3 categories had real data."""
    extension = _scale(m.get("pct_from_52w_high"), _EXTENSION_PTS)
    if extension is not None:
        extension = round(extension, 1)

    trend = _avg([_scale(m.get("pct_from_50d_avg"), _MA_50D_PTS),
                  _scale(m.get("pct_from_200d_avg"), _MA_200D_PTS)])

    stability = _scale(m.get("daily_volatility_pct"), _VOLATILITY_PTS)
    if stability is not None:
        stability = round(stability, 1)

    categories = {"extension": extension, "trend": trend, "stability": stability}
    weights = {"extension": 0.40, "trend": 0.35, "stability": 0.25}

    present = {k: v for k, v in categories.items() if v is not None}
    coverage = len(present)
    if present:
        weight_sum = sum(weights[k] for k in present)
        overall = round(sum(v * weights[k] for k, v in present.items()) / weight_sum, 1)
    else:
        overall = None

    return {"overall": overall, "coverage": coverage, "categories": categories}
