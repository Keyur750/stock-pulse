# Wall Street Pillar Reset — analyst-data rebuild

**Read this first if you have no memory of this specific work stream** (a
new session, lost history, whatever). Same spirit as `CLAUDE.md` and its
sibling doc `FULL_FUNDAMENTAL_RESET.md` (the Business pillar's equivalent
rebuild, already 5/6 phases done — read that one too, this file assumes
you know its pattern): a map of what was decided, why, what's built, and
what's left — not a replacement for the code itself. If this file and the
code disagree, trust the code and fix this file. **Update the one-line
status below every phase.**

**One-line status (update every phase):** Phases 1-4 done and verified
live (2026-08-20/21) — raw analyst data persisted to the payload
(Phase 1); real EPS-estimate-revision Agreement + Magnitude scoring
(Phase 2); `revision_trend`'s crude 2-point proxy replaced with a real
recency-decayed, boldness-weighted `rating_momentum` signal from
individual dated upgrade/downgrade actions (Phase 3); `wallstreet_
confidence()` (coverage breadth + price-target dispersion + rating
recency) plus a full reweighting of all 5 categories toward the
literature-favored revision/change signals and away from static rating
level (Phase 4). Phase 5 (price-target optimism-bias treatment) is next.

## Why this exists

A review of `wallstreet.py` (started 2026-08-20, same session that
produced this doc) found the Wall Street pillar is the least-developed of
the four — not wrong, but thin in a specific, fixable way, and worth
fixing before treating its score as trustworthy:

1. **The raw data is computed, then thrown away.** `run_analyst_pipeline`
   in `main.py` fetches `w = fetch_analyst_data(ticker)` and computes
   `wscore = score_wallstreet(w)`, but only `wscore["overall"]` survives
   into `pillar_scores` — the single number driving the pillar dial.
   Neither `w` nor `wscore`'s sub-category breakdown is ever added to the
   JSON payload `main()` writes. Confirmed by reading `main()`'s `payload`
   dict directly: there is no `"wallstreet"` key, unlike `"fundamentals"`
   for the Business pillar. This is the exact same "computed and
   discarded" gap `FULL_FUNDAMENTAL_RESET.md`'s intro describes for
   fundamentals before that rebuild — Wall Street just hasn't had its
   equivalent pass yet.
2. **Nothing reaches the frontend except one dial and one AI sentence.**
   Confirmed by grepping `wall_street`/`wallstreet` across all three
   templates: the only per-pillar UI is the generic `pillarDialSvg` (a
   bare 0-100 radial gauge, identical styling to all four pillars) plus
   whatever one sentence Gemini writes into `pillar_reads.wall_street`.
   No consensus-rating text, no price target, no analyst count, no
   upside %, no sub-score breakdown, anywhere — the most opaque pillar on
   the site. Business, by contrast, has a full radar chart
   (`renderFundamentalsRadar`) plus raw-financials sections built
   directly off its persisted payload data.
3. **The current weighting may be close to backwards relative to
   published research** (see Research foundations below): the static
   rating *level* — the weakest-evidenced signal in the literature —
   carries the highest weight (0.40) in `score_wallstreet()`, while the
   one attempt at a *revision* signal (the strongest-evidenced one) is a
   crude 2-point proxy (oldest vs. newest row of `ticker.recommendations`,
   an unverified ~3-month window) carrying only 0.25.
4. **No confidence/uncertainty layer**, unlike every other pillar.
   Crowd has `crowd_confidence()` (sample size + cross-source agreement +
   tag ratio). Business has `coverage` + `sector_benchmark_matched`. Wall
   Street has only a bare 0-3 `coverage` count — "24 analysts, tight
   agreement, all rated last month" and "3 analysts, wildly split
   targets, oldest rating 11 months stale" currently look identical.

None of this means the current implementation is wrong to have shipped —
same status as pre-rebuild `fundamentals.py`: an honest, documented
first-pass heuristic, not a validated one. This doc is the plan to close
the gap the same deliberate, phased, live-verified way Business's rebuild
did.

## Research foundations — what a real quant/practitioner would use

Every idea below maps to a specific phase further down. Sources are real,
checked live via web search this session (2026-08-20), not from
training-data memory — see the chat transcript for full citations if this
doc's summary needs re-verifying.

- **Recommendation *levels* carry little independent predictive power;
  recommendation *changes* (revisions) do.** Womack (1996): new Buy
  ratings drift +2.4% over the following 6 months, new Sells drift
  -9.1% — the *change* is where the signal lives. A broader review
  (Bradshaw) found no significant relation between the consensus
  recommendation *level* itself and future returns once other known
  return drivers are controlled for. → **Phases 2, 3, 4** (rebalance
  weight away from static level, toward real revision signals).
- **Earnings estimate revisions are the single most emphasized driver of
  subsequent price moves** in the sell-side-signal literature — this is
  the entire premise of the Zacks Rank, a decades-old, live-tracked
  commercial methodology built on four factors: Agreement (are analysts
  revising EPS estimates the same direction), Magnitude (how much),
  Upside (Zacks' own proprietary "most accurate estimate" vs. consensus —
  not replicable for free, noted not copied), and Surprise (recent
  quarters' EPS-beat pattern). Zacks does not publish its exact internal
  weighting formula — only the qualitative four-factor structure is
  public; any Undertow implementation needs its own justified weights,
  not a copy of a black box. → **Phase 2**.
- **Price targets are systematically, structurally optimistic.** Roughly
  30-50% of 12-month targets are actually reached within their stated
  horizon across large-cap US stocks; the bias is worse for large-caps,
  high institutional ownership, and higher-volatility names, and is
  partly explained by underwriting/advisory-relationship incentives
  (upside costs an analyst little if wrong a year later; a public
  negative call risks the relationship now). → **Phase 5** (treat
  `upside_pct` with real skepticism, not face value).
- **Dispersion across analysts is a real, distinct signal — two different
  literatures, don't conflate them:**
  - Diether/Malloy/Scherbina (2002): high *earnings-forecast* dispersion
    → *lower* subsequent returns (their read: dispersion proxies
    differences of opinion; prices skew toward the optimistic view when
    pessimists can't easily short).
  - A separate strand (Palley/Steffen/Zhang) treats *price-target*
    dispersion as moderating the **informativeness** of the consensus
    target itself — tight agreement across analysts makes a consensus
    target more trustworthy; a wide high/low spread makes it a fragile
    average.
  Both independently support using dispersion as a confidence/uncertainty
  input, which is the use this doc actually needs (not a return
  predictor). → **Phase 4** (`wallstreet_confidence()`).
- **The market reacts more strongly to "bold" rating changes than to
  "herding" ones.** Clement & Tse (2005): a bold forecast deviates from
  both the consensus *and* the analyst's own prior view; herding
  forecasts drift toward what everyone already thinks. Bold calls carry
  more real private information; inexperienced/career-concerned analysts
  herd more. → **Phase 3** (weight an away-from-consensus rating change
  higher than a reiteration).
- **Stale ratings are a documented, real problem**, not a hypothetical
  one. Most methodologies treat a rating over a year old as stale; one
  study found a recency-weighting strategy generated materially higher
  alpha than one using raw, unweighted rating data. → **Phase 3/4**
  (recency-decay individual rating changes, same shape as `sentiment.py`'s
  `score_messages()` exponential decay — a pattern already proven in this
  codebase for the Crowd pillar, being reused here conceptually, not
  copied verbatim).
- **Coverage breadth affects how fast new information gets priced in** —
  price adjustment to a revision is slower for thinly-covered stocks,
  faster for well-covered ones (Gleason & Lee). `num_analysts` is
  currently fetched but used only as a coverage *count*, never as a
  signal or confidence input in its own right. → **Phase 4**.

## Free data sources — what's already paid for and unused

Checked live against `yfinance`'s actual current `Ticker` surface this
session (not assumed from memory) — **every field below is already a
free dependency of this project; none require a new signup or API key.**
None of the fields marked "No" are touched by `wallstreet.py` today.

| `yfinance` property | What it returns | Used today? |
|---|---|---|
| `recommendations` | Historical monthly strongBuy/buy/hold/sell/strongSell counts | Yes — crudely, 2-point delta only |
| `recommendations_summary` | Current-snapshot version of the same | No |
| `upgrades_downgrades` | **Full individual-analyst-action history**: firm, fromGrade, toGrade, action, date | **No** |
| `analyst_price_targets` | dict: current/low/high/mean/median | Partially — mean/high/low fetched, the *spread* (dispersion) unused |
| `earnings_estimate` | numberOfAnalysts, avg/low/high, yearAgoEps, growth — by period (0q/+1q/0y/+1y) | **No** |
| `eps_trend` | current vs. 7/30/60/90-days-ago EPS estimate, by period | **No** |
| `eps_revisions` | upLast7days/upLast30days/downLast7days/downLast30days counts, by period | **No** |
| `revenue_estimate` | Same shape as `earnings_estimate`, for revenue | No |
| `growth_estimates` | stock vs. industry/sector/index growth comparison | No |
| `earnings_history` | Actual vs. estimated EPS, recent quarters — the raw material for a real Surprise signal | No |

`eps_trend` + `eps_revisions` together are close to Zacks' Agreement +
Magnitude factors, for free, zero new integration cost. `upgrades_downgrades`
gives real dated per-firm rating-change history — enough to build genuine
recency-decayed revision momentum and detect "bold" moves, replacing the
current 2-point `revision_delta_pct` proxy entirely.

**Backup/corroboration sources** (same "independent second read" role
ApeWisdom/Bluesky play for the Crowd pillar — not required, evaluate only
if Phase 4's confidence work wants real cross-source agreement, not a
duplicate read of the same underlying vendor):
- **Finnhub** — free, ~60 calls/min, no card. Recommendation trends +
  price-target consensus endpoints. Already noted as a fallback candidate
  in `PRODUCT.md`'s News Intelligence research; not yet integrated
  anywhere in this codebase.
- **Financial Modeling Prep** — free-tier Price Target Consensus
  (high/low/median/consensus) and a Stock Grades/Upgrades-Downgrades API.

**Open, unresolved as of this doc:** whether Finnhub/FMP's free-tier
analyst data is genuinely sourced independently of `yfinance`'s (likely
both aggregate from similar underlying vendors) — needs a live check
before treating agreement between them as real corroboration rather than
a duplicate read. Do not build Phase 4's cross-source term on an
unverified assumption of independence.

## Data integration map — what's safe to change, what isn't

Full trace done before writing this plan (this session, 2026-08-20).
Bottom line, mirroring `FULL_FUNDAMENTAL_RESET.md`'s equivalent section:

**Coupled — must be updated in lockstep with any category add/rename:**
- `analyst.py`'s `_fmt_wallstreet` (~line 181) — hardcodes the 3 existing
  sub-categories (`rating`, `price_target`, `revision_trend`) by key name
  into the Gemini prompt. A new/renamed sub-category is invisible to the
  AI analyst until this is updated, same pattern as `_fmt_fundamentals`.
- Any future dedicated frontend section (Phase 6) — doesn't exist yet, so
  nothing to break today, but once built it'll read the payload's
  `wallstreet` dict by key name the same way `stock_template.html`'s
  `FUND_CATEGORY_META` does for Business.

**NOT coupled — safe regardless of category changes:**
- `main.py` — only ever reads `wscore["overall"]` today (into
  `pillar_scores`), never looks inside `wscore["categories"]`. Adding a
  `payload["wallstreet"]` key (Phase 1) and new sub-categories (Phases
  2-4) is additive and touches nothing else in `main.py`'s control flow.
- `dashboard_template.html` / `sentiment_template.html` — only ever touch
  the 4 top-level pillar numbers via `PILLAR_LABELS`/`pillarDialSvg`,
  never reach into any pillar's sub-categories. Confirmed by grep this
  session: zero references to `recommendation`/`price_target`/`upside`
  anywhere in either file.
- `data/signal_history.json` / `supabase`'s `signal_history` table — one
  column, `wall_street numeric` (the blended overall score only, per
  `build_signal_snapshot` in `main.py` and `supabase/schema.sql`). Not
  touched by any phase below unless a future phase deliberately extends
  the historical record, which isn't in scope here.
- The Divergence Engine's `_WALLSTREET_LEVEL_THRESHOLDS` (55/78) in
  `main.py` — calibrated against the *overall* score's real distribution,
  not its internal composition. Re-verify live whether it still holds
  once Phase 4 reweights `overall`, but nothing here requires touching it
  before then.

**Practical implication:** Phase 1 (pure data fetching + payload
persistence) touches none of the coupled surfaces and is fully safe.
Phases 2-4 (new/reweighted sub-categories) need `_fmt_wallstreet` updated
in the same change, same discipline `FULL_FUNDAMENTAL_RESET.md` used for
`_fmt_fundamentals`. Phase 6 is the first phase that touches the
frontend at all.

## The phased plan

### Phase 1 — Data foundation ✅ DONE (2026-08-20)
Goal: fetch and verify, live, everything later phases need, before
building on top of it — no scoring changes. Same shape as Business
pillar's Phase 1.

Built:
- `wallstreet.py`: `fetch_eps_estimate_history()` — `eps_trend` +
  `eps_revisions`, by period (`0q`/`+1q`/`0y`/`+1y`), NaN-safe via a
  local `_clean()` (same pattern as `fundamentals.py`'s). Column names
  mapped explicitly by source key, not relied on case-insensitively —
  confirmed live that `eps_revisions` really does mix casing
  (`upLast7days` vs. `downLast7Days`, not a typo in yfinance's own
  output).
- `wallstreet.py`: `fetch_upgrades_downgrades()` — real, dated, per-firm
  rating-change history from `upgrades_downgrades`, newest first, capped
  to a 395-day lookback and 60 records. yfinance's own `0.0` sentinel for
  "no price target on this action" (confirmed live on an initiation row)
  is normalized to `None`, never passed through as a fabricated $0
  target; empty-string `FromGrade` (also confirmed live, on initiations)
  normalized to `None` the same way.
- `wallstreet.py`: `fetch_analyst_data()` extended with
  `target_median_price`, sourced from the dedicated
  `analyst_price_targets` endpoint (not `.info`, which never exposed
  median) — matters for Phase 4's dispersion work, since mean ≠ median
  is itself a signal that one analyst's outlier target is skewing the
  average.
- `main.py`: both new fetchers wired into `run_analyst_pipeline`, added
  before `score_wallstreet()` is called (same ordering discipline
  Business Phase 2 used) — a new `wallstreet_data[ticker]` dict (raw
  metrics + existing sub-category scores + the two new fetches) and a
  new `payload["wallstreet"]` key. No changes to `score_wallstreet()`
  itself — this phase is fetch-and-persist only.

Verified live (2026-08-20):
- **Full 30-ticker watchlist coverage check**: `eps_trend`,
  `eps_revisions`, `upgrades_downgrades`, and `analyst_price_targets` all
  came back **30/30** — including thin-coverage names (IONQ, NBIS) that
  needed a financial-sector-style carve-out for the Business pillar.
  No carve-out needed here at the data-foundation level.
- **The "stale ratings" problem from the research section is real, not
  hypothetical, on this exact watchlist**: META, IONQ, BABA, and PTON
  all showed **zero** `upgrades_downgrades` actions in the trailing 90
  days despite having hundreds of historical rows between them (META:
  413 total rows, last action 2024-09-30 — nearly 2 years stale). Direct,
  live confirmation that Phase 3's recency-decay design and Phase 4's
  recency-based confidence term are solving a real problem in this
  data, not a theoretical one.
- **Smoke test** (real function calls, not the pipeline's full daily
  run — NVDA/JPM/IONQ): all three fetchers returned real, sane data;
  the full `wallstreet_data[ticker]` shape survived `json.dumps` cleanly
  (14.2KB/10.6KB/1.3KB respectively); zero fabricated `$0.0` targets
  leaked through. **IONQ's `fetch_upgrades_downgrades()` correctly
  returned `None`** (not an empty list) — its last real action
  (2024-08-12) falls outside the 395-day lookback window, so "no data in
  the window" comes through as a genuine absence, not a fabricated
  empty-but-present state.
- `python -m py_compile` clean on `wallstreet.py` and `main.py`. Full
  end-to-end dashboard render (Gemini analyst calls included) not
  re-run this phase — same "out of scope for a pure data-fetch phase"
  reasoning `FULL_FUNDAMENTAL_RESET.md`'s Phase 4 used; worth a full
  pipeline dry run before the next daily CI run picks this up for real.

### Phase 2 — Revision Agreement & Magnitude (EPS-estimate based) ✅ DONE (2026-08-20)
Goal: a real revision signal from `eps_trend`/`eps_revisions`, replacing
the rationale (not necessarily the field — see below) behind the current
crude `revision_delta_pct` proxy — this is the single most literature-
backed addition in this whole plan (see Research foundations).

Built:
- `wallstreet.py`: `_score_revision_agreement()` — net ratio of analysts
  revising an EPS estimate up vs. down over the trailing **30 days only**
  (`(up-down)/(up+down)`), not a 7d/30d blend as originally sketched
  above — confirmed live that yfinance's `upLast7days`/`upLast30days`
  are cumulative (30d count always >= 7d count for the same period), so
  summing both would double-count the most recent week. The 7-day
  figures stay in the Phase 1 payload for Phase 4's recency/freshness
  work instead, not folded into this score. Scored per period (`0q`,
  `0y`) then averaged, same scale-then-average pattern
  `fundamentals.py`'s `growth`/`profitability` categories use. Zero
  revisions in the window returns `None`, not a fabricated 0.0
  "neutral" — silence and a genuine 50/50 split are different states.
- `wallstreet.py`: `_score_revision_magnitude()` — **scaled by the
  ticker's current price, not by the prior EPS estimate itself**, a
  real, live-discovered correction to this doc's original sketch (which
  assumed the estimate's own magnitude as the scale). Scaling by the
  prior estimate blows up for any company whose EPS sits near zero:
  confirmed live, COIN's 0y magnitude came back as **-45998.7%** and
  IONQ's as **-1643.4%**, both because the 30-days-ago base was a few
  tenths of a cent — the exact same near-zero-denominator failure
  `fundamentals.py`'s PEG calculation (Business Phase 5) already had to
  guard against. Price-relative scaling is stable regardless of how
  small the EPS estimate is, and is arguably more decision-relevant
  anyway (a $0.50 cut matters far more for a $10 stock than a $500 one).
- `score_wallstreet()`: two new optional params, `eps_estimates` and
  `price` (default `None`, existing callers unaffected) add
  `revision_agreement` and `revision_magnitude` as a 4th/5th category,
  plus new `revision_agreement_detail`/`revision_magnitude_detail`
  return fields (raw ratios/pct-of-price, parallel to
  `earnings_quality_detail`'s transparency pattern). Placeholder weights
  (0.15 each) added alongside the original three **unchanged** — same
  incremental-add discipline Business Phase 2/3 used, full reweighting
  deferred to Phase 4 as planned, not done piecemeal here.
- `main.py`: fetch order changed so `eps_estimates` is available before
  `score_wallstreet()` is called (same ordering discipline as Business
  Phase 2); `current_price` reused from the already-fetched `quotes`
  dict rather than a second lookup.
- `analyst.py`'s `_fmt_wallstreet`: fixed a hardcoded `/3 categories`
  string to derive from `len(cats)` — the exact same staleness bug
  `_fmt_fundamentals` already had to fix once for Business pillar
  Phase 2, now caught proactively instead of discovered later. Added
  two new lines surfacing the real net ratios / pct-of-price numbers to
  the Gemini prompt, not just the blended sub-scores.

Verified live (2026-08-20):
- **Breakpoints derived from the real distribution**, not guessed: ran
  both raw formulas across the full 30-ticker watchlist (0q + 0y periods,
  60 data points) before picking any breakpoint. Price-relative magnitude
  came back well-behaved (p5=-0.57%, median=0.00%, p95=+0.45%, one real
  outlier at -13.0% — confirmed against COIN's actual raw EPS numbers,
  not a units bug) — this distribution is what `_REVISION_MAGNITUDE_PTS`
  is built from.
- **Full 30-ticker watchlist: 30/30 scored with all 5 categories
  present** — better real coverage than the Business pillar's own
  Phase 4 needed a financial-sector carve-out for.
- **Real, substantive behavior change, not just new numbers alongside
  the old ones**: IONQ's overall Wall Street score moved from what the
  original 3-category scoring alone would give (rating 92.3, price
  target 97.2 — both strongly bullish) to a blended **65.7** once real
  revision data entered the mix — `revision_agreement: 5.0` (net ratio
  -1.0, i.e. every recent EPS revision across both periods was downward)
  and `revision_magnitude: 8.1` (-2.19% / -13.05% of price, a real,
  large estimate cut). This is exactly the kind of tension ("Wall Street
  says Strong Buy + 63% upside, but is quietly slashing near-term
  estimates") the whole research effort was aimed at surfacing — the
  pre-Phase-2 score was structurally blind to it.
- `_fmt_wallstreet()`'s new output confirmed readable and specific
  (spot-checked NVDA/IONQ/COIN/JPM) — real net ratios and pct-of-price
  numbers reach the Gemini prompt, not just a blended sub-score.
- `python -m py_compile` clean on `wallstreet.py`, `main.py`,
  `analyst.py`. Full end-to-end dashboard render (Gemini calls included)
  not re-run this phase — same "out of scope for a scoring-logic change
  with this level of live verification" reasoning Business pillar Phase
  4 used; worth a full pipeline dry run before the next daily CI run.

### Phase 3 — Rating Momentum from individual actions ✅ DONE (2026-08-21)
Goal: replace the 2-point `revision_delta_pct` proxy with a real,
dated, recency-decayed signal from `upgrades_downgrades`' individual
rating-change history — and weight "bold" moves higher than herding
ones, per Clement & Tse.

Built:
- `wallstreet.py`: `_GRADE_ORDINAL` — a 34-label -> 5-bucket
  (-2..+2) ordinal mapping, covering every distinct grade label
  confirmed live across the full watchlist's real `upgrades_downgrades`
  history (not just the Phase 1 lookback-capped sample — the raw table,
  178 distinct firms). A few entries are real judgment calls, documented
  inline the same way Business pillar Phase 4's sector-industry mapping
  was: "Reduce" scored mildly bearish, "Accumulate"/"Above Average"
  scored bullish, plain "Perform" scored neutral.
- **Cross-validated the mapping against yfinance's own `Action` field**
  before trusting it for anything: 2090 real up/down actions checked,
  99.2% directional agreement (17 "mismatches", 16 explained by a firm's
  own finer-grained internal ladder collapsing to the same bucket here —
  not a mapping error, a real coarseness limit of one shared scale across
  178 firms — and one genuine unexplained anomaly, noted not chased
  further at n=1/2090). **Decision made from this finding**: `Action`
  (`up`/`down`/`main`/`reit`/`init`) is used as the AUTHORITATIVE
  direction signal, never re-derived from grade comparison — the ordinal
  mapping is used only for the boldness (notch-jump-size) multiplier.
- `wallstreet.py`: `_action_signed_magnitude()` — per-action signed
  contribution: `up`/`down` use Action's direction with a notch-jump
  boldness multiplier (capped at 2.0x); `init` contributes a softer,
  0.5x-scaled signal from the initiating grade's ordinal position (a new
  analyst isn't a "change" in the Womack sense, just new information);
  `main`/`reit` contribute nothing — no rating change, no revision
  signal, consistent with this whole phase's premise.
- **Explicit, deliberate scope limit on Clement & Tse's "bold vs.
  herding" definition**: their original definition requires deviating
  from BOTH the analyst's own prior view AND the contemporaneous
  consensus. Only the first half is implemented (directly computable
  from `FromGrade`/`ToGrade`) — the second half needs point-in-time
  historical-consensus reconstruction, judged too large an undertaking
  for this phase and NOT approximated with a shortcut that could
  mislead (e.g., comparing against today's consensus for a months-old
  action would be circular). Noted here so it isn't silently forgotten
  or later assumed to be already handled.
- `wallstreet.py`: `_score_rating_momentum()` — exponential recency
  decay (half-life) composed with Bayesian shrinkage-toward-neutral for
  thin samples, same two-part SHAPE as `sentiment.py`'s
  `score_messages()`, reimplemented (not copy-pasted) for a structurally
  different input (discrete dated events, not scored messages). Returns
  `None` — not a fabricated neutral — when there's no genuine
  rating-change activity (up/down/init) in the lookback window;
  reiteration-only activity doesn't count as "silence" either, since
  `main`/`reit` actions carry no revision signal per the design above.
- `score_wallstreet()`: new optional `upgrades_downgrades` param adds
  `rating_momentum`, which **replaces** `revision_trend` in the
  category/weight dicts (not a 6th addition) — the two answered the same
  question via a crude proxy vs. a real signal, and carrying both would
  be redundant. `revision_delta_pct` itself stays in
  `fetch_analyst_data()`'s output and the Gemini prompt as supplementary
  raw context — not wrong data, just no longer the scored version of
  this idea. `rating_momentum`'s placeholder weight (0.25) matches
  `revision_trend`'s retired weight exactly, keeping the "swap it, don't
  quietly grow total weight mass" framing precise.
- `config.json`: three new tunables —
  `wallstreet_momentum_half_life_days` (60.0), `wallstreet_momentum_
  lookback_days` (270), `wallstreet_momentum_shrinkage_k` (3.0) — same
  never-hardcode discipline as everywhere else in this codebase.
- `main.py`: `run_analyst_pipeline` threads the three new config values
  through to `score_wallstreet()`, sourced at the `main()` call site the
  same way `sleep_seconds` already was.
- `analyst.py`'s `_fmt_wallstreet`: new `_fmt_rating_momentum()` line,
  and the coverage-denominator comment updated to reflect the swap (not
  just "more will follow").

Verified live (2026-08-21):
- **Breakpoints derived from the real shrunk-momentum distribution**
  across the full 30-ticker watchlist (60-day half-life / 270-day
  lookback / shrinkage_k=3.0, before picking any breakpoint): min=-0.52,
  p5=-0.07, median=+0.05, p95=+0.34, max=+0.41.
- **Shrinkage confirmed doing real, visible work, not just present in
  theory**: TEAM's one bold recent downgrade (raw net signal -1.0, thin
  support — total decayed weight 0.23) shrank to -0.07, appropriately
  discounted as weak evidence; NKE's well-corroborated 12-action
  downgrade trend (raw -0.92, total decayed weight 3.85) only shrank to
  -0.52 — a broadly-supported signal keeps its strength instead of being
  flattened the same amount.
- **Full 30-ticker watchlist: 30/30 scored, 26/30 with real
  `rating_momentum` data.** The 4 without it (META, AMZN, IONQ, PANW)
  correctly return `None`, not a fabricated neutral — META's and IONQ's
  staleness was already confirmed in Phase 1 (last real rating action
  outside the 270-day window); `overall` recalculates cleanly via the
  existing weight-sum normalization when a category is absent, no
  special-casing needed.
- **Real, substantive signal, spot-checked**: NKE's `rating_momentum`
  (9.1/100, sharply bearish) is visibly the most negative of its 5
  categories — its blended `rating` category still reads "Hold"
  (mean 2.51) and `price_target` still implies +26% upside, but the
  *dated, recent* rating-change activity has been unambiguously
  negative (12 actions, mostly downgrades). This is a real internal
  disagreement within the Wall Street pillar itself that a single
  blended consensus rating alone hides completely.
- `python -m py_compile` clean on `wallstreet.py`, `main.py`,
  `analyst.py`; `config.json` re-validated as parseable JSON after the
  edit. Full end-to-end dashboard render (Gemini calls included) not
  re-run this phase, same reasoning as Phases 1-2.

### Phase 4 — `wallstreet_confidence()` + reweighting ✅ DONE (2026-08-21)
Goal: give Wall Street the same confidence/uncertainty layer every other
pillar already has, and revisit `score_wallstreet()`'s weights against
what Phases 2-3 actually show, not the original hand-picked 0.40/0.35/0.25.

Built:
- `wallstreet.py`: `wallstreet_confidence()` — three independent signals,
  same weighted-sum SHAPE as `sentiment.py`'s `crowd_confidence()` (not a
  copy, structurally different inputs):
  1. **Coverage breadth (45%)** — `num_analysts` scaled against a
     `config.json` target (`wallstreet_confidence_target_analysts`,
     default 25.0), capped at 100, same shape as
     `crowd_confidence_target_n`.
  2. **Price-target dispersion (30%)** — `(high-low)/mean`, scored via a
     new `_DISPERSION_CONFIDENCE_PTS` breakpoint table (tight spread =
     trustworthy consensus, wide spread = fragile average, per the
     Palley/Steffen/Zhang framing in the research section). `None`
     (missing high/low/mean) scores a neutral 50, same fallback
     `crowd_confidence()` uses for single-source agreement.
  3. **Rating recency (25%)** — exponential decay on days since the most
     recent `upgrades_downgrades` action of ANY kind (reusing Phase 1's
     own "what counts as an action" precedent, not narrowed to just
     up/down/init), using the SAME half-life as `rating_momentum`'s own
     decay (`momentum_half_life_days`, reused directly, not a second
     separately-guessed constant). Zero actions in the fetch window
     scores 0, not neutral — genuine silence is real information here,
     same discipline `_score_rating_momentum` already established.
  Returns `None` only when `w` itself is missing (nothing to be
  confident or unconfident about). `wallstreet_confidence_label()` mirrors
  `crowd_confidence_label()`'s exact High/Medium/Low thresholds (≥70/≥40),
  no reason to diverge cross-pillar semantics for what those words mean.
- `score_wallstreet()`: full reweight of the (now 5) categories —
  `rating: 0.40 -> 0.15`, `price_target: 0.35 -> 0.20`,
  `revision_agreement: 0.15 -> 0.20`, `revision_magnitude: 0.15 -> 0.20`,
  `rating_momentum: 0.25 -> 0.25` (unchanged). Two things happening at
  once, both deliberate: (1) acting on the research section's central
  finding — recommendation LEVEL carries little independent predictive
  power (Womack 1996; Bradshaw's review), recommendation CHANGE is where
  the real signal lives — by demoting `rating` hardest and giving the
  three change/revision-based categories the majority of total weight
  (0.65 combined, up from an effective ~0.42 of the old total mass); (2)
  fixing a real, previously-undocumented side effect: the old weights
  summed to 1.30 (Phase 2's two 0.15 additions were never offset against
  anything), which silently diluted `rating`'s and `price_target`'s
  EFFECTIVE share (40%/35% of raw weight -> ~31%/27% of the normalized
  total) as an accident of the additive-not-breaking discipline, not a
  deliberate choice. New weights sum to exactly 1.0. `price_target` is
  trimmed but deliberately not demoted as hard as `rating` — its own
  documented structural optimism bias is Phase 5's job to actually treat,
  not something to guess an adjustment for here without that dedicated
  work.
- `main.py`: `run_analyst_pipeline` computes `wallstreet_confidence()`
  right alongside `wscore` (same call site), new `confidence_target_
  analysts` param threaded through from `config.json` the same way the
  three momentum params already were; `wallstreet_data[ticker]` gains
  `confidence` and `confidence_label` fields, unprefixed (unlike crowd's
  `crowd_confidence` naming) since they already live inside their own
  `wallstreet` payload namespace, no collision risk.
- `config.json`: one new tunable, `wallstreet_confidence_target_
  analysts` (25.0).
- `_fmt_wallstreet` in `analyst.py`: **deliberately not touched this
  phase** — confirmed against the data integration map above, which only
  requires updating it for a `categories` add/rename, and `confidence`
  isn't a category. Also matches the real precedent already set by
  `crowd_confidence`, which isn't surfaced in any AI prompt either —
  consistent, not an oversight.

Verified live (2026-08-21, full 30-ticker watchlist, real
`fetch_analyst_data`/`fetch_upgrades_downgrades`/`score_wallstreet`/
`wallstreet_confidence` calls, not a smoke sample):
- **Confidence breakpoints derived from a live run BEFORE being picked,
  not guessed**: `num_analysts` (min=13, p25=23.8, median=31.5, p90=50.7,
  max=60), price-target dispersion (min=0.215, p25=0.557, median=0.804,
  p75=1.208, p90=1.527, max=2.000 — BA tightest, PTON most fragile),
  days since most recent `upgrades_downgrades` action (28/30 tickers had
  at least one in the 395-day fetch window; median 11.6 days, max 104.2
  — BABA and PTON, both real, both >90 days stale, consistent with Phase
  1's original stale-ratings finding; META and IONQ had zero actions at
  all). `target_analysts=25.0` and the dispersion breakpoint table were
  set directly from these percentiles.
- **30/30 scored with no exceptions**, both `wscore` and `confidence`.
- **Confidence distribution is real and well-differentiated, not
  clustered**: min=36.0 (PTON), median=78.2, max=95.5 (BA). Labels: 25
  High, 3 Medium (META, NBIS, BABA), 2 Low (IONQ 38.2, PTON 36.0) — the
  two Low-confidence names are exactly the two already flagged elsewhere
  in this doc as thin-coverage/troubled (IONQ: 13 analysts, zero rating
  activity; PTON: fragile 2.0 dispersion, 104-day-stale ratings).
- **Reweighting produces a real, substantive shift, not just renumbered
  scores**: comparing old-weight vs. new-weight `overall` across all 30
  tickers, delta ranges from **-21.5 (IONQ) to +1.7 (PYPL)**, average
  -5.6 — almost universally negative, because `rating`/`price_target`
  (the two categories most exposed to sell-side's documented structural
  bullish bias) were carrying the most weight before. **IONQ is the
  clearest single example of exactly the problem Phase 4 was built to
  fix**: `rating` 92.3, `price_target` 97.2 (both near-max, thin-coverage
  optimism) vs. `revision_agreement` 5.0, `revision_magnitude` 8.1
  (analysts actively slashing near-term estimates), `rating_momentum`
  None (zero real rating-change activity) — old weights leaned on the
  two bullish-biased categories (0.75 combined) and produced 69.4; new
  weights (0.35 combined on those same two) produce 47.9, a genuinely
  different read of the same underlying disagreement. META shows the
  same pattern for a different reason (-15.2, 73.8 -> 58.6): 57 analysts
  and strong rating/target scores, but zero rating-change activity in the
  whole lookback window — confidence correctly lands at Medium (65.5),
  not High, capturing exactly this "lots of coverage, no fresh signal"
  state that a bare category-coverage count couldn't distinguish from
  genuinely fresh strong coverage (e.g. AMZN, also has `rating_momentum:
  None` but confidence 85.7/High, because its `upgrades_downgrades`
  actions — reiterations, not real rating changes — are recent, a real
  and deliberate distinction between "no real change happened" and
  "nobody's looked at this in over a year").
- `python -m py_compile` clean on `wallstreet.py`, `main.py`. Full
  end-to-end dashboard render (Gemini analyst calls included) not re-run
  this phase, same "out of scope for a scoring-logic change with this
  level of live verification already done" reasoning every prior phase
  in both reset docs has used; worth a full pipeline dry run before the
  next daily CI run picks this up for real.
- **Not re-verified this phase, flagged as a known follow-up**: the
  Divergence Engine's `_WALLSTREET_LEVEL_THRESHOLDS` (55/78) in `main.py`
  was calibrated against the OLD `overall` distribution. Given the real
  average -5.6 shift found above, it should be re-checked against the
  new distribution before the next scheduled run relies on it — noted
  here, not silently assumed to still hold.

### Phase 5 — Price-target optimism-bias treatment — NOT STARTED
Goal: stop treating `upside_pct` at face value given the documented,
structural optimism bias in sell-side price targets (see Research
foundations) — contingent on a real live check, not assumed to be
solvable the same way Business Phase 4 handled sector-relative P/E.

To investigate before building anything:
- Does a free, live source of *sector-average* target-implied-upside
  exist (the equivalent of Damodaran's sector benchmarks, which cover
  margins/ROE/P/E/growth/leverage but were not checked for an
  analyst-target-upside figure during this doc's research)? If not,
  sector-relative treatment isn't available the way it was for
  Business's P/E, and this phase needs a different shape — e.g. a fixed
  empirical haircut derived from live data (how far off were this
  watchlist's own targets historically, using `data/signal_history.json`
  once enough of it accumulates), or simply demoting `price_target`'s
  weight further in Phase 4 and documenting the bias explicitly in the
  AI prompt (`_fmt_wallstreet` already has a real precedent for this:
  `_fmt_balance_sheet_detail` telling Gemini exactly which method was
  used and why).
- Do not fabricate a sector-average-upside benchmark or assume Damodaran
  has one without checking his actual published datasets first.

### Phase 6 — Frontend surfacing — NOT STARTED
Goal: give Wall Street the same "show the work" transparency Business
got — currently the most opaque pillar on the site (see this doc's
intro). Only phase that touches the frontend.

To build:
- `main.py` / payload: by this point `payload["wallstreet"]` (Phase 1)
  already carries the raw metrics; add the Phase 2-4 sub-scores and
  `wallstreet_confidence()` output to the same dict.
- `stock_template.html`: a dedicated Wall Street detail section —
  consensus rating text + distribution, price target (mean/high/low,
  with the dispersion now visible), analyst count, and the sub-score
  breakdown — mirroring `renderFundamentalsRadar`'s pattern (a
  `WALLSTREET_CATEGORY_META`-equivalent object driving a labeled chart),
  not copying Business's exact visual, since a 5-axis radar and a
  rating/target/momentum layout may not be the same best shape — worth a
  real design decision at that point, not an assumed copy.
- `analyst.py`'s `_fmt_wallstreet`: update to reference the new
  sub-categories, same lockstep discipline as every prior phase.

### Phase 7 — Validation, backtest, cross-source corroboration — NOT STARTED
Goal: same status and same reasoning as Business pillar's own Phase 6 —
best revisited once `data/signal_history.json` has accumulated enough
real days to backtest the (by then 5) sub-category weights against
actual subsequent price behavior, and to properly evaluate whether
Finnhub/FMP corroboration (see Free data sources above) adds real
independent signal or just duplicates `yfinance`'s own source. Not
actionable yet — noted here so it isn't forgotten, not because it's
next.

## Status snapshot

| Phase | What | Status |
|---|---|---|
| 1 | Data foundation (eps_trend/eps_revisions/upgrades_downgrades fetch + payload persistence) | ✅ Done, verified live 2026-08-20 |
| 2 | Revision Agreement & Magnitude (EPS-estimate based, Zacks-inspired) | ✅ Done, verified live 2026-08-20 |
| 3 | Rating Momentum from individual dated actions (recency-decayed, boldness-weighted) | ✅ Done, verified live 2026-08-21 |
| 4 | `wallstreet_confidence()` + reweighting | ✅ Done, verified live 2026-08-21 |
| 5 | Price-target optimism-bias treatment | Not started |
| 6 | Frontend surfacing (dedicated Wall Street detail section) | Not started |
| 7 | Validation, backtest, cross-source corroboration | Not started |

**Files touched so far:** `wallstreet.py`, `main.py`, `analyst.py`,
`config.json`.

**Next step:** Phase 5 (price-target optimism-bias treatment) — starts
with an investigation, not a build: does a free, live source of
sector-average target-implied-upside exist? If not, this phase needs a
different shape (a fixed empirical haircut derived from live data, or
simply documenting the bias explicitly in the AI prompt) — see that
phase's section above for what to check before writing any code. Two
smaller items also worth picking up whenever convenient, not blocking:
(1) `main.py`'s `_WALLSTREET_LEVEL_THRESHOLDS` (55/78) needs re-
verification against the new reweighted `overall` distribution — Phase
4's live check found a real average -5.6 shift, so the old threshold
calibration shouldn't be assumed to still hold; (2) `README.md`'s "How
it works under the hood" and `PRODUCT.md`'s Phase 2 section both still
describe the pillar's old 3-category shape (pre-Phase-2/3) — a docs-only
staleness, not a code issue, worth a pass at some point.
