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

        # Keyed by ticker directly (see supabase/schema.sql) -- no
        # dependency on the `stocks` table's id column or its exact type.
        rows = [
            {
                "ticker": t["ticker"],
                "price": t.get("price"),
                "change_pct": t.get("change_pct"),
                "avg_sentiment": t.get("avg_sentiment"),
                "mentions": t.get("mentions"),
                "label": t.get("label"),
            }
            for t in watchlist_grid
        ]

        if rows:
            client.table("ticker_snapshots").upsert(rows).execute()
        print(f"  [supabase] upserted {len(rows)}/{len(watchlist_grid)} ticker snapshots")
        return len(rows)
    except Exception as e:
        print(f"  [supabase] sync failed, continuing without it: {e}")
        return 0
