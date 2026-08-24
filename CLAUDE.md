# Undertow — orientation doc for a fresh Claude session

Read this first if you have no memory of this project (a new session, a
lost conversation, whatever). It's a map, not a replacement for the docs
it points to — go read those for real depth, this just tells you where
to look and what to know before you touch anything.

## What this is

**Undertow** — a retail-sentiment + market-analytics dashboard, live at
a GitHub Pages site. Not just a dashboard: a real product idea (see
`PRODUCT.md`) — a "why layer" that reconciles four pillars of stock
analysis (Crowd sentiment, Wall Street analysts, Business fundamentals,
Market/price context) and explains *why* they agree or disagree, instead
of fusing everything into one opaque number the way every competitor
researched does (`COMPETITIVE_INTELLIGENCE.md`).

Solo project, $0/month budget, built almost entirely through Claude Code
sessions. GitHub: `keyur750/stock-pulse` (public repo — GitHub Pages and
unlimited Actions minutes both require this). Runs unattended: GitHub
Actions regenerates the dashboard once a day and refreshes live quotes
every 15 minutes, commits straight to `main`, no PR workflow, no server
to maintain.

**Read in this order if you're getting oriented:**
1. This file (fast map)
2. `README.md` — user-facing setup + "how it works under the hood"
3. `PRODUCT.md` — the actual product vision, the moat, the phased
   roadmap, every major decision and why it was made. This is the real
   source of truth for *why* things are built the way they are — it's
   long, but it's kept meticulously current. If something here conflicts
   with `PRODUCT.md`, trust `PRODUCT.md` and fix this file.
4. `COMPETITIVE_INTELLIGENCE.md` — deep per-competitor research (Phase 1
   of the roadmap), useful context for "why doesn't Undertow just do X
   like TipRanks/Simply Wall St."
5. Any `*_RESET.md` file in repo root (`FULL_FUNDAMENTAL_RESET.md`,
   `MARKET_PILLAR_RESET.md`, `WALL_STREET_PILLAR_RESET.md`,
   `OVERALL_SCORE_RESET.md`, `SITE_REDESIGN_RESET.md` as of this
   writing) — these are the project's living, phased-plan scratchpads
   for any major initiative (a pillar rebuild, a scoring-methodology
   change, a site redesign), each with its own gap analysis, research
   foundations, phased plan, status-snapshot table, and an explicit
   "Next step:" line at the very bottom. **Check `ls -la *_RESET.md` for
   recent mtimes before trusting the "Where things stand" section
   below** — a RESET doc's own status table is far more likely to be
   current than this file's summary of it, the same way `PRODUCT.md`
   already outranks this file for *why* a decision was made.

## Architecture map

**Orchestration:** `main.py` — the daily pipeline. Reads `config.json`,
runs every source/pillar/signal step below in order, writes three static
HTML pages (`docs/dashboard.html`, `docs/sentiment.html`,
`docs/stock.html`) by embedding a JSON payload into
`dashboard_template.html` / `sentiment_template.html` / `stock_template.html`.
`refresh_quotes.py` is a separate, lighter script (prices only, every 15
min) that writes `docs/quotes.json`.

**Crowd pillar** (what retail is saying):
- `stocktwits.py`, `reddit.py`, `bluesky.py` — three independent chatter
  sources, each returns `{ticker: [message_dicts]}` in a common shape
  (a `body` key + `chatter_source` + `author` + `created_at`). All three
  are additive/optional — missing credentials just means fewer sources,
  never a broken pipeline.
- `apewisdom.py`, `trends.py` — mention-volume-only cross-checks (no
  sentiment direction), used for spike detection, not scoring.
- `sentiment.py` — the actual scoring engine. Two-tier trust: StockTwits
  self-tagged Bullish/Bearish messages are ground truth (weight 2.0);
  everything else is read by one batched Gemini call per ticker (an LLM
  handles sarcasm/slang/negation, which the old pure-VADER approach
  couldn't — VADER is kept only as an offline fallback). Then:
  author-capping (`dedupe_by_author`, max 3 msgs/author/source, applied
  before sampling) → recency decay + Bayesian shrinkage toward neutral
  for thin samples (`score_messages`, half-life 8h, k=3) →
  `crowd_confidence()`, a real 0-100 composite (sample size 50% / cross-
  source agreement 30% / tag ratio 20%) added 2026-08-20 as "Phase 3" of
  a 4-phase crowd-score-engine plan.

**Wall Street pillar:** `wallstreet.py` — consensus rating, price-target
upside, recommendation-trend, all free via `yfinance`. Note: sell-side
ratings cluster structurally bullish, so this pillar uses its own higher
divergence thresholds (55/78 vs. 35/65 for the other three pillars) —
see `main.py`'s `_WALLSTREET_LEVEL_THRESHOLDS`.

**Business pillar** (renamed from "Fundamentals"): `fundamentals.py` —
five 0-100 category scores (growth/profitability/cash flow/balance
sheet/valuation) via `yfinance`, transparent piecewise-linear scoring
(`_scale`), raw metrics always carried alongside the score.

**Market pillar:** `market.py` — momentum/extension (distance from
52-week high, position vs. moving averages) + realized volatility.
Deliberately not a "good/bad" verdict — a high score means "priced for
strength," which the Divergence Engine and the AI analyst reason about
rather than treat as automatically good.

**Synthesis:** `analyst.py` — the AI analyst. One Gemini call per
flagship ticker, reads all four pillars + price + matched news, returns
a structured score/verdict/summary/bullish-bearish factors/risks/
catalysts/per-pillar reasoning. Deliberately not a fixed formula — see
its docstring and prompt for the reasoning-in-context principle.
`llm_client.py` holds the shared Gemini client (pinned model, see
"Conventions" below), used by `sentiment.py`, `analyst.py`, and
`news_ranker.py`.

**Divergence Engine:** `main.py`'s `classify_divergence` /
`compute_signals` — full pairwise comparison across all four pillar
scores, classified into four named patterns (Emerging Consensus, Retail
Euphoria, Fundamental Deterioration, Under-the-Radar). This — not any
single pillar, not the AI — is the actual differentiator; see
`PRODUCT.md`'s "The moat."

**News Intelligence** (three tiers, each answering a different
question): `sec_filings.py` (Tier 1, real SEC 8-Ks, ground-truth
materiality, not LLM-filtered) → `news_fetcher.py` + `news_ranker.py`
(Tier 2, per-company news via `yfinance` + Finnhub if `FINNHUB_API_KEY`
is set, deduplicated across the two aggregators via
`news_fetcher.dedupe_news_items` — a word-overlap check on normalized
titles — then one batched Gemini call per ticker to separate real news
from listicle/opinion filler) → generic RSS feeds + Finnhub's
general-news stream, deduplicated the same way (Tier 3, ambient market
context, unranked). **News mechanism reset (2026-08-24):** added
Finnhub as a second Tier 2/3 source (PRODUCT.md flagged this back on
2026-08-13 as a deferred "clean fast-follow," never built until now) and
replaced pure-freshness ordering with a combined relevance+recency score
(`templates/partials/news_utils.js.j2`, shared by `dashboard_template.html`'s
cross-tier feed and `stock_template.html`'s per-ticker Company News list)
— exponential half-life decay on each item's importance, the same decay
shape `sentiment.py`/`wallstreet.py` already use, so a major story
doesn't get buried by fresher-but-routine headlines within minutes, nor
does it sit at the top forever once it's actually stale.

**Charts:** `market_data.py` (quotes + macro instruments: indices,
crypto, commodities, global markets) and `market_history.py`
(multi-timeframe 1D-20Y chart data, price-return not total-return, never
fabricates a data point). `logos.py` caches real company logos to
`docs/logos/` once per ticker.

**Live backend (in progress):** `supabase_sync.py` + `supabase/schema.sql`
— migrating off "commit a JSON file to git" onto live Supabase tables,
one slice at a time (`ticker_snapshots` → `sentiment_history` →
`signal_history`, in that order, each still additive — the JSON files
in `data/` are still the primary source, Supabase is a parallel write).
**Reconciled 2026-08-21 (was flagged here as unresolved):** `schema.sql`
references pre-existing `stocks` / `watchlists` / `watchlist_items`
tables with a `user_id` column referencing `auth.users` — real user-
account infrastructure from an earlier, undocumented "Milestone A."
`PRODUCT.md` used to say "no user accounts" was out of scope, which was
already inaccurate when written. `SITE_REDESIGN_RESET.md`'s Phase 3
closed this: accounts are in scope, wired consistently across all three
app pages, and deliberately unlock only the existing personal watchlist
for now (no alerts, no saved screens) — `PRODUCT.md` now says so.

**Config:** `config.json` — watchlist (30 tickers) = flagship_tickers
right now (see `PRODUCT.md`'s "Decisions locked in" for why they're kept
equal), every tunable constant (crowd scoring params, sleep/rate-limit
timings, history retention). **Never hardcode a constant that already
has a `config.json` entry.**

**CI:** `.github/workflows/update-dashboard.yml` (daily, full pipeline,
~20-30 min) and `.github/workflows/refresh-quotes.yml` (every 15 min,
prices only). Both commit and push straight to `main` with an automatic
rebase-and-retry loop for the race between them — see the workflow
files' own comments before touching this.

## Conventions this project actually enforces (not aspirational)

- **Pin AI models, never `-latest`.** A `-latest` alias silently
  repointed mid-project once and zeroed out a day's free quota. See
  `llm_client.py`'s `MODEL` constant and its docstring.
- **Batch before you pay.** Every LLM call in this pipeline is one
  batched call per ticker (sentiment classification, news ranking),
  never one call per item — this is why the free tier has always been
  enough. Don't introduce a per-item LLM call pattern.
- **Verified live, never assumed.** Every threshold/constant in this
  codebase that looks arbitrary (shrinkage k=3, Wall Street's 55/78
  divergence bucket, the piecewise-linear scoring breakpoints) was
  checked against real fetched data, not picked from a guess or copied
  from docs/memory. If you're about to tune a constant, check real
  current data first, the way every phase in `PRODUCT.md` did.
- **Never fabricate a missing value.** Missing data is `None`/a real gap
  in a chart, never a guessed placeholder, an interpolated point, or a
  silently-defaulted neutral score. Every pillar's `coverage` field
  exists so a partial read is visible, not hidden.
- **Additive, not breaking.** New fields get added to existing dicts;
  existing fields don't get repurposed or removed without checking every
  consumer (frontend templates read this JSON payload directly).
- **Graceful degradation everywhere.** Every external source
  (Reddit/Bluesky credentials missing, Gemini call fails, Supabase down,
  a single ticker's fetch failing) logs a warning and continues with
  what's available — nothing in this pipeline should take down the
  whole run.
- **No comments explaining WHAT — only WHY**, and usually a fairly long
  WHY when a decision isn't obvious (a specific bug it fixes, a specific
  live-tested number, a rejected alternative). This is the actual house
  style across every file — match it.
- **Public repo, direct-to-main commits.** No PR review step historically
  — commits go straight to `main`, including from Claude Code sessions
  (see git log). Confirm with the user before pushing regardless; this
  describes the existing pattern, not blanket standing authorization.

## Where things stand right now (last updated 2026-08-22)

This section is a snapshot, not the source of truth — see item 5 of the
reading order above. As of 2026-08-22, four RESET docs are finished and
shipped (`FULL_FUNDAMENTAL_RESET.md`, `MARKET_PILLAR_RESET.md`,
`WALL_STREET_PILLAR_RESET.md`, `OVERALL_SCORE_RESET.md`), each down to
exactly one remaining phase, and all four of those remaining phases (bar
Wall Street's) are gated on the same thing:

- **`OVERALL_SCORE_RESET.md`**, **`FULL_FUNDAMENTAL_RESET.md`**,
  **`MARKET_PILLAR_RESET.md`** — Phase 1 done and live-verified on each.
  The one remaining phase on all three (recalibrating base
  weights/backtesting against real forward-return data) is blocked on
  `data/signal_history.json` accumulating enough real days — not
  actionable yet, by design, not a gap to fill.
- **`WALL_STREET_PILLAR_RESET.md`** — one open phase (price-target
  optimism-bias treatment), gated on a research question rather than
  history: does a free, live source of sector-average target-implied
  upside exist? Check the doc's own "Next step" before assuming this is
  ready to build.
- **`SITE_REDESIGN_RESET.md`** — **Phases 0 through 5 done and
  live-verified** (design tokens, Jinja2 templating for all six pages
  including `index.html`/`about.html`/`careers.html`, flat navigation,
  the accounts decision, the full visual redesign pass, a copy audit, and
  a two-pass WCAG 2.2 AA contrast fix). Templating is fully wired now —
  `index_template.html`/`about_template.html`/`careers_template.html`
  all feed `main.py` via `templates/partials/*.j2`, not a stale
  exists-but-unwired state. Phases 6 (performance/Core Web Vitals), 7
  (modern features: comparison view, "what changed," Cmd+K, skeleton
  loading, PWA), and 8 (QA/rollout checklist) are not started. **Note:**
  ad-hoc visual polish has continued same-day past this doc's own last
  edit (careers hero redesign, homepage hero motion, Four Signals card
  tilt, and — in the single most recent commit as of this writing — full
  **removal** of the four-axis diamond glyph that Phase 4's status line
  still lists as shipped, keeping only the four pillar drill-down cards
  below it). The doc's status table hasn't caught up to that reversal —
  check `git log` for anything past the doc's own last-modified date
  before trusting its table verbatim.

**A crash-recovery note worth keeping current:** a Claude Code session
died mid-work on 2026-08-21 while `SITE_REDESIGN_RESET.md` was being
built; the RESET docs above are what let a fresh session pick this up
cold. Separately, local and `origin/main` diverged by 24 commits during
that downtime (CI's quote-refresh/dashboard workflows kept running
against the old pre-Jinja2 `main.py`) — resolved by stashing local
changes, fast-forward pulling, and reapplying. **If you're orienting
after another lost session, check `git log HEAD..origin/main` before
trusting either side's `data/*.json`/`docs/*.html` as current.**

**Phase 4 of the crowd-score engine (FinBERT validation) — resolved, not
open.** Phases 1-3 (author-capping, shrinkage/decay, `crowd_confidence`)
shipped 2026-08-20. The full 30-ticker `finbert_full_run.log` run
confirmed the earlier 5-ticker smoke test: Gemini (production's current
path) reconstructs real self-tagged StockTwits sentiment at 67.0%
accuracy; FinBERT scores 13.8%, defaulting the large majority of
messages to "neutral" regardless of its own confidence score. Per the
user's own instruction ("don't put FinBERT out of scope if it's
helpful, but let's see"), the honest conclusion is that FinBERT does not
help *as a blanket confidence signal* the way originally imagined —
Phase 4 needs a different shape, not more validation runs. FinBERT
stays in scope only if a specific real use for it turns up; it should
not be force-fit into the confidence pipeline by default.

## Quick facts worth not re-deriving

- Watchlist = flagship tickers, 30 symbols, in `config.json`.
- Gemini model: `gemini-3.1-flash-lite`, pinned in `llm_client.py`.
- No raw chat messages are persisted anywhere in the repo — only
  aggregated daily scores (`data/history.json`,
  `data/signal_history.json`, `data/analyst_history.json`). Anything
  needing real message text (like FinBERT validation) has to fetch live.
- Local dev machine: Windows, Python 3.14, `torch` (CPU build) was
  already installed before this session added `transformers`.
- `GEMINI_API_KEY` is set in the local environment already (confirmed
  this session) — local runs of anything Gemini-dependent work without
  extra setup.
