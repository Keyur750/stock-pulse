"""
One-time script: copies the existing data/history.json (currently capped
at history_days_to_keep, 30 days) into the new sentiment_history Supabase
table, so Phase 2 of the live-backend migration doesn't start from an
empty table. Not part of the daily pipeline -- run this once, by hand,
after creating the table via supabase/schema.sql.

Usage (with SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY set in the
environment):

    python backfill_sentiment_history.py
"""

import json
import os
import sys

from supabase import create_client

ROOT = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(ROOT, "data", "history.json")


def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must both be set in the environment.")
        sys.exit(1)

    if not os.path.exists(HISTORY_PATH):
        print(f"No history file found at {HISTORY_PATH} -- nothing to backfill.")
        sys.exit(1)

    with open(HISTORY_PATH, encoding="utf-8") as f:
        history = json.load(f)

    rows = []
    for snapshot in history:
        date = snapshot.get("date")
        if not date:
            continue
        for ticker, entry in snapshot.get("tickers", {}).items():
            avg_sentiment = entry.get("avg_sentiment") if isinstance(entry, dict) else entry
            if avg_sentiment is None:
                continue
            rows.append({
                "ticker": ticker,
                "date": date,
                "avg_sentiment": avg_sentiment,
                "mentions": entry.get("mentions") if isinstance(entry, dict) else None,
            })

    if not rows:
        print("No rows found in history.json to backfill.")
        return

    client = create_client(url, key)
    # Batched to stay well under any request-size limit -- 500 rows/batch
    # is comfortable for a table this narrow, and there's no reason to
    # send thousands of rows in a single request just because we can.
    batch_size = 500
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        client.table("sentiment_history").upsert(batch).execute()
        total += len(batch)
        print(f"  upserted {total}/{len(rows)} rows...")

    print(f"Done. Backfilled {total} sentiment_history rows from {HISTORY_PATH}.")


if __name__ == "__main__":
    main()
