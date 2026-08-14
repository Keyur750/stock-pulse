"""
Material Events — SEC EDGAR 8-K filings, the ground-truth materiality
signal for the News Intelligence System's Tier 1. Companies are
*legally required* to file an 8-K within 4 business days of a material
event (a new agreement, an acquisition, an executive departure, a
lawsuit outcome) — this isn't an editorial judgment call about what's
important, it's the regulatory definition. Free, official, no API key.

Uses the per-company submissions endpoint (filtered by CIK), not
full-text search. Full-text search-by-name was tested and rejected —
it free-text-matches a company's name anywhere in any filing, including
unrelated companies that just mention the name in passing. Filtering by
CIK directly is precise; searching by name is not.

SEC's fair-use policy requires a descriptive User-Agent identifying the
requester — this is a real requirement, not optional, and requests
without one get blocked.
"""

from datetime import datetime, timedelta, timezone

import requests

HEADERS = {"User-Agent": "Undertow (personal, non-commercial project) contact: undertow-project@example.com"}
CIK_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

# Standard SEC 8-K item codes, mapped to plain language for retail
# investors who've never seen a filing. Unmapped codes fall back to a
# generic "Item X.XX" label rather than being dropped.
ITEM_LABELS = {
    "1.01": "Entered a material agreement",
    "1.02": "Terminated a material agreement",
    "1.03": "Filed for bankruptcy or receivership",
    "2.01": "Completed an acquisition or disposition",
    "2.02": "Reported results of operations",
    "2.03": "Took on a financial obligation",
    "2.04": "Triggered an accelerated financial obligation",
    "2.05": "Announced exit or restructuring costs",
    "2.06": "Disclosed a material impairment",
    "3.01": "Received a delisting or listing-rule notice",
    "3.02": "Sold unregistered securities",
    "4.01": "Changed its auditor",
    "4.02": "Said prior financial statements can't be relied on",
    "5.01": "Changed control of the company",
    "5.02": "Officer or director departure/appointment",
    "5.03": "Amended its charter or bylaws",
    "5.07": "Held a shareholder vote",
    "7.01": "Made a public disclosure (Reg FD)",
    "8.01": "Disclosed another material event",
    "9.01": "Filed financial statements or exhibits",
}

_cik_cache = None


def _load_cik_map():
    """Official, free ticker->CIK mapping. Cached in-process since it's
    a ~large file covering every public company and doesn't change fast
    enough to justify refetching per ticker."""
    global _cik_cache
    if _cik_cache is not None:
        return _cik_cache
    try:
        r = requests.get(CIK_MAP_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        _cik_cache = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in data.values()}
    except Exception as e:
        print(f"  [sec] failed to load ticker->CIK map: {type(e).__name__}: {e}")
        _cik_cache = {}
    return _cik_cache


def fetch_recent_8ks(tickers, days=3, max_per_ticker=3):
    """Returns {ticker: [{"date", "items", "labels", "url"}]} — 8-Ks
    filed within the last `days` days, most recent first. `recent`
    filings from the submissions API are already sorted newest-first,
    so this stops scanning as soon as it passes the cutoff instead of
    walking the ticker's whole filing history."""
    cik_map = _load_cik_map()
    if not cik_map:
        return {}

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = {}

    for ticker in tickers:
        cik = cik_map.get(ticker)
        if not cik:
            continue
        try:
            r = requests.get(SUBMISSIONS_URL.format(cik=cik), headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            recent = r.json()["filings"]["recent"]
        except Exception as e:
            print(f"  [sec] {ticker} failed: {type(e).__name__}: {e}")
            continue

        forms = recent.get("form", [])
        items_list = recent.get("items", [""] * len(forms))
        filings = []
        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            try:
                filed = datetime.strptime(recent["filingDate"][i], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except (ValueError, IndexError):
                continue
            if filed < cutoff:
                break

            item_codes = [c.strip() for c in (items_list[i] or "").split(",") if c.strip()]
            labels = [ITEM_LABELS.get(c, f"Item {c}") for c in item_codes] or ["Other disclosure"]
            accession = recent["accessionNumber"][i].replace("-", "")
            doc = recent["primaryDocument"][i]
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{doc}"

            filings.append({
                "date": recent["filingDate"][i],
                "items": item_codes,
                "labels": labels,
                "url": url,
            })
            if len(filings) >= max_per_ticker:
                break

        if filings:
            out[ticker] = filings

    return out
