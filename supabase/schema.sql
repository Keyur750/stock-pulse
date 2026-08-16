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
--   id bigint generated always as identity primary key,
--   ticker text not null unique
-- );
--
-- create table watchlists (
--   id bigint generated always as identity primary key,
--   user_id uuid not null references auth.users(id),
--   name text not null
-- );
--
-- create table watchlist_items (
--   watchlist_id bigint not null references watchlists(id),
--   stock_id bigint not null references stocks(id),
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
-- ever need to recreate this schema from scratch, uncomment it first.

-- ============================================================
-- New: ticker_snapshots (Phase 1 of the live-backend migration)
-- ============================================================

create table if not exists ticker_snapshots (
  stock_id bigint primary key references stocks(id),
  ticker text not null,
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
