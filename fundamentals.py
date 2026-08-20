"""
Fundamentals pillar — free, structured financial data per ticker via
yfinance, turned into a transparent 0-100 score across seven categories
(growth, profitability, cash flow, balance sheet, valuation, trend,
earnings quality).

This is deliberately a first-pass heuristic model, not a validated one:
the breakpoints below are reasonable judgment calls, not backtested
thresholds. The raw metrics are always carried alongside the score so
nothing is a black box — see PRODUCT.md's "show the work" principle.

See FULL_FUNDAMENTAL_RESET.md for the full rebuild plan this file is
partway through (Phase 4 of 6 as of the sector-relative scoring below)
and the research behind each phase.
"""

import json
import os

import yfinance as yf

# Business pillar Phase 4: Damodaran sector-average benchmarks built by
# build_sector_benchmarks.py (data/sector_benchmarks.json). Loaded once,
# lazily, and cached at module level -- read a few times per run, never
# refreshed mid-run, no reason to hit disk per ticker. Missing/corrupt
# file degrades to {} rather than crashing the pipeline -- every scoring
# function below already falls back to the pre-Phase-4 fixed global
# breakpoint tables when no sector benchmark is available, so an empty
# cache here just means "no tickers get sector-relative treatment today,"
# never a broken run.
_SECTOR_BENCHMARKS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sector_benchmarks.json")
_sector_benchmarks_cache = None


def _load_sector_benchmarks():
    global _sector_benchmarks_cache
    if _sector_benchmarks_cache is None:
        try:
            with open(_SECTOR_BENCHMARKS_PATH, encoding="utf-8") as fh:
                _sector_benchmarks_cache = json.load(fh)
        except (OSError, json.JSONDecodeError):
            _sector_benchmarks_cache = {}
    return _sector_benchmarks_cache


def _industry_benchmark(industry):
    """Maps a ticker's yfinance `industry` field (e.g. "Semiconductors")
    to its Damodaran industry-average stats via the mapping baked into
    sector_benchmarks.json itself (see build_sector_benchmarks.py).
    Unmapped/unknown industries fall back to "Total Market (without
    financials)", same as the build script -- returns None only if the
    benchmarks file itself couldn't be loaded, which every caller already
    treats as "no sector data today," not an error."""
    data = _load_sector_benchmarks()
    industries = data.get("industries")
    if not industries:
        return None
    mapping = data.get("industry_mapping", {})
    fallback = data.get("fallback_industry", "Total Market (without financials)")
    damodaran_name = mapping.get(industry, fallback) if industry else fallback
    return industries.get(damodaran_name)

FIELDS = [
    "marketCap", "revenueGrowth", "earningsGrowth", "grossMargins",
    "operatingMargins", "profitMargins", "returnOnEquity", "freeCashflow",
    "operatingCashflow", "totalRevenue", "totalDebt", "totalCash",
    "debtToEquity", "currentRatio", "trailingPE", "forwardPE",
    "priceToSalesTrailing12Months", "enterpriseToEbitda", "trailingEps",
    "shortName", "sector",
]


def fetch_fundamentals(symbol: str) -> dict | None:
    """Returns raw fundamental metrics for a ticker, or None if the data
    couldn't be fetched at all (bad ticker, delisted, network hiccup).
    Individual missing fields (common for newly-public or unprofitable
    companies) come through as None rather than failing the whole ticker."""
    try:
        info = yf.Ticker(symbol).info
    except Exception:
        return None
    if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
        return None

    def g(key):
        v = info.get(key)
        return v if isinstance(v, (int, float)) else None

    fcf = g("freeCashflow")
    revenue = g("totalRevenue")

    return {
        "name": info.get("shortName") or symbol,
        "sector": info.get("sector"),
        # Granular field (e.g. "Semiconductors"), distinct from the
        # coarse `sector` above (e.g. "Technology") -- this is the field
        # build_sector_benchmarks.py's industry_mapping actually keys on
        # for Phase 4's sector-relative scoring (see _industry_benchmark
        # below). Wasn't fetched at all before Phase 4 -- confirmed the
        # gap by reading this file fresh before starting that work.
        "industry": info.get("industry"),
        "market_cap": g("marketCap"),
        "revenue_growth": g("revenueGrowth"),
        "earnings_growth": g("earningsGrowth"),
        "gross_margin": g("grossMargins"),
        "operating_margin": g("operatingMargins"),
        "profit_margin": g("profitMargins"),
        "return_on_equity": g("returnOnEquity"),
        "free_cashflow": fcf,
        "operating_cashflow": g("operatingCashflow"),
        "fcf_margin": (fcf / revenue) if (fcf is not None and revenue) else None,
        "total_debt": g("totalDebt"),
        "total_cash": g("totalCash"),
        "debt_to_equity": g("debtToEquity"),
        "current_ratio": g("currentRatio"),
        "trailing_pe": g("trailingPE"),
        "forward_pe": g("forwardPE"),
        "price_to_sales": g("priceToSalesTrailing12Months"),
        "ev_to_ebitda": g("enterpriseToEbitda"),
        "trailing_eps": g("trailingEps"),
    }


_QUARTERLY_PERIODS_KEPT = 8
_ANNUAL_PERIODS_KEPT = 5


def _clean(value):
    """yfinance's financial statements come back as a pandas Series --
    missing periods are NaN, not absent, and NaN != None (isnan() is the
    only reliable check). Never fabricate a 0 for a genuinely missing
    quarter/year; None means "not reported," a real and common state for
    the most recent quarter or a newly-public company's early history."""
    if value is None:
        return None
    try:
        if isinstance(value, float) and value != value:  # NaN
            return None
    except Exception:
        pass
    return float(value)


def _quarter_label(ts):
    q = (ts.month - 1) // 3 + 1
    return f"Q{q}'{ts.year % 100:02d}"


def fetch_financial_history(symbol: str) -> dict | None:
    """Real quarterly (up to 8) and annual (up to 5) Revenue / Diluted EPS
    / Net Income history from yfinance's income statement -- confirmed
    against live data for the full watchlist (2026-08-18): every ticker
    had at least 5 real quarters and 4 real years, ~0.4s/ticker. Returns
    oldest-to-newest (yfinance itself returns newest-first) so a chart
    can plot left-to-right without the caller re-sorting. A period with a
    missing field comes through as value: None -- rendered as a gap, not
    guessed. Returns None only if the ticker has no statement data at all
    (bad symbol, not yet covered)."""
    try:
        t = yf.Ticker(symbol)
        q_stmt = t.quarterly_income_stmt
        a_stmt = t.income_stmt
    except Exception:
        return None

    def _series(stmt, periods_kept, label_fn):
        if stmt is None or stmt.empty:
            return {"revenue": [], "eps": [], "net_income": [], "ebit": []}
        cols = list(stmt.columns)[:periods_kept]
        cols = list(reversed(cols))  # oldest -> newest
        out = {"revenue": [], "eps": [], "net_income": [], "ebit": []}
        row_map = {"revenue": "Total Revenue", "eps": "Diluted EPS", "net_income": "Net Income",
                   "ebit": "EBIT"}
        for key, row_name in row_map.items():
            if row_name not in stmt.index:
                out[key] = [{"period": label_fn(c), "value": None} for c in cols]
                continue
            row = stmt.loc[row_name]
            out[key] = [{"period": label_fn(c), "value": _clean(row.get(c))} for c in cols]
        return out

    quarterly = _series(q_stmt, _QUARTERLY_PERIODS_KEPT, _quarter_label)
    annual = _series(a_stmt, _ANNUAL_PERIODS_KEPT, lambda ts: str(ts.year))

    if not quarterly["revenue"] and not annual["revenue"]:
        return None
    return {"quarterly": quarterly, "annual": annual}


# Balance-sheet line items needed for Phase 4's Altman Z''-Score and
# leverage-aware ROE (DuPont). "Total Liabilities Net Minority Interest"
# isn't reported as its own row for every ticker (confirmed live: absent
# for NVDA, present for JPM/XOM) -- derived as total_assets - total_equity
# instead of relying on the row, which is present more consistently.
# "Working Capital" and EBIT (see fetch_financial_history's "ebit" key)
# are structurally absent for banks (confirmed live on JPM) -- that's a
# real fact about how banks report, not a fetch bug, and score_fundamentals
# must treat it as None, never a fabricated value, once Phase 4 uses it.
_BALANCE_SHEET_ROWS = {
    "total_assets": "Total Assets",
    "total_equity": "Total Equity Gross Minority Interest",
    "working_capital": "Working Capital",
    "retained_earnings": "Retained Earnings",
    "shares_outstanding": "Ordinary Shares Number",
}


def fetch_balance_sheet_history(symbol: str) -> dict | None:
    """Real quarterly (up to 8) and annual (up to 5) Total Assets / Total
    Equity / Working Capital / Retained Earnings / Shares Outstanding
    history from yfinance's balance sheet -- same oldest-to-newest shape
    and same None-for-missing-period discipline as fetch_financial_history.
    total_liabilities is derived (total_assets - total_equity) rather than
    read as its own row, since that row isn't consistently present across
    tickers (confirmed live). Returns None only if the ticker has no
    balance sheet data at all."""
    try:
        t = yf.Ticker(symbol)
        q_stmt = t.quarterly_balance_sheet
        a_stmt = t.balance_sheet
    except Exception:
        return None

    def _series(stmt, periods_kept, label_fn):
        if stmt is None or stmt.empty:
            out = {k: [] for k in _BALANCE_SHEET_ROWS}
            out["total_liabilities"] = []
            return out
        cols = list(stmt.columns)[:periods_kept]
        cols = list(reversed(cols))  # oldest -> newest
        out = {}
        for key, row_name in _BALANCE_SHEET_ROWS.items():
            if row_name not in stmt.index:
                out[key] = [{"period": label_fn(c), "value": None} for c in cols]
                continue
            row = stmt.loc[row_name]
            out[key] = [{"period": label_fn(c), "value": _clean(row.get(c))} for c in cols]

        assets_by_period = {p["period"]: p["value"] for p in out["total_assets"]}
        equity_by_period = {p["period"]: p["value"] for p in out["total_equity"]}
        out["total_liabilities"] = [
            {
                "period": label_fn(c),
                "value": (assets_by_period[label_fn(c)] - equity_by_period[label_fn(c)])
                if (assets_by_period.get(label_fn(c)) is not None and equity_by_period.get(label_fn(c)) is not None)
                else None,
            }
            for c in cols
        ]
        return out

    quarterly = _series(q_stmt, _QUARTERLY_PERIODS_KEPT, _quarter_label)
    annual = _series(a_stmt, _ANNUAL_PERIODS_KEPT, lambda ts: str(ts.year))

    if not quarterly["total_assets"] and not annual["total_assets"]:
        return None
    return {"quarterly": quarterly, "annual": annual}


# Business pillar Phase 3 (earnings quality). "Operating Cash Flow" is
# confirmed live to be reported uniformly -- including for JPM, unlike
# the balance sheet's Working Capital/EBIT rows (Phase 1/2 finding: banks
# don't report a Current Assets/Liabilities split). A cash flow statement
# isn't structured around that split, so this one's real coverage should
# be better than the trend category's liquidity_trend signal.
def fetch_cashflow_history(symbol: str) -> dict | None:
    """Real quarterly (up to 8) and annual (up to 5) Operating Cash Flow
    history from yfinance's cash flow statement -- same oldest-to-newest,
    None-for-missing-period shape as fetch_financial_history and
    fetch_balance_sheet_history. Fetched separately from
    fetch_fundamentals()'s operating_cashflow (a single TTM snapshot from
    `.info`) because Phase 3's accrual check needs a cash flow figure
    tied to the SAME fiscal year as net_income and total_assets --
    mixing a TTM snapshot with fiscal-year-end statement data would be
    comparing different periods, not a real year-over-year check."""
    try:
        t = yf.Ticker(symbol)
        q_stmt = t.quarterly_cashflow
        a_stmt = t.cashflow
    except Exception:
        return None

    def _series(stmt, periods_kept, label_fn):
        if stmt is None or stmt.empty:
            return {"operating_cashflow": []}
        cols = list(stmt.columns)[:periods_kept]
        cols = list(reversed(cols))
        if "Operating Cash Flow" not in stmt.index:
            return {"operating_cashflow": [{"period": label_fn(c), "value": None} for c in cols]}
        row = stmt.loc["Operating Cash Flow"]
        return {"operating_cashflow": [{"period": label_fn(c), "value": _clean(row.get(c))} for c in cols]}

    quarterly = _series(q_stmt, _QUARTERLY_PERIODS_KEPT, _quarter_label)
    annual = _series(a_stmt, _ANNUAL_PERIODS_KEPT, lambda ts: str(ts.year))

    if not quarterly["operating_cashflow"] and not annual["operating_cashflow"]:
        return None
    return {"quarterly": quarterly, "annual": annual}


def _scale(value, points):
    """Piecewise-linear interpolation over (x, score) breakpoints, x
    ascending. Clamps outside the given range. Works for both
    "higher is better" and "lower is better" metrics — just order the
    breakpoints by x and put the scores wherever they belong."""
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


def _latest_value(series):
    """Latest single value from an oldest-to-newest annual series (same
    shape as _yoy_pair's input), for same-year cross-statement checks
    (Altman Z'', DuPont leverage) that don't need a prior year to
    compare against. None if the series is empty or the latest period
    wasn't reported -- never fabricated."""
    if not series:
        return None
    return series[-1]["value"]


def _yoy_pair(series):
    """Latest and prior year's value from an oldest-to-newest annual
    series (fetch_financial_history/fetch_balance_sheet_history's shape).
    Positional (series[-1] vs series[-2]), not "last two non-None values"
    -- a real, adjacent fiscal-year comparison, never silently skipping
    over a gap year. Returns (None, None) if either year is missing."""
    if len(series) < 2:
        return None, None
    latest, prior = series[-1]["value"], series[-2]["value"]
    if latest is None or prior is None:
        return None, None
    return latest, prior


def _yoy_triple(series):
    """Same as _yoy_pair but the latest 3 years, for the acceleration
    signal (this year's growth rate vs. last year's growth rate)."""
    if len(series) < 3:
        return None, None, None
    a, b, c = series[-1]["value"], series[-2]["value"], series[-3]["value"]
    if a is None or b is None or c is None:
        return None, None, None
    return a, b, c


# Rounding/restatement noise in yfinance's reported figures can make two
# genuinely-flat years read as a fake "up" or "down" -- a signal only
# fires if the move clears this margin, not on literal >/< as Piotroski's
# original binary tests do.
_TREND_NOISE_FLOOR = 0.01


def _trend_up(latest, prior, floor=_TREND_NOISE_FLOOR):
    """100 if latest clears prior by more than the noise floor (as a
    fraction of prior's magnitude), else 0. None propagates -- a missing
    year is never scored as "no improvement.\""""
    if latest is None or prior is None:
        return None
    if prior == 0:
        return 100.0 if latest > 0 else 0.0
    return 100.0 if (latest - prior) / abs(prior) > floor else 0.0


def _score_trend(financial_history, balance_sheet_history):
    """Piotroski-inspired year-over-year DIRECTION signals -- financial
    strength is as much about whether things are getting better or worse
    as it is about the current level. Piotroski (2000) found high-F-Score
    value stocks beat low-F-Score ones by several points/year, and most
    of his 9 signals are YoY change, not static level -- exactly what the
    other five categories here don't capture (they only ever look at the
    most recent snapshot).

    This is Piotroski-INSPIRED, not a literal F-Score: his accrual signal
    (operating cash flow > net income) is deliberately NOT duplicated
    here -- that's its own dimension, reserved for Phase 3's earnings-
    quality work, kept visible on its own rather than folded in twice.

    Uses ANNUAL data only (fiscal-year comparisons) -- quarterly data is
    seasonal and noisier, and Piotroski's original design compares fiscal
    years, not quarters. Each signal is None, never a guessed 0 or 100,
    when the two years being compared aren't both real (see _yoy_pair) --
    same "never fabricate" discipline as every other score in this file.
    Working-capital-based liquidity_trend comes back None for banks
    (confirmed live: SOFI, JPM don't report working capital at all) --
    a real gap, not a failure to compute."""
    if not financial_history and not balance_sheet_history:
        return None

    fh = (financial_history or {}).get("annual", {})
    bh = (balance_sheet_history or {}).get("annual", {})

    revenue = fh.get("revenue", [])
    eps = fh.get("eps", [])
    net_income = fh.get("net_income", [])
    total_assets = bh.get("total_assets", [])
    total_liabilities = bh.get("total_liabilities", [])
    working_capital = bh.get("working_capital", [])
    shares = bh.get("shares_outstanding", [])
    retained_earnings = bh.get("retained_earnings", [])

    signals = {}

    rev_latest, rev_prior = _yoy_pair(revenue)
    signals["revenue_trend"] = _trend_up(rev_latest, rev_prior)

    rev_a, rev_b, rev_c = _yoy_triple(revenue)
    if rev_a is not None and rev_b not in (None, 0) and rev_c not in (None, 0):
        growth_now = (rev_a - rev_b) / abs(rev_b)
        growth_prior = (rev_b - rev_c) / abs(rev_c)
        signals["revenue_accel"] = 100.0 if growth_now > growth_prior + _TREND_NOISE_FLOOR else 0.0
    else:
        signals["revenue_accel"] = None

    eps_latest, eps_prior = _yoy_pair(eps)
    signals["eps_trend"] = _trend_up(eps_latest, eps_prior)

    ni_latest, ni_prior = _yoy_pair(net_income)
    if ni_latest is not None and ni_prior is not None and rev_latest not in (None, 0) and rev_prior not in (None, 0):
        margin_latest = ni_latest / rev_latest
        margin_prior = ni_prior / rev_prior
        signals["margin_trend"] = 100.0 if margin_latest > margin_prior + _TREND_NOISE_FLOOR else 0.0
    else:
        signals["margin_trend"] = None

    assets_latest, assets_prior = _yoy_pair(total_assets)
    liab_latest, liab_prior = _yoy_pair(total_liabilities)
    if assets_latest not in (None, 0) and assets_prior not in (None, 0) and liab_latest is not None and liab_prior is not None:
        lev_latest = liab_latest / assets_latest
        lev_prior = liab_prior / assets_prior
        signals["leverage_trend"] = 100.0 if lev_latest < lev_prior - _TREND_NOISE_FLOOR else 0.0
    else:
        signals["leverage_trend"] = None

    wc_latest, wc_prior = _yoy_pair(working_capital)
    if wc_latest is not None and wc_prior is not None and assets_latest not in (None, 0) and assets_prior not in (None, 0):
        liq_latest = wc_latest / assets_latest
        liq_prior = wc_prior / assets_prior
        signals["liquidity_trend"] = 100.0 if liq_latest > liq_prior + _TREND_NOISE_FLOOR else 0.0
    else:
        signals["liquidity_trend"] = None

    shares_latest, shares_prior = _yoy_pair(shares)
    if shares_latest is not None and shares_prior not in (None, 0):
        # 2% tolerance -- routine stock-comp issuance isn't "dilution" in
        # the Piotroski sense the way a follow-on offering is.
        signals["dilution_trend"] = 100.0 if shares_latest <= shares_prior * 1.02 else 0.0
    else:
        signals["dilution_trend"] = None

    re_latest, re_prior = _yoy_pair(retained_earnings)
    signals["retained_earnings_trend"] = _trend_up(re_latest, re_prior)

    present = [v for v in signals.values() if v is not None]
    score = round(sum(present) / len(present), 1) if present else None
    return {"score": score, "signals": signals, "coverage": len(present)}


# Sloan (1996) accrual ratio = (Net Income - Operating Cash Flow) /
# Total Assets -- companies where reported earnings run well ahead of
# actual cash generation subsequently underperform (Sloan's original
# 1962-2001 backtest: ~18%/yr compounded low-accrual vs. high-accrual,
# vs. 7.4%/yr for the S&P). Breakpoints below are NOT a guess -- they're
# the commonly-cited "Sloan Ratio" interpretation bands (checked live
# this session, not from training-data memory): -10% to +10% is the
# normal range most healthy mature businesses cluster in; beyond +/-25%
# is flagged as an unusually large accrual effect. Clamped at the low
# end rather than rewarding ever-more-negative accruals with an ever-
# higher score -- deeply negative accruals past -25% can themselves
# reflect one-time effects, not a cleaner signal the more extreme it gets.
_ACCRUAL_PTS = [(-0.25, 90), (-0.10, 85), (0.0, 75), (0.10, 60), (0.25, 30), (0.40, 5)]


def _score_earnings_quality(financial_history, cashflow_history, balance_sheet_history):
    """Sloan accrual check -- kept as its own visible category (not
    folded into `profitability` or `trend`), because it answers a
    different question than either: not "is profit growing" (growth) or
    "is profit improving YoY" (trend), but "is this year's REPORTED
    profit actually backed by cash." A company can pass every other
    category here and still be quietly propping up earnings with
    accruals -- this is the one signal built specifically to catch that.
    Uses the latest single fiscal year (not a YoY comparison like
    _score_trend) since the accrual ratio is already a same-year cross-
    statement check, not a trend in itself. None, not a guessed ratio,
    when net income, operating cash flow, or total assets for that year
    aren't all available together.

    Business pillar Phase 4 financial-sector carve-out: a bank's
    operating cash flow isn't comparable to a non-bank's under GAAP --
    loan growth counts as an operating outflow, which structurally skews
    the accrual ratio even when it happens to land in a plausible-
    looking range. Confirmed live in Phase 3: JPM's OCF was -$147.8B,
    and the Gemini analyst's resulting bearish-factor prose read the
    (technically in-range) accrual ratio as a genuine earnings-quality
    concern -- a real, specifically misleading read, not just an
    imprecise one. Detected the same way _score_balance_sheet detects
    it: no reported working capital this fiscal year is real evidence of
    bank/lender-style reporting (confirmed live: only SOFI and JPM lack
    it on the current watchlist), not a coincidence -- so this returns
    None rather than a technically-computed-but-misleading score. Data-
    driven, not a hardcoded ticker list, so it generalizes to any future
    watchlist addition with the same reporting structure."""
    if not financial_history or not cashflow_history or not balance_sheet_history:
        return None
    if _latest_value((balance_sheet_history or {}).get("annual", {}).get("working_capital", [])) is None:
        return None

    net_income = (financial_history or {}).get("annual", {}).get("net_income", [])
    ocf = (cashflow_history or {}).get("annual", {}).get("operating_cashflow", [])
    total_assets = (balance_sheet_history or {}).get("annual", {}).get("total_assets", [])

    if not net_income or not ocf or not total_assets:
        return None

    ni = net_income[-1]["value"]
    cfo = ocf[-1]["value"]
    assets = total_assets[-1]["value"]
    if ni is None or cfo is None or assets is None or assets == 0:
        return None

    accrual_ratio = (ni - cfo) / abs(assets)
    score = round(_scale(accrual_ratio, _ACCRUAL_PTS), 1)
    return {"score": score, "accrual_ratio": round(accrual_ratio, 4), "net_income": ni, "operating_cashflow": cfo}


# Growth: reused for both revenue and earnings growth (fractions, e.g. 0.20 = 20%)
# These remain the FALLBACK tables (Phase 4): still used whenever a
# ticker's industry can't be sector-benchmarked -- unmapped industry,
# missing sector_benchmarks.json, or that specific metric absent from
# Damodaran's data for that industry. Never removed, never the primary
# path when a real peer benchmark is available.
_GROWTH_PTS = [(-0.2, 10), (0, 35), (0.10, 55), (0.20, 75), (0.40, 92), (0.80, 100)]
_MARGIN_PTS = [(-0.2, 10), (0, 30), (0.05, 50), (0.15, 70), (0.25, 88), (0.40, 100)]
_ROE_PTS = [(-0.1, 10), (0, 30), (0.10, 55), (0.20, 75), (0.35, 92), (0.60, 100)]
_FCF_MARGIN_PTS = [(-0.1, 10), (0, 30), (0.05, 50), (0.15, 72), (0.25, 90), (0.40, 100)]
_DEBT_TO_EQUITY_PTS = [(0, 100), (50, 85), (100, 65), (200, 40), (400, 15), (800, 0)]
_CURRENT_RATIO_PTS = [(0, 10), (0.8, 35), (1.2, 60), (2.0, 85), (4.0, 100)]
_PE_PTS = [(5, 95), (12, 88), (18, 75), (25, 60), (35, 45), (50, 28), (80, 12), (150, 3)]
_PS_PTS = [(1, 92), (3, 78), (6, 60), (10, 42), (16, 25), (25, 10)]

# Business pillar Phase 4 -- sector-relative breakpoints. Growth/margin/
# ROE metrics score off the DIFFERENCE vs. the industry benchmark
# (percentage points above/below peers), not a ratio -- Damodaran's
# per-industry averages include values at or near zero (e.g. Advertising's
# net_margin is -0.3%), where a ratio blows up or flips sign for no real
# reason. A difference of 0 (exactly in line with peers) scores 50;
# the bands widen for growth since growth rates vary far more across the
# watchlist than margins do. Valuation is the one exception -- P/E is a
# strictly-positive multiple, so a ratio (ticker P/E ÷ industry P/E) is
# stable and is the natural "cheap/expensive vs. peers" framing.
_GROWTH_DIFF_PTS = [(-0.30, 8), (-0.15, 25), (-0.05, 40), (0.0, 50), (0.05, 62), (0.15, 78), (0.30, 92), (0.60, 100)]
_MARGIN_DIFF_PTS = [(-0.25, 5), (-0.12, 22), (-0.04, 38), (0.0, 50), (0.04, 62), (0.12, 78), (0.25, 92), (0.40, 100)]
_ROE_DIFF_PTS = [(-0.25, 5), (-0.12, 22), (-0.04, 38), (0.0, 50), (0.04, 62), (0.15, 78), (0.30, 92), (0.50, 100)]
_PE_RATIO_PTS = [(0.3, 95), (0.6, 82), (0.85, 68), (1.0, 55), (1.2, 40), (1.5, 25), (2.0, 12), (3.5, 3)]

# Altman Z''-Score (Altman, 1968; non-manufacturer variant -- drops the
# sales/assets turnover term Z-Score uses, since that's incomparable
# across non-manufacturing industries, per FULL_FUNDAMENTAL_RESET.md's
# research section). Zones checked live this session against the
# commonly-cited interpretation: >2.6 safe, 1.1-2.6 grey, <1.1 distress.
_ALTMAN_ZPTS = [(-2.0, 5), (0.0, 20), (1.1, 40), (2.6, 75), (4.0, 88), (8.0, 100)]


def _relative_or_absolute(value, benchmark, diff_pts, fallback_pts):
    """Sector-relative score (value minus its industry benchmark, mapped
    through breakpoints centered on 0 = "in line with peers") when a
    real benchmark number is available for that specific metric; falls
    back to the original fixed global breakpoint table otherwise --
    same "never fabricate, degrade gracefully" discipline as every other
    missing-data case in this file. `benchmark` is None both when the
    ticker's industry has no sector_benchmarks.json entry at all and
    when the industry entry exists but doesn't carry that particular
    stat -- either way, the fallback is correct and safe."""
    if value is None:
        return None
    if benchmark is None:
        return _scale(value, fallback_pts)
    return _scale(value - benchmark, diff_pts)


def _relative_pe(pe, industry_pe, fallback_pts):
    """Same fallback discipline as _relative_or_absolute, but ratio-based
    (see the breakpoint tables' docstring above for why P/E uses a ratio
    while margins/ROE/growth use a difference)."""
    if pe is None:
        return None
    if industry_pe is None or industry_pe <= 0:
        return _scale(pe, fallback_pts)
    return _scale(pe / industry_pe, _PE_RATIO_PTS)


def _dupont_leverage_discount(roe_score, ticker_de_ratio, industry_de_pct):
    """DuPont decomposition (ROE = Net Margin × Asset Turnover × Equity
    Multiplier) in spirit, not literally recomputed -- rather than
    reconstruct ROE from its three components (which would just
    reproduce yfinance's own reported ROE, modulo rounding, and add
    nothing), this discounts the already-computed ROE sub-score when the
    company carries meaningfully more leverage (Total Liabilities ÷
    Total Equity) than its industry peers. That's the concrete, checkable
    form of "ROE inflated purely by debt gets discounted" from the
    Business pillar research: two companies with identical ROE are not
    equally strong if one gets there with a much bigger equity
    multiplier. Deliberately asymmetric -- only ever discounts a company
    MORE levered than peers, never rewards one that's LESS levered, per
    that same framing (a leverage bonus wasn't part of what was asked
    for or backtested). Discount is capped at 35 points so a single ratio
    never zeroes out an otherwise-strong score outright, and returns the
    score untouched (not None) whenever the leverage comparison itself
    isn't computable -- a missing peer-leverage figure is a reason to
    skip the discount, not to blank out the underlying ROE score."""
    if roe_score is None or ticker_de_ratio is None or not industry_de_pct or industry_de_pct <= 0:
        return roe_score
    industry_de_ratio = industry_de_pct / 100.0
    excess = ticker_de_ratio / industry_de_ratio
    if excess <= 1.0:
        return roe_score
    discount = min(35.0, (excess - 1.0) * 25.0)
    return max(0.0, round(roe_score - discount, 1))


def _score_balance_sheet(f, balance_sheet_history, financial_history):
    """Altman Z''-Score -- replaces the ad hoc debt-to-equity + current-
    ratio blend with a validated, weighted bankruptcy-risk composite:
    Working Capital, Retained Earnings, EBIT, Total Liabilities (all
    Phase 1 additions) and market cap (already fetched from `.info`).
    Z'' = 6.56×(WC/TA) + 3.26×(RE/TA) + 6.72×(EBIT/TA) + 1.05×(MVE/TL).

    Financial-sector carve-out: Working Capital and EBIT are structurally
    absent for deposit-taking banks (confirmed live, Phase 1: SOFI, JPM)
    -- a bank's balance sheet doesn't report a Current Assets/Liabilities
    split or a traditional EBIT line the way a non-financial company
    does, not a fetch bug (see fetch_balance_sheet_history's docstring).
    Rather than fabricate those two inputs or compute an invalid partial
    Z'', any ticker missing either one falls back to the pre-Phase-4
    debt-to-equity + current-ratio blend -- still a real, fetched signal,
    just a less sophisticated one. Detected by data availability, not a
    hardcoded ticker list, so it generalizes to any future watchlist
    addition with the same reporting structure."""
    bh = (balance_sheet_history or {}).get("annual", {})
    fh = (financial_history or {}).get("annual", {})
    working_capital = _latest_value(bh.get("working_capital", []))
    retained_earnings = _latest_value(bh.get("retained_earnings", []))
    total_assets = _latest_value(bh.get("total_assets", []))
    total_liabilities = _latest_value(bh.get("total_liabilities", []))
    ebit = _latest_value(fh.get("ebit", []))
    market_cap = f.get("market_cap")

    have_altman_inputs = (
        working_capital is not None and ebit is not None and retained_earnings is not None
        and total_assets not in (None, 0) and total_liabilities not in (None, 0)
        and market_cap is not None
    )
    if not have_altman_inputs:
        legacy = _avg([_scale(f.get("debt_to_equity"), _DEBT_TO_EQUITY_PTS),
                        _scale(f.get("current_ratio"), _CURRENT_RATIO_PTS)])
        return {"score": legacy, "method": "legacy_debt_current_ratio", "z_score": None}

    x1 = working_capital / total_assets
    x2 = retained_earnings / total_assets
    x3 = ebit / total_assets
    x4 = market_cap / total_liabilities
    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    score = round(_scale(z, _ALTMAN_ZPTS), 1)
    return {"score": score, "method": "altman_z_double_prime", "z_score": round(z, 2)}


def score_fundamentals(f: dict, financial_history: dict | None = None,
                        balance_sheet_history: dict | None = None,
                        cashflow_history: dict | None = None) -> dict:
    """Turns raw metrics into 0-100 sub-scores plus a weighted overall
    score. Any sub-score with no underlying data is None rather than a
    guessed value — the overall score averages only what's present, and
    `coverage` reports how many categories had real data.

    financial_history/balance_sheet_history are optional (Business pillar
    Phase 2) — when provided, adds a sixth "trend" category scoring
    year-over-year DIRECTION (see _score_trend) alongside the original
    five, which only ever look at the current snapshot. cashflow_history
    is optional too (Phase 3) — combined with the other two, adds a
    seventh "earnings_quality" category (see _score_earnings_quality,
    the Sloan accrual check). Omitting all three keeps the original
    five-category behavior exactly as it was — additive, not a breaking
    change to existing callers.

    Phase 4: growth, profitability (margins + DuPont-leverage-discounted
    ROE), and valuation are now scored sector-relative against Damodaran
    industry benchmarks (via `f["industry"]`, see _industry_benchmark)
    whenever a real benchmark is available, falling back to the original
    fixed global breakpoint tables otherwise. `balance_sheet` now uses
    the Altman Z''-Score in place of the ad hoc debt-to-equity/current-
    ratio blend, with the same legacy blend kept as a financial-sector
    fallback for tickers whose balance sheet doesn't report Working
    Capital/EBIT (see _score_balance_sheet). Category KEY NAMES are
    unchanged — only the math and detail payloads change — so this
    doesn't touch the radar chart's axis structure."""
    benchmark = _industry_benchmark(f.get("industry"))

    growth = _avg([
        _relative_or_absolute(f.get("revenue_growth"), (benchmark or {}).get("expected_growth_5yr"), _GROWTH_DIFF_PTS, _GROWTH_PTS),
        _relative_or_absolute(f.get("earnings_growth"), (benchmark or {}).get("expected_growth_5yr"), _GROWTH_DIFF_PTS, _GROWTH_PTS),
    ])

    # DuPont leverage discount needs the ticker's own Total
    # Liabilities/Total Equity -- latest annual, same "structural fact,
    # not a trend" framing as _score_earnings_quality's single-year read.
    bh_annual = (balance_sheet_history or {}).get("annual", {})
    ticker_equity = _latest_value(bh_annual.get("total_equity", []))
    ticker_liabilities = _latest_value(bh_annual.get("total_liabilities", []))
    ticker_de_ratio = (
        ticker_liabilities / ticker_equity
        if (ticker_liabilities is not None and ticker_equity not in (None, 0))
        else None
    )
    roe_score = _relative_or_absolute(f.get("return_on_equity"), (benchmark or {}).get("roe"), _ROE_DIFF_PTS, _ROE_PTS)
    roe_score = _dupont_leverage_discount(roe_score, ticker_de_ratio, (benchmark or {}).get("debt_to_equity_pct"))

    profitability = _avg([
        _relative_or_absolute(f.get("profit_margin"), (benchmark or {}).get("net_margin"), _MARGIN_DIFF_PTS, _MARGIN_PTS),
        _relative_or_absolute(f.get("operating_margin"), (benchmark or {}).get("operating_margin"), _MARGIN_DIFF_PTS, _MARGIN_PTS),
        roe_score,
    ])

    cash_flow = _scale(f.get("fcf_margin"), _FCF_MARGIN_PTS)
    if cash_flow is not None:
        cash_flow = round(cash_flow, 1)

    bs_result = _score_balance_sheet(f, balance_sheet_history, financial_history)
    balance_sheet = bs_result["score"] if bs_result else None

    # Valuation: P/E is meaningless (or misleading) for unprofitable
    # companies — a negative or missing P/E falls back to price/sales.
    # Sector-relative uses the matching horizon (forward vs. trailing) of
    # whichever P/E value is actually in use, not a mismatched pair.
    pe = f.get("forward_pe") or f.get("trailing_pe")
    pe_is_forward = bool(f.get("forward_pe"))
    if pe is not None and pe <= 0:
        pe = None
    if pe is not None:
        industry_pe = (benchmark or {}).get("forward_pe" if pe_is_forward else "trailing_pe")
        valuation = _relative_pe(pe, industry_pe, _PE_PTS)
    else:
        valuation = _scale(f.get("price_to_sales"), _PS_PTS)
    if valuation is not None:
        valuation = round(valuation, 1)

    trend_result = _score_trend(financial_history, balance_sheet_history)
    trend = trend_result["score"] if trend_result else None

    eq_result = _score_earnings_quality(financial_history, cashflow_history, balance_sheet_history)
    earnings_quality = eq_result["score"] if eq_result else None

    categories = {
        "growth": growth,
        "profitability": profitability,
        "cash_flow": cash_flow,
        "balance_sheet": balance_sheet,
        "valuation": valuation,
        "trend": trend,
        "earnings_quality": earnings_quality,
    }
    # trend's and earnings_quality's weights are placeholders, not
    # validated -- same status as the original five, which the file's
    # own history admits were "reasonable judgment calls, not backtested
    # thresholds." Phase 6 (Business pillar rebuild) is where all seven
    # get checked against real outcomes instead of left as more
    # unexamined guesses.
    weights = {"growth": 0.25, "profitability": 0.20, "cash_flow": 0.20,
               "balance_sheet": 0.15, "valuation": 0.20, "trend": 0.15,
               "earnings_quality": 0.15}

    present = {k: v for k, v in categories.items() if v is not None}
    coverage = len(present)
    if present:
        weight_sum = sum(weights[k] for k in present)
        overall = round(sum(v * weights[k] for k, v in present.items()) / weight_sum, 1)
    else:
        overall = None

    return {
        "overall": overall,
        "coverage": coverage,
        "categories": categories,
        "trend_signals": trend_result["signals"] if trend_result else None,
        "earnings_quality_detail": eq_result,
        "balance_sheet_detail": bs_result,
        "sector_benchmark_matched": benchmark is not None,
    }
