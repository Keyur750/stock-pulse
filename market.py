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

See MARKET_PILLAR_RESET.md for the full rebuild plan this file went
through (Phases 1-6 of 7 done as of the market_confidence() below) and
the research behind each phase.
"""

import statistics

import yfinance as yf


def _returns(closes: list) -> list:
    return [(closes[i] - closes[i - 1]) / closes[i - 1] * 100
            for i in range(1, len(closes)) if closes[i - 1]]


def _idiosyncratic_volatility(price_history: list, benchmark_history: list) -> float | None:
    """Market-model (single-index) regression of the ticker's daily
    returns against a benchmark's (S&P 500) over the same window,
    returning the stdev of the RESIDUALS -- the idiosyncratic volatility
    Ang/Hodrick/Xing/Zhang (2006) actually validated, not the ticker's
    total volatility (market.py's original daily_volatility_pct, which
    conflates market-wide moves with stock-specific ones -- see
    MARKET_PILLAR_RESET.md's Phase 4 section). Aligns the two series by
    DATE first (not by index), since a data gap in either series would
    otherwise silently misalign the returns. Returns None (not a
    fabricated value) whenever there's fewer than 10 overlapping trading
    days, or the benchmark itself shows zero variance (degenerate,
    should not happen in practice but guarded rather than dividing by
    zero)."""
    stock_by_date = {h["date"]: h["close"] for h in price_history if h.get("close")}
    bench_by_date = {h["date"]: h["close"] for h in benchmark_history if h.get("close")}
    common_dates = sorted(set(stock_by_date) & set(bench_by_date))
    if len(common_dates) < 11:
        return None

    stock_closes = [stock_by_date[d] for d in common_dates]
    bench_closes = [bench_by_date[d] for d in common_dates]
    stock_ret = _returns(stock_closes)
    bench_ret = _returns(bench_closes)
    if len(stock_ret) < 10 or len(stock_ret) != len(bench_ret):
        return None

    mkt_variance = statistics.variance(bench_ret)
    if not mkt_variance:
        return None
    local_beta = statistics.covariance(stock_ret, bench_ret) / mkt_variance
    local_alpha = statistics.mean(stock_ret) - local_beta * statistics.mean(bench_ret)
    residuals = [s - (local_alpha + local_beta * mk) for s, mk in zip(stock_ret, bench_ret)]
    return statistics.stdev(residuals)


def fetch_market_data(symbol: str, price_history: list | None = None,
                       benchmark_history: list | None = None) -> dict | None:
    """Raw market/momentum metrics for a ticker, or None if the data
    couldn't be fetched. `price_history` is the same {date, close} list
    already fetched by market_data.py — reused here for realized
    volatility instead of a second API call. `benchmark_history` (Market
    pillar Phase 4) is the same shape for the S&P 500 (^GSPC), fetched
    ONCE per run in main.py (not per ticker) and passed in — used to
    compute idiosyncratic volatility via a market-model regression; None
    or too-short a benchmark series just means that field comes back
    None, same graceful-degradation pattern as everything else here."""
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
    volatility_sample_size = 0
    if price_history and len(price_history) >= 10:
        closes = [h["close"] for h in price_history if h.get("close")]
        returns = _returns(closes)
        volatility_sample_size = len(returns)
        if len(returns) >= 5:
            daily_volatility = statistics.stdev(returns)

    idiosyncratic_volatility = None
    if price_history and benchmark_history:
        idiosyncratic_volatility = _idiosyncratic_volatility(price_history, benchmark_history)

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
        "idiosyncratic_volatility_pct": round(idiosyncratic_volatility, 2) if idiosyncratic_volatility is not None else None,
        "volatility_sample_size": volatility_sample_size,
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

# Market pillar Phase 2 -- short interest, per Asquith/Pathak/Ritter
# (2005): short-sale-constrained stocks (high short interest relative to
# float) show real, economically meaningful subsequent underperformance
# (215bps/month equal-weighted in their sample), twice as strong on news
# days -- see MARKET_PILLAR_RESET.md's research section. `short_percent_
# of_float` is the primary input, matching the literature's own framing
# (short interest AS A SHARE OF FLOAT is the constraint measure); `short_
# ratio` (days-to-cover) is a distinct construct -- squeeze-risk/liquidity,
# not the same "is this a real bearish constraint signal" question --
# confirmed live (2026-08-21) the two don't move together tightly on this
# watchlist (e.g. SBUX: 3.8% of float but short_ratio 5.1 vs MU: 2.7% of
# float but short_ratio 0.6 -- same ballpark % but very different ratios),
# so `short_ratio` deliberately stays supplementary raw context only, not
# folded into this score, to avoid conflating two different constructs.
# Breakpoints derived from a live run across the full 30-ticker watchlist
# (2026-08-21): min=0.01% (BA), p25=1.81%, median=2.74%, p75=9.91%,
# p90=13.46%, max=27.6% (NBIS) -- higher % scores lower, per the
# literature's underperformance finding.
_SHORT_INTEREST_PTS = [(0.5, 90), (2.0, 72), (4.0, 58), (7.0, 42), (10.0, 28), (15.0, 15), (25.0, 5)]

# Market pillar Phase 3 -- beta / low-beta tilt, per Frazzini & Pedersen's
# Betting Against Beta (2014): low-beta stocks earn higher risk-adjusted
# returns than high-beta ones, the opposite of naive CAPM intuition (BAB
# factor Sharpe ratio 0.78 over 1926-2012, ~2x the value factor's). The
# honest translation of a portfolio-level alpha finding into a single-
# stock 0-100 score is a MODEST tilt, not a dominant signal -- see this
# category's placeholder weight below and its deliberately gentler score
# range than the other categories. Centered on the true CAPM market
# beta of 1.0, not this watchlist's own median -- confirmed live
# (2026-08-21) this flagship, growth-tilted watchlist's own median beta
# is 1.27, well above 1.0, so most flagship names scoring modestly below
# neutral here is a real, honest reflection of this basket's own
# structural tilt, not a scoring bug -- same "document it, don't force a
# comparable distribution" precedent Wall Street's README already
# established for sell-side ratings clustering bullish. Real range
# confirmed live: min=0.17 (XOM), max=3.49 (CVNA).
_BETA_PTS = [(0.3, 70), (0.7, 60), (1.0, 50), (1.5, 40), (2.2, 28), (3.0, 18), (3.5, 12)]


def _score_short_interest(m: dict) -> float | None:
    pct = m.get("short_percent_of_float")
    if pct is None:
        return None
    score = _scale(pct * 100, _SHORT_INTEREST_PTS)
    return round(score, 1) if score is not None else None


def _score_beta(m: dict) -> float | None:
    beta = m.get("beta")
    if beta is None:
        return None
    score = _scale(beta, _BETA_PTS)
    return round(score, 1) if score is not None else None


def score_market(m: dict) -> dict:
    """Turns raw market metrics into 0-100 sub-scores plus a weighted
    overall. Missing data (e.g. no 52-week high on a fresh IPO, or no
    beta/short-interest coverage) drops that category rather than
    guessing — `coverage` reports how many categories had real data.

    Weights (Market pillar Phase 5 reweight, 2026-08-21) reflect how
    strongly each category's underlying research is actually evidenced,
    not the original hand-picked 0.40/0.35/0.25 (see MARKET_PILLAR_
    RESET.md's research section for the sources): `extension` (George &
    Hwang 2004 — the single most robust, internationally-replicated
    effect here, no long-term reversal) keeps the largest share;
    `trend` is trimmed to reflect the honest caveat that moving-average
    rules' historical edge has measurably decayed since 1986 even though
    the underlying momentum window is still real; `stability` (now
    idiosyncratic-volatility-aware, Ang/Hodrick/Xing/Zhang 2006 — a major,
    widely-replicated anomaly) keeps a substantial share; `short_interest`
    (Asquith/Pathak/Ritter 2005) and `beta_tilt` (Frazzini & Pedersen
    2014, deliberately the smallest weight — a portfolio-level alpha
    finding translated into a modest single-stock tilt, not a dominant
    signal) round out the total."""
    extension = _scale(m.get("pct_from_52w_high"), _EXTENSION_PTS)
    if extension is not None:
        extension = round(extension, 1)

    trend = _avg([_scale(m.get("pct_from_50d_avg"), _MA_50D_PTS),
                  _scale(m.get("pct_from_200d_avg"), _MA_200D_PTS)])

    # Market pillar Phase 4: score off idiosyncratic (market-model-
    # residual) volatility when it's computable -- matches what Ang/
    # Hodrick/Xing/Zhang (2006) actually validated, not the total-
    # volatility proxy this category started with. Same key name
    # (`stability`), same fallback-on-missing-data pattern
    # fundamentals.py's Altman Z''/legacy-blend fallback for
    # `balance_sheet` already established -- falls back to total
    # volatility whenever the benchmark regression isn't computable
    # (thin overlap, no benchmark series available), never a crash or a
    # fabricated value.
    vol_input = m.get("idiosyncratic_volatility_pct")
    if vol_input is None:
        vol_input = m.get("daily_volatility_pct")
    stability = _scale(vol_input, _VOLATILITY_PTS)
    if stability is not None:
        stability = round(stability, 1)

    short_interest = _score_short_interest(m)
    beta_tilt = _score_beta(m)

    categories = {
        "extension": extension, "trend": trend, "stability": stability,
        "short_interest": short_interest, "beta_tilt": beta_tilt,
    }
    weights = {"extension": 0.35, "trend": 0.20, "stability": 0.20,
               "short_interest": 0.15, "beta_tilt": 0.10}

    present = {k: v for k, v in categories.items() if v is not None}
    coverage = len(present)
    if present:
        weight_sum = sum(weights[k] for k in present)
        overall = round(sum(v * weights[k] for k, v in present.items()) / weight_sum, 1)
    else:
        overall = None

    return {"overall": overall, "coverage": coverage, "categories": categories}


# Market pillar Phase 5 -- market_confidence(). Same three-independent-
# signals-weighted-sum SHAPE as crowd_confidence()/wallstreet_confidence()
# (not a copy -- structurally different inputs), same goal: a real 0-100
# trust measure instead of a bare category-coverage count.
#
# Breakpoints/target below are derived from a live run across the full
# 30-ticker watchlist (2026-08-21, see MARKET_PILLAR_RESET.md's Phase 5
# section for the raw numbers), not guessed.
_DEFAULT_CONFIDENCE_TARGET_SAMPLE = 40.0


def market_confidence(m: dict | None, mscore: dict | None,
                       target_sample_size: float = _DEFAULT_CONFIDENCE_TARGET_SAMPLE) -> float | None:
    """Combines three independent, already-computed signals into one
    0-100 measure of how much to trust a ticker's Market score:

    1. Volatility sample size (35%) -- `volatility_sample_size` (the
       number of daily-return observations behind stability's score)
       scaled against `target_sample_size`, capped at 100. Rarely the
       binding constraint on an established flagship watchlist (most
       tickers have a near-full ~60-day window), but a real, protective
       signal for a genuinely thin case (a recent IPO, a data gap) --
       same role crowd_confidence()'s sample-size term plays even though
       it's usually not the limiting factor either.
    2. Extension/trend agreement (40%) -- the single most real,
       currently-discriminating signal found in this pillar's live data:
       how closely `extension` (distance from 52-week high) and `trend`
       (distance from moving averages) agree. Both are momentum-flavored
       reads computed from different windows -- when they agree, the
       pillar's own internal read is coherent; a sharp disagreement
       (e.g. a stock still far below its 52-week high but showing a
       strongly positive medium-term trend read) is real, meaningful
       tension worth trusting less at face value, not noise to average
       away. `None` (either category unavailable) scores a neutral 50,
       genuinely not assessable rather than a proven bad signal.
    3. Category completeness (25%) -- `mscore["coverage"]` against the
       full category count, same coverage-as-confidence-input shape
       Wall Street's own confidence function uses.

    Returns `None` only when `m`/`mscore` themselves are missing --
    nothing to be confident or unconfident about."""
    if not m or not mscore:
        return None

    sample = m.get("volatility_sample_size") or 0
    sample_term = min(100.0, 100.0 * sample / target_sample_size) if target_sample_size else 100.0

    cats = mscore.get("categories", {})
    extension, trend = cats.get("extension"), cats.get("trend")
    if extension is not None and trend is not None:
        agreement_term = max(0.0, 100.0 - abs(extension - trend))
    else:
        agreement_term = 50.0

    total_cats = len(cats) or 1
    completeness_term = 100.0 * (mscore.get("coverage") or 0) / total_cats

    return round(0.35 * sample_term + 0.40 * agreement_term + 0.25 * completeness_term, 1)


def market_confidence_label(score: float | None) -> str:
    if score is None:
        return "Unknown"
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"
