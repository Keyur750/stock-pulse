"""
Pulls live price data via yfinance (free, unauthenticated Yahoo Finance
data) for market context, sector performance, and price/sentiment
divergence signals — the piece that turns "what people are saying" into
"what people are saying vs what's actually happening."
"""

import yfinance as yf

INDICES = [
    ("SPY", "S&P 500"),
    ("QQQ", "Nasdaq 100"),
    ("DIA", "Dow Jones"),
    ("^VIX", "VIX"),
]

SECTORS = [
    ("XLK", "Technology"),
    ("XLF", "Financials"),
    ("XLE", "Energy"),
    ("XLV", "Health Care"),
    ("XLI", "Industrials"),
    ("XLY", "Consumer Disc."),
    ("XLP", "Consumer Staples"),
    ("XLU", "Utilities"),
    ("XLB", "Materials"),
    ("XLRE", "Real Estate"),
    ("XLC", "Communication"),
]


def fetch_quotes(symbols: list) -> dict:
    """Fetch current price + day-over-day % change for each symbol.
    Symbols that fail to fetch (delisted, bad ticker, network hiccup) are
    simply omitted rather than breaking the whole run."""
    out = {}
    for sym in symbols:
        try:
            hist = yf.Ticker(sym).history(period="5d")
            if hist.empty or len(hist) < 2:
                continue
            closes = hist["Close"].dropna()
            last = float(closes.iloc[-1])
            prev = float(closes.iloc[-2])
            change_pct = round((last - prev) / prev * 100, 2) if prev else 0.0
            out[sym] = {"price": round(last, 2), "change_pct": change_pct}
        except Exception:
            continue
    return out


def fetch_named_quotes(pairs: list) -> list:
    """pairs: [(symbol, display_name), ...]. Returns list of dicts with
    symbol, name, price, change_pct — skipping any that failed to fetch."""
    symbols = [p[0] for p in pairs]
    quotes = fetch_quotes(symbols)
    result = []
    for sym, name in pairs:
        if sym in quotes:
            result.append({"symbol": sym, "name": name, **quotes[sym]})
    return result


def fetch_market_pulse():
    return fetch_named_quotes(INDICES)


def fetch_sector_heatmap():
    return fetch_named_quotes(SECTORS)
