"""
Writes the ticker summary table (price, change%, sentiment, mentions) into
a real Supabase Postgres table -- Phase 1 of moving Undertow off "commit a
JSON file to git" and onto a live-queried backend for this one slice of
data. See supabase/schema.sql for the ticker_snapshots table definition.

Uses the service_role key (SUPABASE_SERVICE_ROLE_KEY), which bypasses RLS
entirely -- this must only ever run server-side (GitHub Actions), never in
client code, and never be committed to the repo. Every failure mode here
is swallowed and logged rather than raised: this write is additive to the
existing static HTML/JSON output, never a dependency of it, so a Supabase
outage or a missing credential must never break the rest of the pipeline.
"""

import os

from supabase import create_client


def sync_ticker_snapshots(watchlist_grid: list) -> int:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("  [supabase] SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set, skipping live sync")
        return 0

    try:
        client = create_client(url, key)

        # ticker_snapshots.stock_id references the existing `stocks` table
        # (built for the personal-watchlist feature) -- map ticker -> id
        # rather than assuming one, since not every tracked ticker is
        # guaranteed to already have a `stocks` row.
        stocks = client.table("stocks").select("id,ticker").execute().data or []
        stock_id_by_ticker = {s["ticker"]: s["id"] for s in stocks}

        rows = []
        skipped = []
        for t in watchlist_grid:
            ticker = t["ticker"]
            stock_id = stock_id_by_ticker.get(ticker)
            if stock_id is None:
                skipped.append(ticker)
                continue
            rows.append({
                "stock_id": stock_id,
                "ticker": ticker,
                "price": t.get("price"),
                "change_pct": t.get("change_pct"),
                "avg_sentiment": t.get("avg_sentiment"),
                "mentions": t.get("mentions"),
                "label": t.get("label"),
            })

        if rows:
            client.table("ticker_snapshots").upsert(rows).execute()
        if skipped:
            print(f"  [supabase] skipped {len(skipped)} ticker(s) missing from `stocks`: {', '.join(skipped)}")
        print(f"  [supabase] upserted {len(rows)}/{len(watchlist_grid)} ticker snapshots")
        return len(rows)
    except Exception as e:
        print(f"  [supabase] sync failed, continuing without it: {e}")
        return 0
