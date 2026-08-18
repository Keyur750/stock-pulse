"""
One-time script: copies the existing data/signal_history.json (currently
capped at signal_history_days_to_keep, 365 days) into the new
signal_history Supabase table, so Phase 3a of the live-backend migration
doesn't start from an empty table. Not part of the daily pipeline -- run
this once, by hand, after adding the table via supabase/schema.sql.

Usage (with SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY set in the
environment):

    python backfill_signal_history.py
"""

import json
import os
import sys

from supabase import create_client

ROOT = os.path.dirname(os.path.abspath(__file__))
SIGNAL_HISTORY_PATH = os.path.join(ROOT, "data", "signal_history.json")


def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must both be set in the environment.")
        sys.exit(1)

    if not os.path.exists(SIGNAL_HISTORY_PATH):
        print(f"No signal history file found at {SIGNAL_HISTORY_PATH} -- nothing to backfill.")
        sys.exit(1)

    with open(SIGNAL_HISTORY_PATH, encoding="utf-8") as f:
        history = json.load(f)

    rows = []
    for snapshot in history:
        date = snapshot.get("date")
        if not date:
            continue
        for ticker, entry in snapshot.get("tickers", {}).items():
            if not isinstance(entry, dict):
                continue
            rows.append({
                "ticker": ticker,
                "date": date,
                "crowd": entry.get("crowd"),
                "wall_street": entry.get("wall_street"),
                "business": entry.get("business"),
                "market": entry.get("market"),
                "divergence": entry.get("divergence"),
                "confidence": entry.get("confidence"),
                "price": entry.get("price"),
            })

    if not rows:
        print("No rows found in signal_history.json to backfill.")
        return

    client = create_client(url, key)
    batch_size = 500
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        client.table("signal_history").upsert(batch).execute()
        total += len(batch)
        print(f"  upserted {total}/{len(rows)} rows...")

    print(f"Done. Backfilled {total} signal_history rows from {SIGNAL_HISTORY_PATH}.")


if __name__ == "__main__":
    main()
