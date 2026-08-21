# Overall Score Reset — building a real composite from the four pillars

Written 2026-08-21, in response to a direct ask: Undertow shows one
"overall score" per flagship ticker today, and it's going to be tracked
against real forward stock movement starting with Phase 4's track-record
work (`PRODUCT.md`). Before that tracking starts, the score being tracked
has to actually be a defensible, reproducible function of real data — not
what it is today. This doc is the research-grounded methodology and the
concrete plan to fix it, in the same Research-foundations-then-phases
shape as `FULL_FUNDAMENTAL_RESET.md` / `WALL_STREET_PILLAR_RESET.md` /
`MARKET_PILLAR_RESET.md`.

## The actual gap (confirmed by reading the code, not assumed)

`stock_template.html` renders `result.overall_score` — that value comes
straight from `analyst.py`'s Gemini call (`RESPONSE_SCHEMA.overall_score`,
"0-100, overall investment-worthiness read", `temperature: 0.4`). It is
**not** a function of `pillar_scores` (`crowd`/`wall_street`/`business`/
`market`, computed independently in `main.py`'s `run_analyst_pipeline`).
The LLM reads all four pillars as context and forms its own free-form
judgment — genuinely useful analysis, but:

1. **Not reproducible.** Same inputs, different run, can produce a
   different number (temperature 0.4, sampled). A backtest needs a
   number that's a deterministic function of the data, or "why did the
   score move" is unanswerable — was it the data, or just resampling?
2. **Not mathematically tied to the four pillars at all.** `pillar_scores`
   is computed and stored (feeds the Divergence Engine and the four
   radial dials) but never combined into anything. There is currently no
   code path that takes `{crowd, wall_street, business, market}` and
   produces a number from them.
3. **Not comparable across tickers/days in a way that supports backtest
   attribution.** You can't decompose "why did NVDA's score change 6
   points since yesterday" into "+4 from Business, −2 from Market" the
   way Phase 4's "why did the score change" feature (`PRODUCT.md`) needs,
   because the number isn't built from parts in the first place.

This doc fixes exactly that: a real `composite_score`, deterministic,
built from the four already-well-designed pillar scores, that can
actually be backtested and decomposed.

## Research foundations

Six literatures are directly relevant, and they don't all point the same
direction — reconciling them is most of the actual design work here.

**1. Index-provider composite methodology (MSCI, S&P).** MSCI's Quality/
Momentum index methodologies compute a Z-score for each underlying metric
(winsorized at ±3 to limit outlier influence), then combine the Z-scores
into a composite — never a raw blend of differently-scaled numbers.
[MSCI Quality Indexes Methodology](https://www.msci.com/eqb/methodology/meth_docs/MSCI_Quality_Indexes_Meth_June2017.pdf),
[MSCI Momentum Indexes Methodology](https://www.msci.com/eqb/methodology/meth_docs/MSCI_Momentum_Indexes_Methodology_Aug2021.pdf),
[S&P: Exploring Techniques in Multi-Factor Index Construction](https://www.spglobal.com/spdji/en/documents/research/research-exploring-techniques-in-multi-factor-index-construction.pdf).
Undertow's four pillars are already internally well-scaled (0-100,
piecewise-linear against literature-derived breakpoints, sector-relative
where it matters — see `fundamentals.py`'s Damodaran benchmarking), so
this doc does **not** propose re-standardizing pillar scores as Z-scores
against the 30-ticker watchlist's own distribution — that cross-section
is too small to give a stable mean/stdev (some industries have exactly
one name on the list), and it would throw away the absolute-level
calibration (e.g. "extension near 100 = near the 52-week high") that the
Divergence Engine's fixed thresholds (`_DEFAULT_LEVEL_THRESHOLDS`,
`_WALLSTREET_LEVEL_THRESHOLDS`) already depend on. What *is* adopted from
this literature: combine already-scaled scores via an explicit weighted
sum, not an ad hoc blend, and treat outliers/missing data explicitly
rather than silently.

**2. Meta-analysis / inverse-variance weighting.** The statistically
optimal way to combine several *independent* estimates of the same
underlying quantity, each with different confidence, is to weight each
one in proportion to its precision (inverse of its variance) — this is
literally the standard method for pooling results across independent
studies. [Inverse-variance weighting](https://en.wikipedia.org/wiki/Inverse-variance_weighting):
"weighting each random variable to minimize the variance of the weighted
average... the inverse-variance weighted average has the least variance
among all weighted averages." Undertow already computes a real, per-
ticker 0-100 confidence for three of the four pillars —
`crowd_confidence()`, `wallstreet_confidence()`, `market_confidence()` —
each combining sample size / agreement / recency into one trust measure.
These are a direct, ready-made precision proxy: a ticker with thin Wall
Street coverage should count Wall Street's *opinion of that ticker* less
in the composite than a ticker with 50 analysts, even though Wall
Street's long-run *importance as a pillar* doesn't change. This is the
justification for confidence-weighting the composite, addressed below.
(Business pillar has no `business_confidence()` yet — `FULL_FUNDAMENTAL_
RESET.md`'s own Phase 6 flags this gap; this doc's Phase 1 below builds a
minimal version rather than leaving one pillar unweighted by construction.)

**3. The forecast-combination puzzle.** This is the single most important
finding for *how much* to trust a fitted weighting scheme right now.
Bates & Granger (1969) derived variance-minimizing "optimal" weights for
combining forecasts; in practice, simple equal (or near-equal) weights
routinely beat them out-of-sample — a well-documented, replicated
phenomenon Stock & Watson (2004) named the "forecast combination puzzle,"
[explained theoretically by Claeskens et al.](https://www.sciencedirect.com/science/article/abs/pii/S0169207016000327)
as **estimation error dominating** whenever the weights themselves are
fit on too little data. This is not a hypothetical risk for Undertow —
`data/signal_history.json` has existed for about a week as of this
writing. Fitting "optimal" weights (e.g. via regression against forward
returns) on a week of data would fit noise, not signal, and the fitted
weights would likely be *worse* than a well-reasoned fixed prior. This is
why the plan below starts with **literature-informed fixed base weights**
(next section), explicitly marked as a prior to be recalibrated later —
exactly the same intellectual honesty every other pillar's RESET doc
already applies to its own weights ("placeholders, not validated... Phase
6/7 is where these get checked against real outcomes").

**4. Grinold & Kahn's Fundamental Law of Active Management.** `IR = IC ×
√Breadth` — [signal quality (IC) and the number of independent bets
(breadth) are substitutes](https://www.sciencedirect.com/science/article/pii/S0927539817300543).
The critical word is *independent*. Four correlated pillars (e.g. all
four rising together in a broad bull market) don't contribute four
independent bets' worth of information — a composite that ignores this
can overstate how much four-way agreement should be trusted. This is the
direct justification for reading `classify_divergence`'s output as part
of the composite: when all four pillars genuinely agree (Emerging
Consensus), the corroboration is real information (see meta-analysis
point above — low heterogeneity across independent estimates increases
confidence in the pooled one); when only one pillar is driving the
number while the others stay flat (Retail Euphoria), the "breadth" is
effectively 1, not 4, and the composite should reflect that, not treat
Crowd's contribution at face value.

**5. Retail sentiment is not a naive "higher = more bullish" signal.**
This is the finding most likely to be missed by a purely mechanical
weighted average, so it gets its own paragraph. The AAII Investor
Sentiment Survey — the most widely cited retail-sentiment benchmark — is
[well-documented as a *contrarian* indicator at extremes](https://hightoweradvisors.com/blogs/well-th-blog/gauging-market-sentiment-as-a-contrarian-indicator):
extreme bearishness has historically preceded above-average forward
returns, and extreme bullishness has coincided with tops, because by the
time sentiment is euphoric, most willing buyers have already bought.
Separately, [combining fundamentals with sentiment measurably outperforms
sentiment alone](https://www.sciencedirect.com/science/article/pii/S1059056025003909)
for 3-6 month forward prediction — sentiment is real information, but
conditional on, not substitutable for, fundamentals. This is exactly
what Undertow's own Divergence Engine pattern names already encode:
**Retail Euphoria is explicitly defined as crowd-hot-without-confirmation
being a warning sign, not a bullish confirmation** (`main.py`'s own
`_build_divergence_signal` headline: *"retail conviction is running
ahead of the rest"*). A composite score that just adds Crowd's 0-100
number in linearly, at face value, alongside the other three pillars
would silently contradict a pattern the codebase has already built and
named correctly. The composite must not do that — Crowd needs to
participate at its literature-supported (smaller, more conditional)
weight, and the Retail-Euphoria case needs an explicit, bounded
adjustment, not just hope that a modest linear weight is enough.

**6. Signal horizon mismatch.** The four pillars don't operate on the
same native time horizon, and pretending they do is a real source of
error, not a simplification. Zacks' entire Agreement/Magnitude system
(already the direct inspiration for `wallstreet.py`'s revision scoring)
is [built and validated specifically for a 1-3 month holding horizon](https://www.zacks.com/education/stock-education/zacks-rank-guide-9),
and [post-earnings-announcement drift is concentrated in the first
post-announcement quarter and decays rapidly after](https://www.sciencedirect.com/science/article/pii/S2214635020303750)
— both meaningfully *shorter* than the target horizon this doc actually
uses (see below). Momentum's classic academic window is 6-12 months —
[George & Hwang's 52-week-high effect, which `market.py`'s `extension`
category is directly built on, shows no long-term reversal](https://www.spglobal.com/spdji/en/documents/research/research-exploring-techniques-in-multi-factor-index-construction.pdf),
i.e. it doesn't just work short-term and then mean-revert against you.
Quality/fundamentals' edge (Piotroski, already cited in `fundamentals.py`)
was originally validated over a full one-year holding period — a
multi-quarter-to-multi-year-native signal, not a short-term one. Crowd
sentiment's predictive window is the shortest of the four for a simple
"reads correctly" interpretation — but its well-documented *contrarian*
behavior at extremes (AAII) is itself validated at six-to-twelve months
(see point 5), which turns out to matter a great deal for which target
horizon this doc should actually calibrate to (resolved below, with
user input — see "Decisions" at the end).

**Target horizon: 6-12+ months, not 30-90 days.** This was an open
decision in the first draft of this doc; resolved directly by the user.
It changes the weight derivation, not just the framing — at 6-12 months,
Business and Market are now the *best*-horizon-matched pillars (both
validated at exactly this window), Wall Street's revision-driven edge is
specifically documented to have mostly decayed by this point (its real
edge lives in the 1-3 month window this doc is deliberately *not*
targeting), and Crowd's AAII-documented contrarian effect at extremes —
"above-average returns over the following six to twelve months" after
sentiment hits an extreme — lands squarely inside the chosen target
horizon. That last point matters structurally: it's not just a reason to
keep Crowd's linear weight low, it's direct evidence that Crowd's
relationship to 6-12 month forward returns is genuinely non-monotonic at
extremes, which is exactly what Step 4's divergence adjustment (not a
higher linear weight) is built to capture. See the revised Step 1/Step 4
below.

## Design principles this implies

1. **Deterministic and decomposable.** A pure function of `pillar_scores`
   + each pillar's confidence + the Divergence Engine's classification —
   same inputs always produce the same output, and the output can be
   broken back down into "how much did each pillar contribute."
2. **Fixed, literature-informed base weights now; fitted weights later,
   once there's enough data not to be fitting noise** (forecast-
   combination-puzzle discipline — same "Phase 7 blocked on data volume"
   honesty every other pillar's RESET doc already has).
3. **Confidence-weighted, not just coverage-gated.** Existing code
   already drops a missing pillar from the average (`present` dict
   pattern throughout `main.py`/`fundamentals.py`/`wallstreet.py`/
   `market.py`) — this doc's addition is *within* the present pillars,
   weighting each one by how much to trust it for *this specific
   ticker today* (inverse-variance-weighting-style precision weighting),
   not just whether it exists at all.
4. **Divergence-aware, not divergence-blind.** The Divergence Engine's
   classification becomes a small, bounded, fully-documented adjustment
   on top of the weighted sum — not a new independent input laundering
   the same four numbers twice, and never large enough to override what
   the weighted sum itself says. Same shape as Moody's own scorecard
   methodology: [a weighted-average grid score, then a bounded, explicit
   notching adjustment](https://www.moodys.com/web/en/us/insights/methodologies-and-models.html)
   for things the raw weights can't fully capture on their own — not
   analyst discretion here (there is no analyst), but the literature-
   backed, already-named divergence patterns filling that same structural
   role.
5. **Never fabricate.** Same discipline as every pillar: a ticker with
   only 2 of 4 pillars present gets a real, visibly-lower-coverage
   composite from those 2, never a guessed value for the missing ones.
6. **Additive, not a silent replacement of the AI's read.** The AI
   analyst's own `overall_score` is real, valuable, context-aware
   analysis — it should keep existing, clearly labeled as the AI's
   independent judgment call, alongside (not instead of) the new
   deterministic `composite_score`. Only the deterministic one is fit to
   be the thing tracked against forward returns; the AI's stays useful
   for what LLM reasoning is actually good at (naming the specific
   mechanism, reading news/context numbers can't capture) and — as a
   genuine side benefit — having both lets Undertow measure, over time,
   whether the formula or the LLM's judgment tracks real outcomes better,
   which is itself real data worth having.

## Proposed methodology

### Step 1 — Base weights (prior, not fitted)

```
BASE_WEIGHTS = {
    "business":    0.35,
    "market":      0.30,
    "wall_street": 0.20,
    "crowd":       0.15,
}
```

Rationale, each grounded above and re-derived specifically for the
6-12+ month target (not carried over from a shorter-horizon draft):
**Business** gets the single largest share — quality/fundamentals is the
most multi-year-native of the four pillars (Piotroski's original F-Score
result was measured over a full one-year holding period; the whole
category — growth, profitability, balance-sheet strength, earnings
quality — describes a company's trajectory, not a short-lived read).
**Market** is close behind — the classic academic momentum window (6-12
months) and the George & Hwang 52-week-high effect `extension` is built
on (validated with no long-term reversal) are both an close, direct
match for this exact horizon, not an approximation. **Wall Street** is
demoted from what a 30-90 day target would justify — its strongest,
best-documented edge (EPS-revision Agreement/Magnitude, PEAD) is
specifically shown to concentrate in the first post-announcement quarter
and decay rapidly after, meaning by 6-12 months out the sharpest part of
that signal has typically already played out. It isn't zeroed — sustained
rating-momentum trends still carry real, slower-moving information about
a company's trajectory — just weighted below Business and Market for
this horizon rather than above them. **Crowd** stays smallest, and for a
sharper reason at this horizon than at a shorter one: sentiment's AAII-
documented contrarian effect at extremes is itself measured over 6-12
months, which means Crowd's relationship to *this specific* target isn't
just "weaker," it's genuinely non-monotonic at the extremes — real
information, but the wrong shape for a bigger linear weight to capture
well. That's what Step 4's divergence adjustment exists to handle
instead of a higher weight here. This is a **Phase 1 prior**, explicitly
marked for recalibration in Phase 2 below — never presented as backtested.

### Step 2 — Confidence-weight within the present pillars

```
for each pillar p present for this ticker:
    confidence_p = existing confidence fn (crowd_confidence / wallstreet_confidence /
                    market_confidence / NEW business_confidence), scaled 0-1
    raw_weight_p = BASE_WEIGHTS[p] * confidence_p

normalize: weight_p = raw_weight_p / sum(raw_weight_p for p present)
```

A ticker with excellent Business/Market data but thin, low-confidence
Wall Street coverage (e.g. IONQ/NBIS, already-confirmed-live thin-
coverage names per `wallstreet.py`'s own docstrings) automatically lets
Wall Street's contribution shrink toward the other three, in proportion
to how little that specific number should be trusted — precision
weighting, not a blunt on/off switch. `business_confidence()` doesn't
exist yet; Phase 1 below builds a minimal version (coverage across the
7 categories + sector-benchmark-match, same shape as the others) so no
pillar is structurally left out of this step.

### Step 3 — Weighted sum

```
composite_raw = sum(weight_p * pillar_scores[p] for p present) / sum(weight_p for p present)
```

(The denominator is 1 by construction after Step 2's normalization —
written explicitly so a future edit to Step 2 can't silently break this.)

### Step 4 — Bounded divergence adjustment

```
DIVERGENCE_ADJUSTMENT = {
    "emerging_consensus":          +4,
    "under_the_radar":             +4,
    "fundamental_deterioration":   -7,
    "retail_euphoria":             -7,
    None:                            0,
}
composite_score = clamp(composite_raw + DIVERGENCE_ADJUSTMENT[pattern], 0, 100)
```

Small and capped deliberately — this must read as "the weighted sum,
lightly adjusted for a named, literature-backed pattern," never as a
second scoring system fighting the first one. The two discounts are
deliberately larger in magnitude than the two boosts (−7 vs. +4), and
that asymmetry is itself evidence-based, not a stylistic choice: the
AAII research behind point 5 is specifically about *downside* mean-
reversion risk after sentiment extremes ("above-average returns
following extreme bearishness," tops coinciding with extreme
bullishness) measured at exactly this doc's 6-12 month target horizon —
there's real literature backing the caution side of this adjustment at
this horizon, and no equally strong literature saying four-way agreement
deserves an equally large reward. `retail_euphoria`'s discount is the
direct, concrete implementation of that finding (crowd-led-without-
confirmation is a caution flag at this horizon specifically, not a
bonus); `fundamental_deterioration`'s discount applies the same
sentiment-driven-mispricing logic (Baker & Wurgler framing) to price/
sentiment strength outrunning the business. The two confirmatory
patterns get smaller, matching-magnitude boosts on the "corroboration
across genuinely independent reads is real information" logic from
point 4 — real, but not asserted to be as strong a signal as the
downside literature is for the discount side.

### Step 5 — Coverage-aware confidence for the composite itself

```
composite_confidence = round(100 * count(pillars present) / 4)
```
...as a starting point, reported alongside `composite_score` exactly the
way `build_signal_snapshot()` already reports a coverage-based
`confidence` in `data/signal_history.json` today. This can be upgraded
later (Phase 2) to weight by each present pillar's own confidence, not
just count them — noted, not built yet, to avoid over-engineering a
field that already has a real, honest value today.

## Handling edge cases (never fabricate)

- **Fewer than 2 pillars present:** `composite_score = None`, not a
  guessed value from 1 data point — same threshold `classify_divergence`
  already uses ("fewer than 3 pillars present" → no pattern; this is a
  stricter, separate threshold because a single-pillar "composite" isn't
  a composite at all).
- **No divergence pattern fired:** adjustment is 0, not omitted — most
  tickers most days won't match a pattern, and that's the correct,
  common case (already true of `classify_divergence` itself).
- **A pillar's confidence function itself returns `None`** (e.g.
  `wallstreet_confidence()` when `w` is missing): that pillar is already
  excluded by the "present" check one level up — `None` confidence never
  reaches Step 2's multiplication.

## What changes in code

- **New:** `overall_score.py` — `score_composite(pillar_scores, confidences,
  divergence_pattern)`, pure function, unit-testable in isolation from the
  rest of the pipeline (first module in this codebase that's a pure
  function over already-computed values, not itself a fetcher — matches
  how cleanly `classify_divergence` was already isolated in `main.py`).
- **`fundamentals.py`:** add `business_confidence()`, same three-signals-
  weighted-sum shape as the other three (coverage across 7 categories /
  sector-benchmark-match freshness / a third signal TBD during Phase 1
  build — see Status below).
- **`main.py`:** call `score_composite()` inside `run_analyst_pipeline`
  right after `pillar_scores[ticker]` is computed (that's also where
  `classify_divergence` would need to run per-ticker instead of only
  inside `compute_signals`'s signal-list pass — a small reordering, not
  a redesign). Add `composite_score` / `composite_confidence` to
  `signal_snapshot` in `build_signal_snapshot()` so backtesting has it
  from day one, same "start recording before the feature exists"
  discipline `PRODUCT.md` already committed to for Phase 4.
- **`analyst.py` / `RESPONSE_SCHEMA`:** rename the LLM's own field from
  `overall_score` to `ai_score` (additive rename — old field name can stay
  as an alias one release if needed) so the two numbers are never
  confused with each other in the payload or the frontend.
- **`stock_template.html`:** show both — `composite_score` as the
  primary, prominent number (labeled clearly as the systematic score);
  `ai_score` alongside as the AI analyst's independent read. Small
  addition, not a redesign of the existing chart-modal layout.

## Validation plan (phased, same honesty as every sibling RESET doc)

### Phase 1 — Build it ✅ DONE (2026-08-21)
`overall_score.py`, `business_confidence()`, wiring into `main.py` and
the payload, frontend surfacing. Verify live across the full 30-ticker
watchlist the same way every other phase in this project has: real
numbers, spot-checked by hand (e.g. confirm a known Retail-Euphoria
ticker's composite actually reads lower than its naive linear average
would, confirm a 2-pillar ticker shows real reduced coverage, not a
fabricated 4-pillar-equivalent number).

**What actually landed:** `score_composite()` in `overall_score.py`
(pure function, hand-verified against 3 constructed cases — full
weighting + retail-euphoria discount, 2-pillar reduced coverage, <2-pillar
→ `None` — see git history for the exact numbers checked); `business_confidence()`
added to `fundamentals.py`; `main.py`'s `run_analyst_pipeline` computes
`composite_scores` per ticker (classify_divergence called per-ticker,
not only inside the later signal-list pass) and records
`composite_score`/`composite_confidence` into both the main payload and
`signal_history` from this run onward; `analyst.py`'s own field renamed
`overall_score` → `ai_score` per Decision 1. Frontend: `stock_template.html`'s
header badge now shows `composite_score` as the primary number with
`ai_score` alongside as a secondary "AI read: N" line (falling back to
`ai_score` alone as the primary badge only when a composite genuinely
isn't available for that ticker); `dashboard_template.html` and
`sentiment_template.html`'s chart-modal AI cards and the dashboard's
ticker-search results were updated for the `ai_score` rename (the rename
had silently broken all three — `result.overall_score` no longer existed
in the payload — until this pass caught and fixed it alongside the
frontend surfacing work).
**Not yet run against a live pipeline execution** — verified via
`score_composite()` unit-style checks and a DOM-level harness exercising
`renderAiSection()`'s four data-availability cases, not yet via an actual
`main.py` run (that's a ~20-30 min live-API run, not done as part of this
pass) — the first real `main.py` run after this lands is this feature's
true first live verification, worth a spot-check per the checklist above
when that happens.

### Phase 2 — Recalibrate base weights against real outcomes — NOT
STARTED, NOT ACTIONABLE YET
Exactly the same gate every pillar's own final phase is already sitting
behind: this needs `data/signal_history.json` (now carrying
`composite_score` from Phase 1 onward) to accumulate enough real days to
compute a real Information Coefficient — correlation between
`composite_score` and actual forward returns at 7/30/90/180 days,
maturing in that order per `PRODUCT.md`'s own existing schedule. All four
windows are worth tracking, but the 180-day one is the actual
calibration target for `BASE_WEIGHTS`, since it's the closest of
`PRODUCT.md`'s existing windows to this doc's 6-12 month target — worth
flagging honestly rather than glossing over: 180 days is 6 months, the
*near* edge of "6-12 months," not the far edge, and `PRODUCT.md`'s
current track-record schedule doesn't yet define a longer window at all.
A real 12-month IC read is further out than Phase 4's existing schedule
gets Undertow on its own — either a new, longer window gets added to
that schedule, or Phase 2 here explicitly settles for calibrating against
180 days as the best available proxy for the target and says so, rather
than quietly treating 180-day results as if they validated the full
6-12 month claim. Per the forecast-combination-puzzle research above,
this should be approached carefully even once data exists (regularize
toward the Phase 1 prior rather than let a still-small sample swing the
weights hard) — not a green light to immediately curve-fit once any data
exists at all.

### Phase 3 — Decompose "why did the score change" — NOT STARTED
Once Phase 1's composite is real and stored daily, a day-over-day diff
(`PRODUCT.md`'s Phase 4 feature) becomes a real subtraction of five
already-known numbers (four pillar contributions + the divergence
adjustment) rather than new infrastructure — noted here so Phase 1 is
built with that decomposition already in mind (return the per-pillar
weighted contributions from `score_composite()`, not just the final
number).

## Status snapshot

| Phase | What | Status |
|---|---|---|
| 1 | Build `overall_score.py` + `business_confidence()` + wiring + frontend | Done (2026-08-21) — not yet exercised by a live `main.py` run |
| 2 | Recalibrate `BASE_WEIGHTS` against real signal_history outcomes | Not started — blocked on data volume |
| 3 | "Why did the score change" decomposition | Not started — depends on Phase 1's `signal_history` accumulating real days |

**Next step:** run the daily pipeline for real and spot-check
`composite_score`/`ai_score` live across the watchlist (per Phase 1's
own verification checklist above) — this hasn't happened yet, only
isolated/unit-level verification has. Phase 2 stays blocked on data
volume regardless.

## Decisions (resolved directly by the user, 2026-08-21)

1. **`ai_score` stays visible**, alongside `composite_score`, with
   `composite_score` as the large/primary number on the card and
   `ai_score` clearly secondary. Matches Design principle 6 — lets
   Undertow empirically compare the formula's real-world accuracy
   against the LLM's independent judgment over time, as a genuine side
   benefit of keeping both.
2. **Target horizon is 6-12+ months**, not the shorter 30-90 day window
   this doc originally proposed. `BASE_WEIGHTS` and the divergence-
   adjustment magnitudes above are the re-derived, horizon-correct
   versions — see the "Target horizon" callout under Research point 6
   and the rationale under Step 1/Step 4 for exactly what changed and
   why (Business and Market promoted, Wall Street demoted, Crowd's role
   shifted from "small linear weight" toward "handled mainly through the
   divergence adjustment," each with its own citation).
