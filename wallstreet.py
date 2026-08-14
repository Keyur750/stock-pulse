"""
Wall Street pillar — "what are professionals expecting?" Free via
yfinance: analyst consensus rating, price targets, and a 3-month
recommendation-trend read (are analysts getting more or less bullish),
used as a free proxy for estimate revisions since yfinance doesn't
expose EPS/revenue revision history cleanly. Same shape as
fundamentals.py and market.py: raw metrics carried alongside the score.
"""

import yfinance as yf


def fetch_analyst_data(symbol: str) -> dict | None:
    """Raw analyst-consensus metrics for a ticker, or None if the data
    couldn't be fetched at all. Individual missing fields (a stock with
    no analyst coverage) come through as None, not a failure."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
    except Exception:
        return None
    if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
        return None

    def g(key):
        v = info.get(key)
        return v if isinstance(v, (int, float)) else None

    price = g("currentPrice") or g("regularMarketPrice")
    target_mean = g("targetMeanPrice")
    upside_pct = ((target_mean - price) / price * 100) if (price and target_mean) else None

    revision_delta = None
    try:
        rec = ticker.recommendations
        if rec is not None and not rec.empty and len(rec) >= 2:
            def bullish_ratio(row):
                total = row["strongBuy"] + row["buy"] + row["hold"] + row["sell"] + row["strongSell"]
                return (row["strongBuy"] + row["buy"]) / total * 100 if total else None

            latest = bullish_ratio(rec.iloc[0])
            oldest = bullish_ratio(rec.iloc[-1])
            if latest is not None and oldest is not None:
                # yfinance's recommendations table is pandas-backed, so
                # these are numpy float64 — cast to native float or they
                # break json.dumps() later in the pipeline.
                revision_delta = round(float(latest - oldest), 1)
    except Exception:
        pass

    return {
        "recommendation_mean": g("recommendationMean"),
        "recommendation_key": info.get("recommendationKey"),
        "num_analysts": g("numberOfAnalystOpinions"),
        "target_mean_price": target_mean,
        "target_high_price": g("targetHighPrice"),
        "target_low_price": g("targetLowPrice"),
        "upside_pct": round(upside_pct, 1) if upside_pct is not None else None,
        "revision_delta_pct": revision_delta,
    }


def _scale(value, points):
    """Same piecewise-linear interpolation as fundamentals.py/market.py."""
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


# recommendationMean: 1.0 = Strong Buy ... 5.0 = Strong Sell. Inverted
# so higher score = more bullish consensus, consistent with every other
# pillar in this project.
_RATING_PTS = [(1.0, 100), (2.0, 80), (3.0, 50), (4.0, 20), (5.0, 0)]
# Implied upside/downside to the mean analyst price target, in percent.
_TARGET_PTS = [(-30, 8), (-10, 28), (0, 50), (10, 65), (25, 82), (50, 95), (80, 100)]
# Change in "bullish share" of ratings over the recommendations table's
# available window (typically ~3 months), in percentage points.
_REVISION_PTS = [(-30, 10), (-10, 30), (0, 50), (10, 70), (30, 90)]


def score_wallstreet(w: dict) -> dict:
    """Turns raw analyst metrics into three 0-100 sub-scores plus a
    weighted overall. `coverage` reports how many of the 3 categories
    had real data — a stock with no analyst coverage returns overall
    None rather than a fabricated neutral score."""
    rating = _scale(w.get("recommendation_mean"), _RATING_PTS)
    if rating is not None:
        rating = round(rating, 1)

    price_target = _scale(w.get("upside_pct"), _TARGET_PTS)
    if price_target is not None:
        price_target = round(price_target, 1)

    revision_trend = _scale(w.get("revision_delta_pct"), _REVISION_PTS)
    if revision_trend is not None:
        revision_trend = round(revision_trend, 1)

    categories = {"rating": rating, "price_target": price_target, "revision_trend": revision_trend}
    weights = {"rating": 0.40, "price_target": 0.35, "revision_trend": 0.25}

    present = {k: v for k, v in categories.items() if v is not None}
    coverage = len(present)
    if present:
        weight_sum = sum(weights[k] for k in present)
        overall = round(sum(v * weights[k] for k, v in present.items()) / weight_sum, 1)
    else:
        overall = None

    return {"overall": overall, "coverage": coverage, "categories": categories}
