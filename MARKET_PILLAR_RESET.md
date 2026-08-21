# Market Pillar Reset — momentum/positioning rebuild

**Read this first if you have no memory of this specific work stream** (a
new session, lost history, whatever). Same spirit as `CLAUDE.md` and its
siblings `FULL_FUNDAMENTAL_RESET.md` (Business pillar, 5/6 phases done)
and `WALL_STREET_PILLAR_RESET.md` (Wall Street pillar, 4/7 phases done —
read that one too, this file assumes you know its pattern and reuses
several of its conventions directly): a map of what was decided, why,
what's built, and what's left — not a replacement for the code itself.
If this file and the code disagree, trust the code and fix this file.
**Update the one-line status below every phase.**

**One-line status (update every phase):** Phases 1-6 done and verified
live (2026-08-21) — raw data persisted (Phase 1); short interest (Phase
2) and beta/low-beta tilt (Phase 3) added as real categories from
previously-fetched-and-discarded fields; idiosyncratic (market-model-
residual) volatility (Phase 4) replaces total volatility as `stability`'s
input, via a real regression against a shared S&P 500 benchmark series;
`market_confidence()` + a full reweight (Phase 5); a dedicated Market
Positioning radar chart + glance strip on the Stock Intelligence page,
verified live in-browser with real data (Phase 6). Phase 7 (validation/
backtest) remains genuinely not actionable — needs weeks of accumulated
`signal_history.json`, same structural blocker both sibling pillars hit
at their own final phase.

## Why this exists

A review of `market.py` (2026-08-21, this session) found the Market
pillar in a state distinct from where Business and Wall Street started:
its 3 existing categories are actually well-grounded in real literature
(see Research foundations below — this is genuinely reassuring, not
every pillar needed a "the old approach might be backwards" finding the
way Wall Street's rating-level weighting did). The real gaps are
narrower and more mechanical:

1. **Two real, literature-backed signals are fetched, then thrown away.**
   `fetch_market_data()` fetches `beta`, `short_percent_of_float`, and
   `short_ratio` from `yfinance`'s `.info` — confirmed by reading
   `score_market()` directly: none of the three appears anywhere in the
   scoring function, `_fmt_market()` (the AI prompt), or `main.py`'s
   payload. This is the exact same "computed and discarded" pattern
   `WALL_STREET_PILLAR_RESET.md`'s Finding #1 described, just for two
   metrics rather than the whole pillar.
2. **Nothing reaches the frontend except one dial and one AI sentence** —
   same finding as Wall Street pre-Phase-6, confirmed the same way:
   grepped every `*_template.html` for anything Market-pillar-specific
   (`pct_from_52w`, `daily_volatility`, a `MARKET_CATEGORY_META`-style
   object). The only match was `renderMarketsStrip()` in
   `dashboard_template.html`, which is the unrelated macro-instruments
   strip (indices/crypto/commodities from `market_data.py` — a
   confusingly similarly-named but completely different file) — zero
   real Market-*pillar* UI exists anywhere.
3. **Raw data + sub-category breakdown never reach the payload.**
   Confirmed by reading `main()`'s final `payload` dict directly: it has
   `"fundamentals"` and `"wallstreet"` keys carrying each pillar's raw
   metrics, but no `"market"` key — only `pillar_scores["market"]`, the
   single blended number, survives. Same Phase-1-shaped gap as the other
   two pillars had, not yet closed here.
4. **No confidence/uncertainty layer**, same starting point Crowd, Wall
   Street, and Business all had before their own confidence work. A
   fresh IPO with a 52-week high but only 3 months of real trading
   history and a stock with a decade of stable trading currently look
   identical here — both just report `coverage: 3/3`.
5. **One real construct-precision nuance, not a bug**: `stability`
   scores TOTAL realized volatility (plain stdev of daily returns), but
   the specific academic result validating "calmer = better" (Ang,
   Hodrick, Xing & Zhang 2006 — see below) is about IDIOSYNCRATIC
   volatility (the stock-specific component left over after removing
   market-wide/beta-driven moves), not total volatility. The two are
   correlated but not identical — a high-beta stock in a volatile market
   week can show high total volatility while its idiosyncratic
   volatility (relative to how much the market itself moved) is
   unremarkable. Not urgent to fix (total volatility is still a
   reasonable, simpler, defensible proxy — this is a refinement
   opportunity flagged honestly, not a "the current score is wrong"
   finding).

None of this means the current implementation is wrong to have shipped.
Unlike pre-rebuild `fundamentals.py` or `wallstreet.py`, this pillar's
core methodology already points the right direction on all three
existing categories — the gap here is closer to "good bones, unused
data, and no visibility," not "the weighting is backwards." This doc is
the plan to close that gap the same deliberate, phased, live-verified
way the other two pillars' rebuilds did.

## Research foundations — what a real quant/practitioner would use

Every idea below maps to a specific phase further down. Sources are
real, checked live via web search this session (2026-08-21), not from
training-data memory — see the chat transcript for full citations if
this doc's summary needs re-verifying. Two are direct validations of
what's already built (rare and worth stating plainly, not just hunting
for problems); the rest are real gaps.

- **The 52-week-high effect is real, robust, and matches `extension`'s
  existing direction exactly.** George & Hwang (2004, *Journal of
  Finance*): nearness to a stock's 52-week high is a strong, independent
  predictor of future returns — it actually dominates and subsumes the
  predictive power of plain trailing returns for classic momentum, is
  robust in 18 of 20 major international markets tested, and — notably —
  does NOT reverse in the long run the way plain momentum profits
  partially do. Behavioral mechanism: an anchor-and-adjust bias, where
  investors are reluctant to bid a price past its recent high/low even
  when new information warrants it. **`extension`'s current framing
  (closer to 52-week high = higher score) is already the literature-
  favored direction — this is a validation, not a fix.**
- **Momentum is real over 3-12 month horizons, but has two important
  boundary conditions `trend`'s current framing should respect.**
  Jegadeesh & Titman (1993): past winners over a 3-12 month formation
  period continue to outperform past losers over the following 3-12
  months — this is the single most-replicated finding in this whole
  research pass. Two caveats from the same literature, both real: (1)
  it is standard practice to SKIP the most recent ~1 month between
  formation and holding periods specifically because a separate,
  well-documented SHORT-TERM REVERSAL effect (Jegadeesh, 1990) runs the
  opposite direction at the ~1-month horizon; (2) De Bondt & Thaler
  (1985) found the opposite pattern again at 3-5 YEAR horizons (past
  losers outperform past winners — long-term reversal). Distance from a
  50-day/200-day moving average is a reasonable, simpler proxy for
  "where is price relative to its own medium-term trend" rather than the
  exact academically-tested construct (a clean trailing formation-period
  return) — both approximately land inside the literature-favored
  3-12-month window (50 trading days ≈ ~2.5 months, 200 ≈ ~9-10 months),
  which is reassuring, but worth naming as an approximation, not an
  identical replication. → informs **Phase 5** reweighting/validation,
  not an immediate rebuild — the current framing isn't backwards, just
  worth keeping this boundary-condition context in mind.
- **Moving-average trading rules have real historical support, with an
  honest, load-bearing caveat.** Brock, Lakonishok & LeBaron (1992,
  *Journal of Finance*) — the foundational study here — found real,
  statistically robust predictive power in simple moving-average rules
  across 90 years of Dow Jones data (1897-1986), surviving tests against
  four different null models (random walk, AR(1), GARCH-M, EGARCH); buy
  signals outperformed sell signals and were followed by lower
  volatility. **The important caveat, found in the same research pass,
  not omitted**: subsequent studies found this specific edge has
  measurably diminished in the post-1986 period across multiple
  developed markets, consistent with markets "adapting" as a technique
  becomes widely known and traded on. Read together with George &
  Hwang's finding that MA-adjacent signals still have real predictive
  content today, the honest takeaway is: moving-average-based signals
  are a real, legitimate INPUT among several, not a standalone strong
  edge on their own — which is exactly how `market.py` already treats
  `trend` (one of three roughly-equal-weighted categories, not the
  entire score). Another validation of the existing shape, with a
  caveat worth documenting rather than ignoring.
- **Idiosyncratic volatility, not total volatility, is what the
  literature actually validates for "calmer = more trustworthy."** Ang,
  Hodrick, Xing & Zhang (2006, *Journal of Finance*) — a major, widely-
  replicated anomaly: stocks with high IDIOSYNCRATIC return volatility
  (the firm-specific component left after removing market-wide/beta-
  driven moves via a market-model regression) show LOW subsequent
  returns — the opposite of naive risk-return intuition, and robust
  internationally across every G7 country tested. `stability`'s current
  input (`daily_volatility_pct`, plain stdev of the ticker's own daily
  returns) is TOTAL volatility, which conflates market-wide moves with
  stock-specific ones — a real, fixable construct-precision gap, not
  just a nuance to note. → **Phase 4** (needs a benchmark series to
  regress against — see Free data sources below for what's already
  fetched elsewhere in this codebase).
- **Short interest is a real, published predictor of future
  underperformance — and the two fields needed are already fetched and
  already unused.** Asquith, Pathak & Ritter (2005, *Journal of
  Financial Economics*, by way of an earlier NBER working paper):
  short-sale-constrained stocks (high short interest relative to
  available float) underperform by a real, economically meaningful
  margin (215 bps/month equal-weighted in their sample), and the
  negative short-interest/future-return relationship is roughly twice as
  strong on news days and four times as strong on negative-news days —
  a real, corroborated signal, not a folk belief. `short_percent_of_float`
  and `short_ratio` are both already fields on `fetch_market_data()`'s
  return dict, fetched every run, currently unused anywhere. →
  **Phase 2**.
- **Low-beta stocks earn higher risk-adjusted returns than high-beta
  ones — the opposite of naive CAPM intuition.** Frazzini & Pedersen
  (2014, *Journal of Financial Economics*): the "Betting Against Beta"
  factor (long low-beta, short high-beta) delivered a Sharpe ratio of
  0.78 over 1926-2012 — roughly double the classic value factor's and
  40% higher than momentum's over the same period, in one of the more
  striking risk-adjusted comparisons in this whole research pass. Their
  proposed mechanism is leverage-constrained investors overweighting
  risky (high-beta) assets instead of using leverage on the market
  portfolio, bidding high-beta stocks to a premium and low-beta stocks
  to a discount. Real nuance worth carrying into implementation: BAB is
  a risk-*adjusted*-return (alpha) finding from a portfolio-construction
  context, not simply "low beta always beats high beta in raw terms" —
  the honest translation into a single-stock 0-100 score is a modest
  tilt toward lower beta, not a dominant category on its own. `beta` is
  already fetched, currently unused. → **Phase 3**.

## Free data sources — what's already paid for and unused

Checked live against this project's actual current dependencies this
session (not assumed from memory) — **every field below is already a
free dependency of this project; none require a new signup or API key.**

| Source | What it gives | Used today in `market.py`? |
|---|---|---|
| `yfinance` `.info` `beta` | 5yr-monthly-vs-S&P-500 beta, Yahoo's standard methodology | Fetched, **never scored** |
| `yfinance` `.info` `shortPercentOfFloat` / `shortRatio` | Short-interest coverage, days-to-cover | Fetched, **never scored** |
| `market_data.py`'s `^GSPC` (S&P 500) series | Already fetched elsewhere in the pipeline for the macro-instruments strip | **Not reused here** — Phase 4's idiosyncratic-volatility work needs a benchmark return series to regress against, and this is already being pulled by a sibling module in the same daily run; worth checking whether it's fetched at a point in the pipeline `run_analyst_pipeline` can reach, or whether it needs its own lighter fetch, before assuming reuse is free (same "verify before assuming" discipline as everywhere else in this project). |
| `yfinance` `.info` `regularMarketVolume` / `averageVolume` (10-day, 3-month) | Real volume-vs-average, a distinct attention/liquidity signal from ApeWisdom's mention-based volume | **Not fetched or used at all** — noted as a real, cheap possible future addition, not scoped into any phase below yet. |

## Data integration map — what's safe to change, what isn't

Trace done before writing this plan (this session, 2026-08-21). Bottom
line, mirroring both sibling docs' equivalent sections:

**Coupled — must be updated in lockstep with any category add/rename:**
- `analyst.py`'s `_fmt_market` (~line 225) — hardcodes the 3 existing
  sub-categories' raw metrics into the Gemini prompt by field name, plus
  a hardcoded `"/3 categories"` string (same staleness bug
  `_fmt_fundamentals` and `_fmt_wallstreet` both already had to fix once
  — worth fixing proactively in Phase 1 rather than waiting to discover
  it again).
- Any future dedicated frontend section (Phase 6) — doesn't exist yet,
  so nothing to break today.

**NOT coupled — safe regardless of category changes:**
- `main.py` — only ever reads `mscore["overall"]` today (into
  `pillar_scores`), never looks inside `mscore["categories"]`. Adding a
  `payload["market"]` key (Phase 1) and new sub-categories (Phases 2-4)
  is additive and touches nothing else in `main.py`'s control flow.
- `dashboard_template.html` / `sentiment_template.html` — only ever
  touch the 4 top-level pillar numbers, never reach into any pillar's
  sub-categories. Confirmed by the same grep that found finding #2
  above.
- `data/signal_history.json` / `supabase`'s `signal_history` table — one
  column, `market numeric` (the blended overall score only). Not touched
  by any phase below.
- The Divergence Engine's `_DEFAULT_LEVEL_THRESHOLDS` (35/65) in
  `main.py` — Market pillar uses the shared default threshold, not a
  dedicated one like Wall Street's 55/78. Worth re-verifying it still
  holds if Phase 5's reweighting meaningfully shifts the `overall`
  distribution, same "don't assume, re-check" note Wall Street Phase 4
  left for its own threshold.

**Practical implication:** Phase 1 (pure data persistence) touches none
of the coupled surfaces and is fully safe. Phases 2-4 (new sub-
categories) need `_fmt_market` updated in the same change, same
discipline both sibling docs used. Phase 6 is the first phase that
touches the frontend at all.

## The phased plan

### Phase 1 — Data foundation ✅ DONE (2026-08-21)
Goal: persist what's already computed instead of discarding it — no
scoring changes. Same shape as both sibling pillars' own Phase 1s.

Built:
- `main.py`: new `market_data = {}` dict in `run_analyst_pipeline`,
  populated alongside the existing `m`/`mscore` computation (raw metrics
  dict + `categories` + `coverage` + `overall`, same shape as
  `wallstreet_data`); threaded through `run_analyst_pipeline`'s return
  tuple and `main()`'s call site; added to the final `payload` as
  `"market"`.
- `analyst.py`'s `_fmt_market`: fixed the hardcoded `/3 categories`
  string to derive from `len(cats)`, proactively — the same bug both
  sibling pillars' `_fmt_*` functions already had to fix once each, now
  caught before it went stale rather than discovered later.
- `score_market()` itself untouched this phase — pure fetch-and-persist,
  same discipline both sibling docs' own Phase 1s used.

Verified live (2026-08-21, full 30-ticker watchlist, real
`fetch_market_data`/`score_market` calls):
- **`beta`, `short_percent_of_float`, and `short_ratio` — the exact
  three fields flagged in this doc's "Why this exists" as fetched-and-
  discarded — all came back 30/30**, better real coverage than this doc
  assumed going in (the original review only confirmed they were fetched
  and unused, not that they were universally populated). Real spread:
  beta 0.17 (XOM) to 3.49 (CVNA) — confirms the doc's Phase 3 sketch's
  suspicion that this flagship, growth-tilted watchlist skews toward
  higher beta, worth keeping in mind when Phase 3 picks real breakpoints
  rather than assuming beta ≈ 1.0 is "typical" for this specific set.
  `short_percent_of_float` spread: 0.01% (BA) to 27.6% (NBIS) — a real,
  wide range with genuine standout names, good raw material for Phase 2.
- `python -m py_compile` clean on `main.py`, `analyst.py`, `market.py`.
  Full end-to-end dashboard render (Gemini analyst calls included) not
  re-run this phase, same "out of scope for a pure data-fetch phase"
  reasoning every prior Phase 1 in both sibling docs used.

### Phase 2 — Short interest signal ✅ DONE (2026-08-21)
Goal: a real `short_interest` category from Asquith/Pathak/Ritter's
finding, using fields already fetched and currently discarded.

Built:
- `market.py`: `_score_short_interest()` scores `short_percent_of_float`
  only — the literature's own primary framing (short interest AS A SHARE
  OF FLOAT is the constraint measure). `short_ratio` deliberately stays
  supplementary raw context, not folded into the score — resolving the
  design question this doc's own review flagged: checked live whether
  the two fields move together enough to blend (they don't — e.g. SBUX
  showed 3.8% of float but a short_ratio of 5.1, while MU showed a
  similar 2.7% of float but a short_ratio of only 0.6 — same ballpark
  percentage, very different days-to-cover, confirming they answer
  different questions and shouldn't be conflated into one number).
- `_SHORT_INTEREST_PTS`: breakpoints derived from the real Phase 1
  live-verified distribution (min=0.01%, p25=1.81%, median=2.74%,
  p75=9.91%, p90=13.46%, max=27.6%) — higher % scores lower.
- `score_market()`: new `short_interest` category, placeholder weight
  0.15, existing three categories' weights unchanged this phase — same
  incremental-add-then-reweight-later discipline Wall Street pillar's
  own Phase 2/3 used.

Verified live (2026-08-21, full 30-ticker watchlist): **30/30 scored**,
real spread across the score range (RDDT and NBIS — both real, high-
short-interest names — scored 19.6 and 5.0 respectively; BA and JPM —
both very low short interest — scored 90.0 and 83.2).

### Phase 3 — Beta / low-beta tilt ✅ DONE (2026-08-21)
Goal: a modest, real signal from Frazzini & Pedersen's betting-against-
beta finding, using `beta` (already fetched, currently discarded).

Built:
- `market.py`: `_score_beta()` + `_BETA_PTS`, a deliberately gentle
  curve (observed score range in the live check below: 12-70, narrower
  than the other categories' full 5-95 spans) centered on the TRUE CAPM
  market beta of 1.0, not this watchlist's own median — confirmed live
  this flagship, growth-tilted watchlist's median beta is 1.27, well
  above 1.0, so most flagship names scoring modestly below neutral here
  is an honest reflection of this basket's own structural tilt, not a
  bug (documented in the code, not silently recentered away, same
  "document it, don't force a comparable distribution" precedent Wall
  Street's README already set for sell-side ratings clustering bullish).
- `score_market()`: new `beta_tilt` category, placeholder weight 0.10 —
  the smallest of the five, matching this phase's own honest translation
  of a portfolio-level alpha finding into a modest single-stock tilt,
  not a dominant signal.

Verified live (2026-08-21, full 30-ticker watchlist): **30/30 scored**.
Real spread confirms the design intent: XOM (beta 0.17, lowest) scored
70 (this category's ceiling), CVNA (beta 3.49, highest) scored 12.1 —
directionally correct and appropriately bounded, not swinging the full
0-100 range the way `extension` does.

### Phase 4 — Idiosyncratic (not total) volatility ✅ DONE (2026-08-21)
Goal: close the construct-precision gap in Research foundations —
regress each ticker's daily returns against a benchmark (S&P 500) and
score the RESIDUAL (idiosyncratic) volatility, not total volatility,
matching what Ang/Hodrick/Xing/Zhang actually validated.

Built:
- `main.py`: one shared `^GSPC` benchmark series fetched ONCE per run
  (via the same `fetch_quotes()` already used for every ticker's own
  price history, same `chart_period`), not a per-ticker fetch — resolves
  this doc's own flagged uncertainty about whether `market_data.py`'s
  series was reusable; the answer was "fetch it fresh with the same
  function, once" rather than reaching into a sibling module's internal
  state.
- `market.py`: `_idiosyncratic_volatility()` — a single-index market-
  model regression (Sharpe's original framing, the same free/legitimate
  approximation Ang/Hodrick/Xing/Zhang's own robustness checks include).
  Aligns the ticker's and benchmark's price histories by DATE first (not
  index), computes local beta via `statistics.covariance`/`variance`
  (stdlib, Python 3.10+, already the project's runtime), then scores the
  regression RESIDUALS' stdev. Requires 10+ overlapping return pairs;
  returns `None` (not a fabricated value) otherwise.
- `score_market()`: `stability` now scores off
  `idiosyncratic_volatility_pct` when computable, falling back to the
  original `daily_volatility_pct` (total volatility) otherwise — same
  key name, same fallback-on-missing-data pattern Business pillar's
  Altman Z''/legacy-blend fallback for `balance_sheet` already
  established. `daily_volatility_pct` itself stays in the payload as
  supplementary raw context, not removed.

Verified live (2026-08-21, full 30-ticker watchlist, real regression
against a real 60-point `^GSPC` series): **30/30 computed** —
`idiosyncratic_volatility_pct` was never silently `None`. **Real,
meaningful divergence from total volatility, not just noise**: average
absolute difference 0.35 percentage points, max 1.08 — e.g. NVDA's total
volatility (2.50%) drops to 1.89% once market-wide moves are stripped
out (a real, decision-relevant gap — NVDA's own price swings are
noticeably calmer than its total volatility alone suggested, once you
account for how much the broader market itself moved those same days);
SOFI similarly drops from 3.57% to 2.49%. This is exactly the
construct-precision improvement this phase set out to make, confirmed
live rather than assumed from the math alone.

### Phase 5 — `market_confidence()` + reweighting ✅ DONE (2026-08-21)
Goal: same shape as both sibling pillars' own confidence phases — a real
0-100 trust measure, plus a reweighting pass across all 5 categories
using live evidence from Phases 2-4's actual computed distributions.

Built:
- `market.py`: `market_confidence()` — three signals: volatility sample
  size (35%, `volatility_sample_size` scaled against a live-derived
  target of 40), extension/trend agreement (40% — the single most real,
  currently-discriminating signal found in this pillar's own live data;
  `100 - abs(extension - trend)`), and category completeness (25%,
  `coverage`/total categories). `market_confidence_label()` mirrors the
  other two pillars' exact High/Medium/Low thresholds.
- `score_market()`: full reweight — `extension: 0.40 -> 0.35`,
  `trend: 0.35 -> 0.20`, `stability: 0.25 -> 0.20`, `short_interest`/
  `beta_tilt` unchanged at 0.15/0.10. Sums to exactly 1.0. Demotes
  `trend` hardest (reflecting the moving-average-edge-decay caveat from
  research), trims `stability` modestly to make room while keeping it
  substantial (a major, still-robust anomaly), keeps `extension` the
  largest single weight (the strongest, most robust single effect
  found in this whole research pass).
- `main.py`: `market_confidence()` computed alongside `mscore` (same
  call site), new `market_confidence_target_sample` config param
  threaded through; `market_data[ticker]` gains `confidence`/
  `confidence_label`.
- `config.json`: new tunable, `market_confidence_target_sample` (40.0).

Verified live (2026-08-21, full 30-ticker watchlist): **30/30 scored**.
**One honest, real finding worth stating plainly, not engineered
around**: confidence clustered entirely in the High band (30/30, range
82.6-99.5) — a genuinely different result from Wall Street's own
confidence spread (which ranged Low-to-High because analyst coverage
and rating recency genuinely vary a lot across that watchlist). This
flagship, mature, large/mid-cap set has near-uniform `volatility_sample_
size` (61-62 for every ticker, since `chart_history_period` fetches the
same 3-month window for everyone) and near-universal 5/5 category
coverage — there's genuinely less "thin data" variance in this pillar's
inputs on THIS specific watchlist than the other two pillars found on
theirs. The one real discriminator (extension/trend agreement) still
produced meaningful spread underneath the surface — COIN (extension 7.5
vs. trend 51.1, real internal tension) scored the lowest confidence at
82.6, still High but visibly lower than TSLA/META's 99.3/99.5 (both
near-perfect agreement) — the signal is working, it just doesn't happen
to push anyone below the High threshold on this particular set. Not
adjusted to force artificial spread — same "document it, don't force a
comparable distribution" precedent as Wall Street's own rating-
clustering finding; this term would show real Low/Medium confidence for
a genuinely thin-data ticker (a recent IPO, a data gap) outside today's
watchlist.
- **Reweighting produces a real but much smaller shift than Wall
  Street's own reweight**, consistent with this doc's own "Why this
  exists" finding that Market's original weights weren't nearly as
  backwards as Wall Street's: delta range **-3.7 (TEAM) to +1.6 (BA)**,
  average -0.7 — an honest, expected contrast, not an inconsistency
  between the two pillars' rebuilds.
- `python -m py_compile` clean on `main.py`, `market.py`.

### Phase 6 — Frontend surfacing ✅ DONE (2026-08-21)
Goal: give Market the same "show the work" transparency Business
already has. Currently the most invisible pillar on the site — same
finding as pre-Phase-6 Wall Street, still true there (not yet built for
that pillar either).

Built:
- `stock_template.html`: a new "Market Positioning" card, same position
  in the page flow as "Business Fundamentals" — a glance strip
  (`renderMarketGlanceStrip`: price vs. 52-week high, vs. 200-day
  average, beta, short % of float) plus a 5-axis radar chart
  (`renderMarketRadar`, `MARKET_CATEGORY_META`) with a hoverable legend,
  same visual language as `renderFundamentalsRadar`'s existing radar —
  a deliberately SEPARATE function (not a shared abstraction) with its
  own container/tooltip element ids (`market-visual`/`market-tooltip`
  vs. `fund-visual`/`fund-tooltip`) so the two charts can coexist on the
  same page without ID collisions, and so a future change to one
  pillar's chart can't silently affect the other's. Also surfaces
  `market_confidence()`'s label + score as an extra legend row.
- `initPage()`: reads `(DATA.market || {})[sym]` (the payload key Phase
  1 added) the same way `fundamentals` is already read, calls both new
  render functions right after the existing Business ones.

Verified live in-browser (2026-08-21) — the only phase in this whole
rebuild (either pillar) requiring this, per the project's own UI-
verification discipline: extracted the real payload already embedded in
the committed `docs/stock.html`, injected freshly-computed real Market
pillar data (via this session's actual `fetch_market_data`/
`score_market`/`market_confidence` calls, not synthetic placeholder
numbers) for 5 tickers spanning different real profiles (NVDA — high
confidence/strong scores; COIN — the real extension/trend disagreement
case; XOM — this pillar's highest live overall; IONQ and PTON — weak
scores across most categories), re-rendered `stock_template.html`
locally, served it via the repo's existing `docs-static` launch config,
and opened it in-browser:
- **NVDA**: radar rendered with exactly 5 dots and 6 legend rows (5
  categories + the confidence badge), values matched the live-computed
  categories exactly (Extension 71, Trend 62, Stability 57, Short
  Interest 81, Beta 28), correct color-coding per each value's real
  threshold (green ≥65, amber 41-64, red ≤40), confidence badge read
  "High (96)" — matching the real computed number, not a placeholder.
  Glance strip showed real values (-8.3% vs. 52-week high, +11.1% vs.
  200-day average, beta 2.21, 1.3% short of float).
  Hover interaction confirmed working: hovering the Beta dot showed
  tooltip text "Beta: 28" and correctly highlighted exactly 3 matching
  elements (dot + hit-target + legend row).
- **COIN**: legend values matched its own live-computed categories
  exactly (8/51/18/28/14, confidence "High (83)") — confirms the page
  isn't just correctly rendering one hardcoded example.
- **Zero console errors** on either ticker.
- **No regression to the existing Business Fundamentals radar**:
  confirmed its dot count (7) and its own `fund-tooltip` element were
  both unaffected, and the two radars' tooltip ids are genuinely
  distinct (`fund-tooltip` vs. `market-tooltip`) — the deliberate
  separate-function choice above did what it was meant to.
- `docs/stock.html` was git-clean before this check and reverted via
  `git checkout` immediately after — same "render locally, not
  committed, reverted after" precedent `FULL_FUNDAMENTAL_RESET.md`'s
  Phase 2/3 used, confirmed clean again afterward.

### Phase 7 — Validation, backtest — NOT STARTED, NOT ACTIONABLE YET
Same status and reasoning as both sibling pillars' own final phases —
best revisited once `data/signal_history.json` has accumulated enough
real days to backtest the (now 5) category weights against actual
subsequent price behavior. Genuinely blocked on data volume, not effort
— noted here so it isn't forgotten, not attempted or faked as done.

## Status snapshot

| Phase | What | Status |
|---|---|---|
| 1 | Data foundation (persist raw metrics + sub-scores to payload) | ✅ Done, verified live 2026-08-21 |
| 2 | Short interest signal (Asquith/Pathak/Ritter) | ✅ Done, verified live 2026-08-21 |
| 3 | Beta / low-beta tilt (Frazzini & Pedersen) | ✅ Done, verified live 2026-08-21 |
| 4 | Idiosyncratic (not total) volatility | ✅ Done, verified live 2026-08-21 |
| 5 | `market_confidence()` + reweighting | ✅ Done, verified live 2026-08-21 |
| 6 | Frontend surfacing | ✅ Done, verified live in-browser 2026-08-21 |
| 7 | Validation, backtest | Not started — blocked on data volume |

**Files touched:** `main.py`, `analyst.py`, `market.py`, `config.json`,
`stock_template.html`.

**Next step:** none actionable right now — Phase 7 is the only
remaining phase, and it's genuinely gated on `data/signal_history.json`
accumulating enough real days to backtest against, not on more building.
Revisit once that history has meaningfully grown, same as both sibling
pillars' own final phases.
