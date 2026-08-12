"""
Fundamentals pillar — free, structured financial data per ticker via
yfinance, turned into a transparent 0-100 score across five categories
(growth, profitability, cash flow, balance sheet, valuation).

This is deliberately a first-pass heuristic model, not a validated one:
the breakpoints below are reasonable judgment calls, not backtested
thresholds. The raw metrics are always carried alongside the score so
nothing is a black box — see PRODUCT.md's "show the work" principle.
"""

import yfinance as yf

FIELDS = [
    "marketCap", "revenueGrowth", "earningsGrowth", "grossMargins",
    "operatingMargins", "profitMargins", "returnOnEquity", "freeCashflow",
    "operatingCashflow", "totalRevenue", "totalDebt", "totalCash",
    "debtToEquity", "currentRatio", "trailingPE", "forwardPE",
    "priceToSalesTrailing12Months", "enterpriseToEbitda", "shortName", "sector",
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
    }


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


# Growth: reused for both revenue and earnings growth (fractions, e.g. 0.20 = 20%)
_GROWTH_PTS = [(-0.2, 10), (0, 35), (0.10, 55), (0.20, 75), (0.40, 92), (0.80, 100)]
_MARGIN_PTS = [(-0.2, 10), (0, 30), (0.05, 50), (0.15, 70), (0.25, 88), (0.40, 100)]
_ROE_PTS = [(-0.1, 10), (0, 30), (0.10, 55), (0.20, 75), (0.35, 92), (0.60, 100)]
_FCF_MARGIN_PTS = [(-0.1, 10), (0, 30), (0.05, 50), (0.15, 72), (0.25, 90), (0.40, 100)]
_DEBT_TO_EQUITY_PTS = [(0, 100), (50, 85), (100, 65), (200, 40), (400, 15), (800, 0)]
_CURRENT_RATIO_PTS = [(0, 10), (0.8, 35), (1.2, 60), (2.0, 85), (4.0, 100)]
_PE_PTS = [(5, 95), (12, 88), (18, 75), (25, 60), (35, 45), (50, 28), (80, 12), (150, 3)]
_PS_PTS = [(1, 92), (3, 78), (6, 60), (10, 42), (16, 25), (25, 10)]


def score_fundamentals(f: dict) -> dict:
    """Turns raw metrics into five 0-100 sub-scores plus a weighted
    overall score. Any sub-score with no underlying data is None rather
    than a guessed value — the overall score averages only what's present,
    and `coverage` reports how many of the 5 categories had real data."""
    growth = _avg([_scale(f.get("revenue_growth"), _GROWTH_PTS),
                   _scale(f.get("earnings_growth"), _GROWTH_PTS)])

    profitability = _avg([_scale(f.get("profit_margin"), _MARGIN_PTS),
                           _scale(f.get("operating_margin"), _MARGIN_PTS),
                           _scale(f.get("return_on_equity"), _ROE_PTS)])

    cash_flow = _scale(f.get("fcf_margin"), _FCF_MARGIN_PTS)
    if cash_flow is not None:
        cash_flow = round(cash_flow, 1)

    balance_sheet = _avg([_scale(f.get("debt_to_equity"), _DEBT_TO_EQUITY_PTS),
                           _scale(f.get("current_ratio"), _CURRENT_RATIO_PTS)])

    # Valuation: P/E is meaningless (or misleading) for unprofitable
    # companies — a negative or missing P/E falls back to price/sales.
    pe = f.get("forward_pe") or f.get("trailing_pe")
    if pe is not None and pe <= 0:
        pe = None
    valuation = _scale(pe, _PE_PTS) if pe is not None else _scale(f.get("price_to_sales"), _PS_PTS)
    if valuation is not None:
        valuation = round(valuation, 1)

    categories = {
        "growth": growth,
        "profitability": profitability,
        "cash_flow": cash_flow,
        "balance_sheet": balance_sheet,
        "valuation": valuation,
    }
    weights = {"growth": 0.25, "profitability": 0.20, "cash_flow": 0.20,
               "balance_sheet": 0.15, "valuation": 0.20}

    present = {k: v for k, v in categories.items() if v is not None}
    coverage = len(present)
    if present:
        weight_sum = sum(weights[k] for k in present)
        overall = round(sum(v * weights[k] for k, v in present.items()) / weight_sum, 1)
    else:
        overall = None

    return {"overall": overall, "coverage": coverage, "categories": categories}
