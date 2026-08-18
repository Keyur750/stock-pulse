-- Undertow — Supabase schema.
--
-- This is the first time this project's schema has been checked into
-- version control. The tables below `stocks` / `watchlists` /
-- `watchlist_items` already exist in the live Supabase project (built
-- during Milestone A) but were never captured in the repo — this section
-- reverse-engineers their shape from the `sbClient` calls in
-- dashboard_template.html so there's finally one source of truth. If the
-- live project differs from what's below, the live project is correct —
-- update this file to match, don't assume this file is correct.
--
-- `ticker_snapshots` (bottom of this file) is new: Phase 1 of moving
-- Undertow off "commit a JSON file to git" and onto a real, live-queried
-- table for one representative slice of data (price, change%, sentiment
-- label, mentions). See PRODUCT.md / project history for why this is
-- scoped to one table rather than the full data model in one pass.

-- ============================================================
-- Existing tables (Milestone A) — reverse-engineered, not authored here
-- ============================================================

-- create table stocks (
--   id uuid default gen_random_uuid() primary key,  -- confirmed uuid live (2026-08-16); the rest of this block is still an unconfirmed best guess
--   ticker text not null unique
-- );
--
-- create table watchlists (
--   id uuid default gen_random_uuid() primary key,
--   user_id uuid not null references auth.users(id),
--   name text not null
-- );
--
-- create table watchlist_items (
--   watchlist_id uuid not null references watchlists(id),
--   stock_id uuid not null references stocks(id),
--   primary key (watchlist_id, stock_id)
-- );
--
-- An `on_auth_user_created` trigger is referenced in dashboard_template.html
-- as the intended way a new user gets their first `watchlists` row: the
-- client-side code has a fallback that creates one lazily if it's missing,
-- which implies the trigger doesn't reliably fire today — worth checking
-- directly in the Supabase dashboard (Database > Triggers) rather than
-- assuming either the trigger or the fallback is the real source of truth.
--
-- Left commented out deliberately: these tables already exist live. Do not
-- run this section — it's here for documentation, not execution. If you
-- ever need to recreate this schema from scratch, uncomment it first (and
-- verify every column type against the live project before you do, the
-- same way `stocks.id` turned out to be uuid, not the bigint first
-- guessed here).

-- ============================================================
-- New: ticker_snapshots (Phase 1 of the live-backend migration)
-- ============================================================
-- Deliberately has no foreign key into `stocks` -- that table's exact
-- shape isn't fully confirmed (see above), and this table doesn't
-- actually need the relationship for anything Phase 1 does. Using the
-- ticker symbol itself as the primary key avoids depending on another
-- table's schema being guessed correctly.

create table if not exists ticker_snapshots (
  ticker text primary key,
  price numeric,
  change_pct numeric,
  avg_sentiment numeric,
  mentions integer,
  label text,
  updated_at timestamptz not null default now()
);

alter table ticker_snapshots enable row level security;

-- Public market-summary data, not user-specific — anyone (including the
-- anonymous/publishable key already embedded in the site's HTML) can read
-- it. Only main.py writes to this table, using the service_role key
-- (which bypasses RLS entirely), so there is deliberately no insert /
-- update / delete policy for the anon or authenticated roles below.
create policy "Public read access" on ticker_snapshots
  for select using (true);

-- ============================================================
-- New: sentiment_history (Phase 2 of the live-backend migration)
-- ============================================================
-- data/history.json is a git-committed flat file, so it's trimmed to
-- history_days_to_keep (30, config.json) every run to keep the repo from
-- growing forever -- this table has no such constraint. Primary key on
-- (ticker, date) means a same-day re-run upserts over today's row
-- instead of duplicating it, the same dedupe save_history() does in
-- Python, for free. No frontend reads this yet -- see project notes for
-- why that's a deliberate, separate later phase.

create table if not exists sentiment_history (
  ticker text not null,
  date date not null,
  avg_sentiment numeric not null,
  mentions integer,
  primary key (ticker, date)
);

alter table sentiment_history enable row level security;

create policy "Public read access" on sentiment_history
  for select using (true);

-- ============================================================
-- New: signal_history (Phase 3a of the live-backend migration)
-- ============================================================
-- data/signal_history.json is git-committed and trimmed to
-- signal_history_days_to_keep (365, config.json) -- this is the "track
-- record" data PRODUCT.md treats as the long-term moat, so removing that
-- cap matters most here. Same (ticker, date) upsert-dedupe pattern as
-- sentiment_history. Columns match build_signal_snapshot()'s return shape
-- in main.py exactly.

create table if not exists signal_history (
  ticker text not null,
  date date not null,
  crowd numeric,
  wall_street numeric,
  business numeric,
  market numeric,
  divergence text,
  confidence numeric,
  price numeric,
  primary key (ticker, date)
);

alter table signal_history enable row level security;

create policy "Public read access" on signal_history
  for select using (true);
