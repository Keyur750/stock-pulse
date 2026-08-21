"""
Wall Street pillar — "what are professionals expecting?" Free via
yfinance: analyst consensus rating, price targets, and a 3-month
recommendation-trend read (are analysts getting more or less bullish),
used as a free proxy for estimate revisions since yfinance doesn't
expose EPS/revenue revision history cleanly. Same shape as
fundamentals.py and market.py: raw metrics carried alongside the score.

See WALL_STREET_PILLAR_RESET.md for the full rebuild plan this file is
partway through (Phase 3 of 7 as of the rating-momentum scoring below)
and the research behind each phase.
"""

from datetime import datetime, timedelta, timezone

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

    # Wall Street pillar Phase 1: target_median_price sourced from the
    # dedicated analyst_price_targets endpoint (current/high/low/mean/
    # median), not `.info` -- `.info` only ever exposed mean/high/low.
    # Median matters on its own for Phase 4's dispersion work: a target
    # set skewed by one outlier analyst shows up as mean != median, which
    # a mean-only reading can't detect.
    target_median = None
    try:
        apt = ticker.analyst_price_targets
        if apt:
            v = apt.get("median")
            target_median = float(v) if isinstance(v, (int, float)) else None
    except Exception:
        pass

    return {
        "recommendation_mean": g("recommendationMean"),
        "recommendation_key": info.get("recommendationKey"),
        "num_analysts": g("numberOfAnalystOpinions"),
        "target_mean_price": target_mean,
        "target_median_price": target_median,
        "target_high_price": g("targetHighPrice"),
        "target_low_price": g("targetLowPrice"),
        "upside_pct": round(upside_pct, 1) if upside_pct is not None else None,
        "revision_delta_pct": revision_delta,
    }


# Wall Street pillar Phase 1 -- EPS estimate history. yfinance's period
# index is fixed across every ticker (confirmed live, full 30-ticker
# watchlist, 2026-08-20): "0q" = current quarter, "+1q" = next quarter,
# "0y" = current fiscal year, "+1y" = next fiscal year. Column names are
# inconsistently cased in the raw source (confirmed live: eps_revisions
# has "upLast7days" but "downLast7Days" -- lowercase/uppercase "D" is not
# a typo here, it's really what yfinance returns) -- mapped explicitly by
# name below rather than relied on case-insensitively, so a silent yfinance
# casing change can't misroute a column.
_EPS_TREND_COLS = {"current": "current", "7daysAgo": "7d_ago", "30daysAgo": "30d_ago",
                    "60daysAgo": "60d_ago", "90daysAgo": "90d_ago"}
_EPS_REVISIONS_COLS = {"upLast7days": "up_last_7d", "upLast30days": "up_last_30d",
                        "downLast7Days": "down_last_7d", "downLast30days": "down_last_30d"}


def _clean(value):
    """Same NaN-safety as fundamentals.py's _clean -- yfinance's
    DataFrame-backed fields come back as NaN for a genuinely missing
    period, not absent. Never fabricate 0 for a missing value."""
    if value is None:
        return None
    try:
        if isinstance(value, float) and value != value:  # NaN
            return None
    except Exception:
        pass
    return float(value)


def fetch_eps_estimate_history(symbol: str) -> dict | None:
    """Real EPS-estimate trend + revision-count history from yfinance's
    eps_trend/eps_revisions, one entry per period ("0q"/"+1q"/"0y"/"+1y").
    This is the raw material Wall Street pillar Phase 2 needs for a real
    Agreement/Magnitude revision signal (Zacks-inspired -- see
    WALL_STREET_PILLAR_RESET.md's research section) -- confirmed live,
    full watchlist: 30/30 tickers have real data here, including thin-
    coverage names (IONQ, NBIS) that later phases will need to treat
    carefully for other reasons, not this fetch. Returns None only if
    neither field has any data at all for this ticker (not expected in
    practice, per the live check, but never assumed)."""
    try:
        t = yf.Ticker(symbol)
        trend_df = t.eps_trend
        rev_df = t.eps_revisions
    except Exception:
        return None

    trend = {}
    if trend_df is not None and not trend_df.empty:
        for period, row in trend_df.iterrows():
            trend[period] = {out_key: _clean(row.get(src_key)) for src_key, out_key in _EPS_TREND_COLS.items()}

    revisions = {}
    if rev_df is not None and not rev_df.empty:
        for period, row in rev_df.iterrows():
            revisions[period] = {out_key: _clean(row.get(src_key)) for src_key, out_key in _EPS_REVISIONS_COLS.items()}

    if not trend and not revisions:
        return None
    return {"eps_trend": trend, "eps_revisions": revisions}


# Wall Street pillar Phase 1 -- individual dated rating-change history.
# Confirmed live (full watchlist, 2026-08-20): 30/30 tickers have real
# data here, but real depth varies hugely (29 rows for IONQ vs. 989 for
# AMZN) and -- the important finding -- RECENCY varies just as much:
# META, IONQ, BABA, and PTON all show ZERO actions in the trailing 90
# days despite having hundreds of historical rows between them. This is
# the "stale ratings" problem from the research section made concrete,
# not hypothetical -- exactly why Phase 3's recency-decay design and
# Phase 4's recency-based confidence term matter. A default lookback of
# ~13 months (comfortably wider than any recency window those later
# phases are likely to use) keeps today's fetch generous without
# unboundedly growing the payload for tickers with a decade-plus of rows.
_UPGRADES_DOWNGRADES_MAX_RECORDS = 60


def fetch_upgrades_downgrades(symbol: str, lookback_days: int = 395,
                               max_records: int = _UPGRADES_DOWNGRADES_MAX_RECORDS) -> list | None:
    """Real, dated, per-firm rating-change history from yfinance's
    upgrades_downgrades, newest first, capped to `lookback_days` and then
    `max_records`. yfinance uses 0.0 as its own sentinel for "no price
    target on this action" (confirmed live: an initiation's priorPriceTarget
    is 0.0, never a real price) -- normalized to None here rather than
    passed through as a fabricated $0 target. `from_grade` is empty string
    (not missing) for an initiation -- also normalized to None, since
    there genuinely was no prior grade to report. Returns None if the
    ticker has no rating-change history at all."""
    try:
        df = yf.Ticker(symbol).upgrades_downgrades
    except Exception:
        return None
    if df is None or df.empty:
        return None

    import pandas as pd
    cutoff = pd.Timestamp.now(tz=df.index.tz) - pd.Timedelta(days=lookback_days) if df.index.tz \
        else pd.Timestamp.now() - pd.Timedelta(days=lookback_days)
    recent = df[df.index >= cutoff].sort_index(ascending=False)

    def _price(v):
        v = _clean(v)
        return v if v not in (None, 0.0) else None

    records = []
    for date, row in recent.iterrows():
        from_grade = (row.get("FromGrade") or "").strip() or None
        records.append({
            "date": date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "firm": row.get("Firm"),
            "to_grade": row.get("ToGrade") or None,
            "from_grade": from_grade,
            "action": row.get("Action"),
            "price_target_action": row.get("priceTargetAction"),
            "current_price_target": _price(row.get("currentPriceTarget")),
            "prior_price_target": _price(row.get("priorPriceTarget")),
        })
        if len(records) >= max_records:
            break

    return records if records else None


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
# available window (typically ~3 months), in percentage points. Retired
# as a scored category in Wall Street pillar Phase 3 -- replaced by
# rating_momentum (below), a real dated-action signal built from
# upgrades_downgrades rather than this crude 2-point proxy. The metric
# itself (revision_delta_pct) stays in fetch_analyst_data()'s output and
# in the Gemini prompt as supplementary raw context -- it's not wrong
# data, just a much weaker version of what rating_momentum now covers.

# Wall Street pillar Phase 2 -- revision Agreement & Magnitude, the
# single most literature-backed addition in the rebuild plan (see
# WALL_STREET_PILLAR_RESET.md's research section: earnings-estimate
# revisions are the most emphasized driver of subsequent price moves in
# the sell-side-signal literature, and this is the entire premise of the
# Zacks Rank's Agreement/Magnitude factors).
#
# Agreement: net ratio of analysts revising EPS estimates up vs. down
# over the trailing 30 days -- (up-down)/(up+down), naturally bounded
# [-1, +1]. Uses the 30-day window only, not a 7d/30d blend: confirmed
# live (2026-08-20) that yfinance's upLast7days/upLast30days are
# cumulative (30d always >= 7d for the same period), so summing both
# would double-count the most recent week's activity. The 7-day figures
# stay in the payload (Phase 1) for Phase 4's recency/freshness work
# instead. Breakpoints centered on 0.0=50 (an even split is genuinely
# neutral, not derived from today's sample's own median, which happened
# to skew positive -- same principled-zero-point discipline as every
# other centered scale in this codebase, e.g. market.py's _MA_50D_PTS).
_REVISION_AGREEMENT_PTS = [(-1.0, 5), (-0.6, 20), (-0.2, 38), (0.0, 50), (0.2, 62), (0.6, 80), (1.0, 95)]

# Magnitude: how much the EPS estimate itself moved over the trailing 30
# days, scaled by the ticker's OWN CURRENT PRICE, not by the prior
# estimate. Verified live (2026-08-20) that scaling by the prior
# estimate blows up for any company whose EPS estimate sits near zero --
# COIN's 0y magnitude came back as -45998.7%, IONQ's as -1643.4%, both
# because the 30-days-ago base was a few tenths of a cent -- the exact
# same near-zero-denominator failure fundamentals.py's PEG calculation
# already had to guard against (see its _peg_score docstring). Scaling
# by price instead is stable regardless of how small the EPS estimate
# is, and is arguably more decision-relevant anyway (a $0.50 estimate
# cut matters far more for a $10 stock than a $500 one) -- same
# price-relative framing wallstreet.py's own upside_pct already uses.
# Breakpoints derived from the real distribution across the full
# 30-ticker watchlist (30 periods x 2, checked live 2026-08-20): p5=
# -0.57%, median=0.00%, p95=+0.45%, one real outlier at -13.0% (COIN,
# a genuine large estimate cut, not a units bug) -- confirmed by direct
# inspection of the raw eps_trend values behind it, not assumed.
_REVISION_MAGNITUDE_PTS = [(-3.0, 5), (-1.0, 20), (-0.3, 35), (0.0, 50), (0.3, 65), (1.0, 80), (3.0, 95)]

# Periods scored: "0q" (current quarter, the most responsive read) and
# "0y" (current fiscal year, a steadier read less prone to single-quarter
# noise) -- both confirmed live to have 30/30 watchlist coverage in
# Phase 1. "+1q"/"+1y" (next-period estimates) are available in the same
# payload but not scored here -- a possible future refinement, not
# needed for this phase.
_REVISION_PERIODS = ("0q", "0y")


def _revision_agreement_ratio(rev_period: dict) -> float | None:
    up, down = rev_period.get("up_last_30d"), rev_period.get("down_last_30d")
    if up is None or down is None or (up + down) == 0:
        # Zero revisions in the window is a real, different state from a
        # 50/50 split (net ratio 0.0) -- "no analyst touched this
        # estimate in 30 days" is silence, not agreement, so it's None,
        # not a fabricated neutral.
        return None
    return (up - down) / (up + down)


def _score_revision_agreement(eps_revisions: dict | None) -> dict | None:
    """Zacks-style Agreement factor: what share of analysts revising an
    EPS estimate in the last 30 days are moving the same direction.
    Averages the "0q"/"+0y" periods' individually-scaled reads (same
    scale-then-average pattern as fundamentals.py's growth/profitability
    categories), not a raw average of the two ratios themselves. None if
    neither period has any revision activity in the window."""
    if not eps_revisions:
        return None
    ratios, scores = {}, []
    for period in _REVISION_PERIODS:
        ratio = _revision_agreement_ratio(eps_revisions.get(period) or {})
        ratios[period] = round(ratio, 3) if ratio is not None else None
        if ratio is not None:
            scores.append(_scale(ratio, _REVISION_AGREEMENT_PTS))
    if not scores:
        return None
    return {"score": round(sum(scores) / len(scores), 1), "net_ratios": ratios}


def _score_revision_magnitude(eps_trend: dict | None, price: float | None) -> dict | None:
    """Zacks-style Magnitude factor: how much the EPS estimate itself
    moved over the last 30 days, scaled by price (see breakpoint-table
    docstring above for why). None if there's no usable price or no
    eps_trend data for either scored period."""
    if not eps_trend or not price:
        return None
    pct_changes, scores = {}, []
    for period in _REVISION_PERIODS:
        t = eps_trend.get(period) or {}
        current, ago30 = t.get("current"), t.get("30d_ago")
        if current is None or ago30 is None:
            pct_changes[period] = None
            continue
        pct = (current - ago30) / price * 100
        pct_changes[period] = round(pct, 3)
        scores.append(_scale(pct, _REVISION_MAGNITUDE_PTS))
    if not scores:
        return None
    return {"score": round(sum(scores) / len(scores), 1), "pct_of_price": pct_changes}


# Wall Street pillar Phase 3 -- rating momentum from individual dated
# actions (upgrades_downgrades), replacing revision_trend's crude 2-point
# proxy. yfinance's own `Action` field (up/down/main/reit/init) is the
# AUTHORITATIVE direction classification -- confirmed live (2026-08-20,
# 2090 real up/down actions across the full watchlist): cross-validating
# Action against the ordinal grade mapping below agreed 99.2% of the time
# (17 "mismatches", all but one explained by firms whose own internal
# scale has finer tiers within one of this table's 5 buckets, e.g.
# Outperform->Buy both map to +1 here but Action='up' since that firm's
# ladder still ranks Buy above Outperform -- not a mapping error, a real
# coarseness limit of sharing one ordinal scale across 178 firms). So
# direction comes from Action directly, never re-derived from grade
# comparison; the ordinal mapping is used only for the "boldness"
# (notch-jump-size) multiplier below.
#
# Confirmed live across the full watchlist: 34 distinct grade labels,
# no shared taxonomy across firms. Mapped to a 5-bucket ordinal scale;
# a few are real judgment calls (documented inline), same "flag it, don't
# hide it" discipline as Business pillar Phase 4's sector-industry
# mapping: "Reduce" is scored as mildly bearish (-1), some firms use it
# as a softer "Sell" and others as a harder "Hold" -- no universal
# convention exists; "Accumulate"/"Above Average" scored bullish (+1),
# used by several firms as a tier below "Buy" but still clearly positive;
# plain "Perform" (no qualifier) scored neutral (0), matching how firms
# that use it (e.g. Oppenheimer) intend it. An unmapped future label
# (one this exact watchlist hasn't produced yet) falls back to notch_jump
# = 1 (the baseline, no bold/herding adjustment) rather than a guess.
_GRADE_ORDINAL = {
    "Strong Buy": 2, "Conviction Buy": 2, "Top Pick": 2,
    "Buy": 1, "Overweight": 1, "Outperform": 1, "Outperformer": 1,
    "Accumulate": 1, "Above Average": 1, "Positive": 1,
    "Long-Term Buy": 1, "Market Outperform": 1, "Sector Outperform": 1,
    "Hold": 0, "Neutral": 0, "Equal-Weight": 0, "Equal-weight": 0,
    "Market Perform": 0, "Sector Perform": 0, "Peer Perform": 0,
    "In-Line": 0, "Average": 0, "Market Weight": 0, "Sector Weight": 0,
    "Mixed": 0, "Perform": 0,
    "Underweight": -1, "Underperform": -1, "Reduce": -1, "Negative": -1,
    "Market Underperform": -1, "Sector Underperform": -1,
    "Sell": -2, "Strong Sell": -2,
}

# A same-notch move (e.g. Buy->Hold) is the baseline, weight 1.0. Each
# additional notch of jump (e.g. Buy->Sell, a 3-notch move on this scale)
# adds weight, capped so one extreme single action can't dominate the
# whole momentum read outright -- same capping instinct as fundamentals
# .py's _dupont_leverage_discount. Concretely a real, checkable form of
# Clement & Tse's "bold vs. herding" finding (see research doc): this
# implements the "deviates from the analyst's OWN prior view" half of
# their definition (directly computable from FromGrade/ToGrade); the
# "AND deviates from the current consensus" half is NOT implemented here
# -- it needs point-in-time historical consensus reconstruction, a
# meaningfully bigger undertaking not attempted in this phase. Noted as
# a real, deliberate scope limit, not silently dropped.
_BOLDNESS_STEP = 0.3
_BOLDNESS_CAP = 2.0


def _action_signed_magnitude(action: str, from_grade: str | None, to_grade: str | None) -> float | None:
    """Signed contribution of one rating-change record, before recency
    decay. up/down use Action's own direction (never re-derived) with a
    boldness multiplier from the notch jump; init contributes a softer
    signal (0.5x-scaled by the initiating grade's ordinal position) since
    a new analyst starting coverage isn't a "change" in the Womack/
    revision sense, just new information; main/reit return None --
    a reiteration with no rating change carries no revision signal,
    consistent with this whole phase's premise that levels don't predict,
    changes do."""
    if action == "init":
        to_ord = _GRADE_ORDINAL.get(to_grade) if to_grade else None
        return None if to_ord is None else 0.5 * (to_ord / 2.0)
    if action in ("up", "down"):
        direction = 1.0 if action == "up" else -1.0
        from_ord = _GRADE_ORDINAL.get(from_grade) if from_grade else None
        to_ord = _GRADE_ORDINAL.get(to_grade) if to_grade else None
        notch_jump = abs(to_ord - from_ord) if (from_ord is not None and to_ord is not None) else 1
        boldness = min(_BOLDNESS_CAP, 1.0 + _BOLDNESS_STEP * max(0, notch_jump - 1))
        return direction * boldness
    return None


def _parse_grade_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


# Breakpoints derived from the real shrunk-momentum distribution across
# the full 30-ticker watchlist (checked live 2026-08-20, 60-day half-
# life / 270-day lookback / shrinkage_k=3.0): min=-0.52, p5=-0.07,
# median=+0.05, p95=+0.34, max=+0.41. Live example of the shrinkage
# actually doing real work: TEAM's one bold recent downgrade (raw -1.0,
# thin support, total decayed weight 0.23) shrank to -0.07 -- appropriately
# discounted; NKE's well-corroborated downgrade trend (raw -0.92, 12
# actions, total decayed weight 3.85) only shrank to -0.52 -- a real,
# broadly-supported signal keeps its strength. Centered on 0.0=50 (net
# zero momentum), not the sample's own median, same principled-zero-point
# discipline as every other centered scale in this codebase.
_RATING_MOMENTUM_PTS = [(-0.6, 5), (-0.3, 20), (-0.1, 38), (0.0, 50), (0.1, 62), (0.3, 80), (0.6, 95)]


def _score_rating_momentum(upgrades_downgrades: list | None, half_life_days: float = 60.0,
                            lookback_days: int = 270, shrinkage_k: float = 3.0,
                            now=None) -> dict | None:
    """Recency-decayed, boldness-weighted net upgrade/downgrade balance
    from real dated actions -- same exponential-decay-plus-shrinkage
    SHAPE as sentiment.py's score_messages() (half-life decay composed
    with a Bayesian shrinkage-toward-neutral for thin samples), applied
    to a structurally different input (discrete dated rating-change
    events, not scored chat messages), not a copy-paste. Returns None if
    there's no rating-change (not reiteration-only) activity within the
    lookback window -- silence is a real, different state from a
    genuinely net-zero momentum, same discipline _score_revision_agreement
    already established for this pillar."""
    if not upgrades_downgrades:
        return None
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)

    weighted_sum, total_weight, included = 0.0, 0.0, 0
    for rec in upgrades_downgrades:
        date = _parse_grade_date(rec.get("date"))
        if date is None or date < cutoff:
            continue
        magnitude = _action_signed_magnitude(rec.get("action"), rec.get("from_grade"), rec.get("to_grade"))
        if magnitude is None:
            continue
        age_days = max(0.0, (now - date).total_seconds() / 86400)
        decay = 0.5 ** (age_days / half_life_days)
        weighted_sum += magnitude * decay
        total_weight += decay
        included += 1

    if total_weight == 0:
        return None
    raw = weighted_sum / total_weight
    shrunk = raw * (total_weight / (total_weight + shrinkage_k))
    return {
        "score": round(_scale(shrunk, _RATING_MOMENTUM_PTS), 1),
        "net_momentum_raw": round(raw, 3),
        "net_momentum_shrunk": round(shrunk, 3),
        "included_actions": included,
    }


def score_wallstreet(w: dict, eps_estimates: dict | None = None, price: float | None = None,
                      upgrades_downgrades: list | None = None, momentum_half_life_days: float = 60.0,
                      momentum_lookback_days: int = 270, momentum_shrinkage_k: float = 3.0) -> dict:
    """Turns raw analyst metrics into 0-100 sub-scores plus a weighted
    overall. `coverage` reports how many categories had real data — a
    stock with no analyst coverage returns overall None rather than a
    fabricated neutral score.

    eps_estimates/price are optional (Wall Street pillar Phase 2) — when
    both are provided, adds `revision_agreement` and `revision_magnitude`.
    upgrades_downgrades is optional (Phase 3) — when provided, adds
    `rating_momentum`, which REPLACES the old `revision_trend` category
    (a real dated-action signal in place of a crude 2-point proxy — see
    WALL_STREET_PILLAR_RESET.md's Phase 3 section). Omitting all of these
    keeps the original three-category behavior exactly as it was —
    additive, not a breaking change to existing callers, same pattern
    fundamentals.py's score_fundamentals used for its own phased
    additions.

    Weights for the new categories are placeholders, not validated —
    same status the original three (and every fixed weight in this
    codebase's other pillars) started at. Wall Street pillar Phase 4 is
    where all five get checked against real outcomes together, not
    reweighted piecemeal here."""
    rating = _scale(w.get("recommendation_mean"), _RATING_PTS)
    if rating is not None:
        rating = round(rating, 1)

    price_target = _scale(w.get("upside_pct"), _TARGET_PTS)
    if price_target is not None:
        price_target = round(price_target, 1)

    agreement_result = _score_revision_agreement((eps_estimates or {}).get("eps_revisions"))
    magnitude_result = _score_revision_magnitude((eps_estimates or {}).get("eps_trend"), price)
    revision_agreement = agreement_result["score"] if agreement_result else None
    revision_magnitude = magnitude_result["score"] if magnitude_result else None

    momentum_result = _score_rating_momentum(
        upgrades_downgrades, half_life_days=momentum_half_life_days,
        lookback_days=momentum_lookback_days, shrinkage_k=momentum_shrinkage_k,
    )
    rating_momentum = momentum_result["score"] if momentum_result else None

    categories = {
        "rating": rating, "price_target": price_target,
        "revision_agreement": revision_agreement, "revision_magnitude": revision_magnitude,
        "rating_momentum": rating_momentum,
    }
    # Wall Street pillar Phase 4 reweighting -- the original 0.40/0.35/0.25
    # (rating/price_target/revision_trend) plus Phase 2's two 0.15
    # placeholders summed to 1.30, not 1.0: additive-not-breaking was the
    # right call at the time (see Phase 2/3 sections of
    # WALL_STREET_PILLAR_RESET.md), but it silently diluted rating's and
    # price_target's EFFECTIVE share (40%/35% of raw weight -> ~31%/27% of
    # the normalized total once revision_agreement/magnitude entered the
    # mix) as a side effect nobody deliberately chose. This reweighting
    # both fixes that (now sums to 1.0 exactly) and acts on the research
    # foundations doc's central finding: recommendation LEVEL carries
    # little independent predictive power (Womack 1996; Bradshaw's review
    # found no significant level-return relation once other drivers are
    # controlled for) while recommendation CHANGE is where the real signal
    # lives -- `rating` is demoted hardest (0.40 -> 0.15) and the three
    # change/revision-based categories (revision_agreement,
    # revision_magnitude, rating_momentum -- the Zacks-Agreement/Magnitude
    # and Clement&Tse-boldness-informed signals) now carry the majority of
    # the total weight (0.65 combined) instead of being minor add-ons.
    # `price_target` is trimmed (0.35 -> 0.20) but deliberately not
    # demoted as hard as `rating` or folded into the revision categories --
    # its own documented structural optimism bias (see research doc) is
    # Phase 5's job to actually treat, not something to guess an
    # adjustment for here without that dedicated work.
    weights = {"rating": 0.15, "price_target": 0.20,
               "revision_agreement": 0.20, "revision_magnitude": 0.20, "rating_momentum": 0.25}

    present = {k: v for k, v in categories.items() if v is not None}
    coverage = len(present)
    if present:
        weight_sum = sum(weights[k] for k in present)
        overall = round(sum(v * weights[k] for k, v in present.items()) / weight_sum, 1)
    else:
        overall = None

    return {
        "overall": overall, "coverage": coverage, "categories": categories,
        "revision_agreement_detail": agreement_result,
        "revision_magnitude_detail": magnitude_result,
        "rating_momentum_detail": momentum_result,
    }


# Wall Street pillar Phase 4 -- wallstreet_confidence(). Same three-
# independent-signals-weighted-sum SHAPE as sentiment.py's
# crowd_confidence() (not a copy -- structurally different inputs), and
# the same underlying goal: replace a bare 0-3 category-coverage count
# with a real 0-100 measure of how much to trust THIS ticker's Wall
# Street score, not just whether data exists at all.
#
# Breakpoints below are derived from a live run across the full 30-ticker
# watchlist (2026-08-21, see WALL_STREET_PILLAR_RESET.md's Phase 4
# section for the raw numbers), not guessed:
#   num_analysts:            min=13, p25=23.8, median=31.5, p90=50.7, max=60
#   dispersion (high-low)/mean: min=0.215, p25=0.557, median=0.804,
#                                p75=1.208, p90=1.527, max=2.000
#   days since most recent action: min=0.4, median=11.6, p75=18.3,
#                                p90=29.0, max=104.2 (28/30 tickers had at
#                                least one action in the 395-day fetch
#                                window; 2/30 -- META, IONQ -- had none)

# Target analyst count for full coverage-breadth confidence. 25 sits just
# above the real watchlist's p25 (23.8) -- roughly a quarter of the
# watchlist doesn't yet reach full confidence on this term alone, rather
# than a threshold picked to flatter the data -- and lines up with the
# commonly-cited equity-research heuristic that ~20+ analysts constitutes
# genuinely well-covered. Configurable via
# wallstreet_confidence_target_analysts in config.json, same tunable
# discipline as crowd_confidence_target_n.
_DEFAULT_CONFIDENCE_TARGET_ANALYSTS = 25.0

# Price-target dispersion -> confidence. Tight agreement across analysts
# makes a consensus target more trustworthy; a wide high/low spread makes
# it a fragile average (Palley/Steffen/Zhang framing -- see research
# doc). Breakpoints walk the real live percentiles above almost exactly:
# 0.2 (~min, BA's real 0.215) -> 95, 0.8 (~median, 0.804) -> 50, 1.2
# (~p75, 1.208) -> 30, 2.0 (real max, PTON) -> 5. None (missing high/low/
# mean) scores a neutral 50 -- genuinely not assessable, not a proven bad
# signal, same fallback crowd_confidence() uses for single-source
# agreement.
_DISPERSION_CONFIDENCE_PTS = [(0.2, 95), (0.4, 80), (0.6, 65), (0.8, 50),
                              (1.2, 30), (1.6, 15), (2.0, 5)]


def wallstreet_confidence(w: dict | None, upgrades_downgrades: list | None,
                           target_analysts: float = _DEFAULT_CONFIDENCE_TARGET_ANALYSTS,
                           recency_half_life_days: float = 60.0, now=None) -> float | None:
    """Combines three independent, already-fetched signals into one 0-100
    measure of how much to trust a ticker's Wall Street score:

    1. Coverage breadth (45% weight) -- num_analysts scaled against
       target_analysts, capped at 100. Most statistically foundational of
       the three (same reasoning crowd_confidence() gives sample size the
       largest share), so it carries the most weight.
    2. Price-target dispersion (30% weight) -- see breakpoint-table
       docstring above. Real and literature-backed, but narrower in scope
       than coverage breadth (it speaks mainly to price_target's own
       trustworthiness, not the whole pillar).
    3. Rating recency (25% weight) -- exponential decay on days since the
       most recent upgrades_downgrades action of ANY kind (matching Phase
       1's own precedent for what counts as "an action" -- see that
       phase's stale-ratings finding), using the SAME half-life as
       rating_momentum's own decay rather than a second, separately-
       guessed constant -- both represent the same underlying "how fast
       does an analyst action's relevance fade" idea. No actions at all
       in the fetch window scores 0, not a neutral 50 -- genuine silence
       is real, meaningful information (the same discipline
       _score_rating_momentum already established for this pillar), not
       an unknowable state like a missing price target is.

    Returns None only if `w` itself is missing (no analyst data fetched
    at all for this ticker) -- there's nothing to be confident or
    unconfident about."""
    if not w:
        return None

    num_analysts = w.get("num_analysts")
    coverage_term = min(100.0, 100.0 * num_analysts / target_analysts) if num_analysts else 0.0

    high, low, mean = w.get("target_high_price"), w.get("target_low_price"), w.get("target_mean_price")
    dispersion = ((high - low) / mean) if (high is not None and low is not None and mean) else None
    dispersion_term = _scale(dispersion, _DISPERSION_CONFIDENCE_PTS) if dispersion is not None else 50.0

    now = now or datetime.now(timezone.utc)
    dates = [d for d in (_parse_grade_date(rec.get("date")) for rec in (upgrades_downgrades or [])) if d is not None]
    if dates:
        days_since_last = max(0.0, (now - max(dates)).total_seconds() / 86400)
        recency_term = 100.0 * (0.5 ** (days_since_last / recency_half_life_days))
    else:
        recency_term = 0.0

    return round(0.45 * coverage_term + 0.30 * dispersion_term + 0.25 * recency_term, 1)


def wallstreet_confidence_label(score: float | None) -> str:
    if score is None:
        return "Unknown"
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"
