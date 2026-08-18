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


def sync_sentiment_history(ticker_results: list, today: str) -> int:
    """Writes today's per-ticker avg_sentiment/mentions into sentiment_history
    -- Phase 2. Unlike sync_ticker_snapshots, this never needs to read
    anything back first: main.py already has today's real numbers in
    ticker_results, so this just upserts one row per ticker for `today`.
    The (ticker, date) primary key means a same-day re-run naturally
    replaces today's row instead of duplicating it -- data/history.json's
    save_history() dedupe, for free, no trimming logic needed at all since
    this table has no size constraint forcing old rows to be discarded."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("  [supabase] SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set, skipping sentiment history sync")
        return 0

    try:
        client = create_client(url, key)

        rows = [
            {
                "ticker": r["ticker"],
                "date": today,
                "avg_sentiment": r["avg_sentiment"],
                "mentions": r.get("mentions"),
            }
            for r in ticker_results
            if r.get("avg_sentiment") is not None
        ]

        if rows:
            client.table("sentiment_history").upsert(rows).execute()
        print(f"  [supabase] upserted {len(rows)}/{len(ticker_results)} sentiment history rows for {today}")
        return len(rows)
    except Exception as e:
        print(f"  [supabase] sentiment history sync failed, continuing without it: {e}")
        return 0
