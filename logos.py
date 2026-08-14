"""
Real company logos for the ticker avatars — fetched once per ticker and
committed to the repo as static files, not hotlinked from a third-party
service at page-view time.

This is a small, fixed set of flagship tickers (15 today), so caching is
cheap and removes a permanent runtime dependency: once a ticker's logo is
saved to docs/logos/, the site never needs the source again for it, even
if that source later changes its terms, rate-limits, or disappears
entirely. Only a newly-added ticker ever triggers a fresh fetch.

Source: financialmodelingprep's ticker-keyed image-stock endpoint —
verified against all 15 flagship tickers before adopting it: returns a
real, distinct company logo per ticker (not a generic placeholder) and an
honest 404 for a ticker it doesn't have one for. No API key required.
(Clearbit's old domain-keyed logo API, the more commonly cited option,
was checked first and no longer resolves at all — dropped.)

If no real logo can be fetched for a ticker, ensure_logo() returns False
and nothing is written — the frontend falls back to the existing colored-
letter avatar rather than showing a broken image or a fabricated stand-in.
"""

import os

import requests

LOGO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "logos")
LOGO_URL = "https://financialmodelingprep.com/image-stock/{ticker}.png"


def ensure_logo(ticker: str, timeout=8) -> bool:
    """True if a real logo file exists for `ticker` in docs/logos/ after
    this call — either it was already cached, or a real one was just
    fetched. False means no real logo is available; callers should fall
    back to the letter avatar, never fabricate a placeholder image."""
    os.makedirs(LOGO_DIR, exist_ok=True)
    path = os.path.join(LOGO_DIR, f"{ticker}.png")
    if os.path.exists(path):
        return True

    try:
        resp = requests.get(LOGO_URL.format(ticker=ticker), timeout=timeout)
        if resp.status_code != 200:
            return False
        if "image" not in resp.headers.get("Content-Type", ""):
            return False
        if len(resp.content) < 100:
            return False
    except Exception:
        return False

    with open(path, "wb") as f:
        f.write(resp.content)
    return True


def ensure_logos(tickers: list) -> dict:
    """Runs ensure_logo() for every ticker. Returns {ticker: bool} so the
    caller can log real coverage without failing the pipeline on a
    source hiccup for one ticker."""
    return {ticker: ensure_logo(ticker) for ticker in tickers}
