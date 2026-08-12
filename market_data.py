"""
Pulls live price data via yfinance (free, unauthenticated Yahoo Finance
data) for market context, sector performance, and price/sentiment
divergence signals — the piece that turns "what people are saying" into
"what people are saying vs what's actually happening."
"""

import yfinance as yf

INDICES = [
    ("^GSPC", "S&P 500"),
    ("^NDX", "Nasdaq 100"),
    ("^DJI", "Dow Jones"),
    ("^VIX", "VIX"),
]

# (symbol, display name, approx. S&P 500 sector weight %) — weight drives
# treemap tile size on the dashboard, same convention as Finviz/TradingView
# sector maps. Ballpark figures, not live weights; only used for sizing.
SECTORS = [
    ("XLK", "Technology", 32.0),
    ("XLF", "Financials", 13.5),
    ("XLV", "Health Care", 10.5),
    ("XLY", "Consumer Disc.", 10.5),
    ("XLC", "Communication", 9.5),
    ("XLI", "Industrials", 8.5),
    ("XLP", "Consumer Staples", 5.5),
    ("XLE", "Energy", 3.5),
    ("XLU", "Utilities", 2.5),
    ("XLRE", "Real Estate", 2.0),
    ("XLB", "Materials", 2.0),
]


def fetch_quotes(symbols: list, period: str = "5d") -> dict:
    """Fetch current price + day-over-day % change for each symbol, plus
    its daily closes over `period` — the same call powers both the price
    ticker everywhere and the self-hosted charts (no separate round-trip
    needed). Symbols that fail to fetch (delisted, bad ticker, network
    hiccup) are simply omitted rather than breaking the whole run."""
    out = {}
    for sym in symbols:
        try:
            hist = yf.Ticker(sym).history(period=period)
            if hist.empty or len(hist) < 2:
                continue
            closes = hist["Close"].dropna()
            last = float(closes.iloc[-1])
            prev = float(closes.iloc[-2])
            change_pct = round((last - prev) / prev * 100, 2) if prev else 0.0
            history = [
                {"date": idx.strftime("%Y-%m-%d"), "close": round(float(v), 4)}
                for idx, v in closes.items()
            ]
            out[sym] = {"price": round(last, 2), "change_pct": change_pct, "history": history}
        except Exception:
            continue
    return out


def fetch_named_quotes(pairs: list, period: str = "5d") -> list:
    """pairs: [(symbol, display_name)] or [(symbol, display_name, weight)].
    Returns list of dicts with symbol, name, price, change_pct (+ weight
    when given) — skipping any that failed to fetch. Deliberately drops
    the history array (indices/sectors don't chart) so this stays light."""
    symbols = [p[0] for p in pairs]
    quotes = fetch_quotes(symbols, period=period)
    result = []
    for pair in pairs:
        sym, name = pair[0], pair[1]
        if sym in quotes:
            q = quotes[sym]
            row = {"symbol": sym, "name": name, "price": q["price"], "change_pct": q["change_pct"]}
            if len(pair) > 2:
                row["weight"] = pair[2]
            result.append(row)
    return result


def fetch_market_pulse():
    return fetch_named_quotes(INDICES)


def fetch_sector_heatmap():
    return fetch_named_quotes(SECTORS)
