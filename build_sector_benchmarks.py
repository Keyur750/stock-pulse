"""
Business pillar Phase 1 (data foundation) -- NOT part of the daily
pipeline, run by hand, occasionally (Damodaran refreshes his data a few
times a year; this doesn't need to be live every day the way prices do).

Question this answers: what does a "normal" margin, ROE, P/E, growth
rate, and leverage ratio look like for THIS ticker's actual industry,
not some single global number applied to every sector alike? See the
Business pillar review: every serious framework found (S&P/MSCI sector-
relative z-scores, CFA peer-group valuation) scores fundamentals against
industry peers, never a fixed universal ruler -- and this codebase's own
30-ticker watchlist is too small to build stable percentiles from itself
(some industries only have one name on it).

Aswath Damodaran (NYU Stern) publishes free, regularly-updated industry-
level averages across ~94 industries -- exactly the real peer benchmarks
a practitioner would reach for, at $0. This script downloads five of his
datasets (margins, ROE, P/E & growth, leverage) and a hand-built mapping
from yfinance's `industry` field (much more granular than its `sector`
field -- e.g. "Semiconductors" or "Banks - Diversified" vs. just
"Technology" or "Financial Services") to Damodaran's industry names, and
writes the merged result to data/sector_benchmarks.json for
score_fundamentals() to read (Phase 4 -- not wired into scoring yet).

The industry_mapping below only covers industries actually seen on the
current watchlist (confirmed live, see PRODUCT.md-adjacent research
notes) -- a ticker whose industry isn't mapped yet falls back to
"Total Market (without financials)" rather than crashing or guessing.
A few mappings are real judgment calls, not exact matches (Damodaran's
94 buckets don't line up 1:1 with yfinance's ~150), noted inline.

Needs `xlrd` to read Damodaran's legacy .xls files -- not in
requirements.txt on purpose, same reasoning as validate_finbert.py's
torch/transformers: this is a standalone tool, not a daily-pipeline
dependency. `pip install xlrd` before running.

Usage: python build_sector_benchmarks.py
"""

import json
import os
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(ROOT, "data", "sector_benchmarks.json")

_BASE = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/"
_FILES = {
    "margin": "margin.xls",
    "roe": "roe.xls",
    "pedata": "pedata.xls",
    "dbtfund": "dbtfund.xls",
}

# Confirmed live (see fetch inspection): margin/pedata/dbtfund's real
# header row is index 8, roe's is index 7 -- Damodaran's sheets aren't
# laid out identically to each other, verified rather than assumed.
_HEADER_ROW = {"margin": 8, "roe": 7, "pedata": 7, "dbtfund": 7}

# yfinance's granular `industry` field (confirmed live across the full
# watchlist) -> the closest Damodaran industry name. Most are close to
# exact; a few are real judgment calls:
#  - Internet Content & Information -> Software (Internet): Damodaran has
#    no dedicated "social/ad-supported platform" bucket; Software
#    (Internet) is the closest fit for META/RDDT/NBIS/SNAP.
#  - Internet Retail -> Retail (General): no e-commerce-specific bucket.
#  - Credit Services -> Financial Svcs. (Non-bank & Insurance): SOFI/PYPL
#    are lenders/payments, not deposit-taking banks -- deliberately NOT
#    mapped to Bank (Money Center), which would misrepresent them the
#    same way scoring JPM on working-capital ratios would.
#  - Financial Data & Stock Exchanges -> Brokerage & Investment Banking:
#    closest fit for COIN (an exchange, not a lender).
#  - Healthcare Plans -> Healthcare Support Services: UNH is a managed-
#    care insurer; Damodaran's "Insurance (General)" skews P&C/life, this
#    is the closer read.
INDUSTRY_MAPPING = {
    "Internet Content & Information": "Software (Internet)",
    "Internet Retail": "Retail (General)",
    "Software - Application": "Software (System & Application)",
    "Semiconductors": "Semiconductor",
    "Credit Services": "Financial Svcs. (Non-bank & Insurance)",
    "Computer Hardware": "Computers/Peripherals",
    "Software - Infrastructure": "Software (System & Application)",
    "Aerospace & Defense": "Aerospace/Defense",
    "Footwear & Accessories": "Shoe",
    "Restaurants": "Restaurant/Dining",
    "Leisure": "Recreation",
    "Auto Manufacturers": "Auto & Truck",
    "Financial Data & Stock Exchanges": "Brokerage & Investment Banking",
    "Entertainment": "Entertainment",
    "Banks - Diversified": "Bank (Money Center)",
    "Oil & Gas Integrated": "Oil/Gas (Integrated)",
    "Healthcare Plans": "Healthcare Support Services",
    "Drug Manufacturers - General": "Drugs (Pharmaceutical)",
    "Auto & Truck Dealerships": "Retail (Automotive)",
    "Telecom Services": "Telecom. Services",
}

FALLBACK_INDUSTRY = "Total Market (without financials)"


def _download(name, filename):
    path = os.path.join(ROOT, "data", f"_damodaran_{filename}")
    req = urllib.request.Request(
        _BASE + filename,
        headers={"User-Agent": "Mozilla/5.0 (research; Undertow build_sector_benchmarks.py)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)
    return path


def _load(name, path):
    hdr = _HEADER_ROW[name]
    df = pd.read_excel(path, sheet_name="Industry Averages", header=None)
    header = list(df.iloc[hdr].values)
    data = df.iloc[hdr + 1:].copy()
    data.columns = header
    data = data[data["Industry Name"].notna()]
    data = data.set_index("Industry Name")
    return data


def build():
    frames = {}
    for name, filename in _FILES.items():
        path = _download(name, filename)
        frames[name] = _load(name, path)
        os.remove(path)  # raw .xls not committed, only the merged JSON

    margin, roe, pedata, dbtfund = frames["margin"], frames["roe"], frames["pedata"], frames["dbtfund"]

    industries = {}
    all_names = set(margin.index) | set(roe.index) | set(pedata.index) | set(dbtfund.index)
    for ind in sorted(all_names):
        if ind == "Total Market":
            continue

        def g(df, col):
            if ind not in df.index or col not in df.columns:
                return None
            v = df.loc[ind, col]
            return None if pd.isna(v) else float(v)

        industries[ind] = {
            "n_firms": g(margin, "Number of firms"),
            "gross_margin": g(margin, "Gross Margin"),
            "net_margin": g(margin, "Net Margin"),
            # "as measured in financial statements" -- closest match to
            # yfinance's as-reported operatingMargins, not Damodaran's
            # own pre-tax/pre-SBC adjusted variant.
            "operating_margin": g(margin, "Pre-tax Unadjusted Operating Margin"),
            "roe": g(roe, "ROE (unadjusted)"),
            "trailing_pe": g(pedata, "Trailing PE"),
            "forward_pe": g(pedata, "Forward PE"),
            # 5-year forward analyst estimate -- a different time horizon
            # than yfinance's trailing/quarterly revenue_growth and
            # earnings_growth, but the best available free industry-level
            # growth benchmark; noted, not hidden, for whoever wires this
            # into Phase 4/5 scoring.
            "expected_growth_5yr": g(pedata, "Expected growth - next 5 years"),
            # Damodaran's Market D/E is a plain ratio (0.28 = 28%);
            # yfinance's debtToEquity is already in percentage-point
            # units (confirmed live: BA=790.875, matching its known
            # distressed leverage) -- multiplied by 100 here so the two
            # are on the same scale before any comparison in Phase 4.
            "debt_to_equity_pct": (lambda v: v * 100 if v is not None else None)(g(dbtfund, "Market D/E (unadjusted)")),
        }

    out = {
        "as_of": "2026-01-05",
        "source": "Aswath Damodaran, NYU Stern (https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html)",
        "note": "Free, publicly published industry-average data -- used as sector-relative benchmarks for Phase 4 of the Business pillar rebuild, not yet wired into score_fundamentals().",
        "fallback_industry": FALLBACK_INDUSTRY,
        "industry_mapping": INDUSTRY_MAPPING,
        "industries": industries,
    }

    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    unmapped = [v for v in INDUSTRY_MAPPING.values() if v not in industries]
    print(f"Wrote {len(industries)} industries to {OUT_PATH}")
    print(f"Watchlist industry mappings: {len(INDUSTRY_MAPPING)}, unmapped targets: {unmapped or 'none'}")


if __name__ == "__main__":
    build()
