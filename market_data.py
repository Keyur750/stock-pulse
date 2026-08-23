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

# (symbol, display name, category) — powers the dashboard's "Markets" strip.
# category is a display grouping only, not used for weighting. ^NSEI
# (Nifty 50) chosen over ^BSESN (Sensex) as India's benchmark — more
# commonly quoted internationally. Every symbol here was verified live
# against yfinance before being added. Canadian entries (added
# 2026-08-23): ^GSPTSE is the S&P/TSX Composite, Canada's headline
# benchmark (TSX's own "S&P 500 equivalent"); USDCAD=X is the exchange
# rate, real context for a Canadian-market read that a bare index level
# doesn't give on its own. ^TX60 / ^SPTSX60 (S&P/TSX 60) and TSX Venture
# (^JX) were checked live and don't resolve on yfinance — not included
# rather than guessed at.
#
# Expanded 2026-08-23 (crypto/commodities/global indices): curated to
# genuinely well-known names, not every symbol yfinance happens to carry
# — every one verified live before being added. Crypto: SOL/XRP/BNB/DOGE
# are consistently the next-most-tracked names after BTC/ETH by market
# cap and retail attention; ADA and others left out to keep this a
# "famous names" strip, not a full market cap ranking. Commodities:
# Natural Gas and Copper are the standard "energy + industrial metal"
# pair alongside Gold/Silver/Oil (copper specifically tracked as a
# growth-cycle bellwether, "Dr. Copper"); Brent Crude is the other half
# of the oil benchmark most financial media actually quotes alongside
# WTI, hence renaming the existing entry to disambiguate. Global indices:
# FTSE 100 (UK), DAX (Germany), CAC 40 (France), and Hang Seng (Hong
# Kong) were the clearest real gaps — the prior four (Nikkei/Nifty/
# Shanghai/KOSPI) were all Asia-Pacific, with zero of Europe or Hong
# Kong's financial hub represented.
MACRO_INSTRUMENTS = [
    ("^GSPC", "S&P 500", "US"),
    ("^IXIC", "Nasdaq Composite", "US"),
    ("^DJI", "Dow Jones", "US"),
    ("^RUT", "Russell 2000", "US"),
    ("^VIX", "VIX", "US"),
    ("^GSPTSE", "S&P/TSX Composite", "Canada"),
    ("USDCAD=X", "USD/CAD", "Canada"),
    ("BTC-USD", "Bitcoin", "Crypto"),
    ("ETH-USD", "Ethereum", "Crypto"),
    ("SOL-USD", "Solana", "Crypto"),
    ("XRP-USD", "XRP", "Crypto"),
    ("BNB-USD", "BNB", "Crypto"),
    ("DOGE-USD", "Dogecoin", "Crypto"),
    ("GC=F", "Gold", "Commodities"),
    ("SI=F", "Silver", "Commodities"),
    ("CL=F", "Crude Oil (WTI)", "Commodities"),
    ("BZ=F", "Brent Crude", "Commodities"),
    ("NG=F", "Natural Gas", "Commodities"),
    ("HG=F", "Copper", "Commodities"),
    ("^N225", "Nikkei 225", "Global"),
    ("^NSEI", "Nifty 50", "Global"),
    ("000001.SS", "Shanghai Composite", "Global"),
    ("^KS11", "KOSPI", "Global"),
    ("^FTSE", "FTSE 100", "Global"),
    ("^GDAXI", "DAX", "Global"),
    ("^FCHI", "CAC 40", "Global"),
    ("^HSI", "Hang Seng", "Global"),
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
    hiccup) are simply omitted rather than breaking the whole run.

    `price` is rounded to 2 decimals for anything >= $1 (every flagship
    equity), but 6 decimals below that — added 2026-08-23 when adding
    Dogecoin to the Markets strip surfaced a real precision loss: a flat
    2dp rounding was truncating a sub-$1 price (~$0.091) to $0.09 before
    it ever reached the payload, silently erasing an 8%+ real daily move
    (change_pct itself was always computed from the unrounded floats, so
    only the displayed price/derived $-change were wrong, not the %)."""
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
            price_decimals = 2 if last >= 1 else 6
            history = [
                {"date": idx.strftime("%Y-%m-%d"), "close": round(float(v), 4)}
                for idx, v in closes.items()
            ]
            out[sym] = {"price": round(last, price_decimals), "change_pct": change_pct, "history": history}
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
