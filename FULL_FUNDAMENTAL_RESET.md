# Full Fundamental Reset — Business pillar rebuild

**Read this first if you have no memory of this specific work stream** (a
new session, lost history, whatever). Same spirit as `CLAUDE.md`: a map
of what was decided, why, what's built, and what's left — not a replacement
for the code itself. If this file and the code disagree, trust the code
and fix this file.

**One-line status (update this line every phase):** Phases 1-5 done and
verified live across the full 30-ticker watchlist (data foundation,
trend/momentum scoring, earnings quality, sector-relative scoring +
Altman Z'' + DuPont-leverage-discounted ROE + financial-sector
carve-out, growth-adjusted valuation via PEG/Rule of 40). Phase 6 is
designed but not started — needs more accumulated `signal_history.json`
to backtest against before it's actionable (see that section for why).

## Why this exists

The Business/Fundamentals pillar (`fundamentals.py`) was built once, in
Phase 2 of the original four-pillar rollout (2026-08-13, see
`PRODUCT.md`), and never touched again except for UI fixes to its radar
chart. A review of the actual scoring method (this work stream, started
2026-08-20) found it's an honest, documented heuristic — but missing the
one idea every real quant/practitioner framework uses: **nothing in it
is relative to anything.** Every ticker, every sector, gets scored
against the same fixed global breakpoint tables (`_MARGIN_PTS`,
`_ROE_PTS`, `_PE_PTS`, etc. in `fundamentals.py`).

Concrete problems found (see full detail in the research section below):
1. **No sector relativity** — a bank (JPM) gets scored on debt-to-equity
   and current ratio, both structurally meaningless for banks. Software
   margins get judged by the same ruler as energy margins.
2. **Snapshot, not trend** — only current-level metrics are scored;
   `fetch_financial_history` already pulls 5yr annual + 8qtr quarterly
   data daily and it was going completely unused for scoring (only fed
   charts).
3. **No earnings-quality check** — net income vs. operating cash flow is
   never compared, so a company propping up earnings with non-cash
   accounting gets no penalty.
4. **ROE isn't leverage-adjusted** — a company juicing ROE with debt
   gets full profitability credit.
5. **Valuation isn't growth-adjusted** — a 40x P/E grower and a 40x P/E
   non-grower score identically; `growth` and `valuation` never interact.
6. **Weights are hand-picked and never examined** — `growth` carries the
   highest weight (0.25) despite academic research favoring profitability
   as the more robust factor.

## Research foundations — how a real quant/practitioner would do this

Every idea below maps to a specific phase further down. Sources are
real, checked live this session (not from training-data memory):

- **Piotroski F-Score** (Piotroski, 2000) — nine binary yes/no signals
  across profitability, leverage/liquidity, and efficiency, most of them
  about *year-over-year change*, not static level. Original study: high-
  F-Score value stocks beat low-F-Score ones by several points/year.
  → **Phase 2**.
- **Sloan accrual anomaly** (Sloan, 1996) — companies where net income
  runs far ahead of operating cash flow (high accruals) subsequently
  underperform; ~18%/yr compounded for a low-accrual long/high-accrual
  short strategy over 1962-2001 vs. 7.4%/yr for the S&P. → **Phase 3**.
- **Sector-relative z-scores** (S&P/MSCI sector scorecards, CFA peer-
  group valuation curriculum) — score companies against sector/industry
  peers, never a fixed universal threshold, because "normal" margins,
  multiples, and leverage are sector-conditional facts. → **Phase 4**.
- **DuPont decomposition** — ROE = Net Margin × Asset Turnover × Equity
  Multiplier. Two companies can have identical ROE for very different
  (and very differently risky) reasons. → **Phase 4**.
- **Altman Z-Score / Z''-Score** (Altman, 1968; non-manufacturer variant)
  — a validated, weighted bankruptcy-risk composite from Working
  Capital/Total Assets, Retained Earnings/Total Assets, EBIT/Total
  Assets, Market Value of Equity/Total Liabilities. The Z'' variant drops
  the sales/assets turnover term specifically because it's incomparable
  across non-manufacturing industries — better fit than manufacturing
  Z-Score for most of this watchlist. Zones: >2.6 safe, 1.1-2.6 grey,
  <1.1 distress. → **Phase 4**, replaces the ad hoc debt-to-equity +
  current-ratio "balance sheet" category.
- **Novy-Marx gross profitability premium** (2013) and **AQR's Quality
  Minus Junk** (Asness/Frazzini/Pedersen) — profitability (gross profit /
  assets) has about as much power predicting returns as classic value
  metrics; QMJ frames quality as profitability + growth + safety +
  payout, four legs, not just growth. → informs **Phase 6** weighting.
- **Fama-French five-factor model** (2014) — added profitability (RMW)
  and investment (CMA) factors specifically because they're independently
  priced; the CMA finding is that firms investing *aggressively* (high
  asset growth) tend to underperform conservative investors — growth
  isn't unambiguously "more is better." → informs **Phase 6** weighting.
- **Greenblatt Magic Formula** — combines ranked Earnings Yield (EBIT/EV)
  and Return on Capital; the combination outperformed either alone. A
  model for how to combine independent signals into one rank rather than
  a single blended average. → informs **Phase 6** methodology.
- **PEG ratio / Rule of 40** (SaaS-specific: growth% + margin% ≥ 40) —
  growth-adjusted valuation instead of absolute P/E buckets. → **Phase 5**.

## Free data sources found (all $0, all verified live this session)

| Source | What it gives | Status |
|---|---|---|
| `yfinance` `.balance_sheet` / `.quarterly_balance_sheet` | Total Assets, Total Equity, Working Capital, Retained Earnings, Shares Outstanding | **Wired in, Phase 1** |
| `yfinance` `.income_stmt` (already fetched) | Added `EBIT` row alongside existing Revenue/EPS/Net Income | **Wired in, Phase 1** |
| **Aswath Damodaran, NYU Stern** (free `.xls` downloads, updated ~annually — current file dated 2026-01-05) | Industry-average margins, ROE, P/E, 5yr expected growth, leverage, across ~94 industries | **Wired in, Phase 1** — see `build_sector_benchmarks.py` |
| SEC EDGAR `companyfacts` XBRL API (`data.sec.gov`, free, no key, just a descriptive User-Agent — same pattern `sec_filings.py` already uses) | Full historical structured financials, any public company | **Not used yet** — reserve cross-check if yfinance balance-sheet coverage ever has real gaps |
| Finnhub free tier (60 calls/min) | Cleaner normalized fundamentals/ratios | **Not used** — only a fallback option if needed, no registration done |

Damodaran source URLs actually used (see `build_sector_benchmarks.py`):
`margin.xls`, `roe.xls`, `pedata.xls`, `dbtfund.xls` from
`https://pages.stern.nyu.edu/~adamodar/pc/datasets/`.

## Data integration map — what's safe to change, what isn't

Full backend/frontend trace done before touching any code (see this
session's transcript for the complete walkthrough). Bottom line:

**Tightly coupled to the current 5 category names (`growth`,
`profitability`, `cash_flow`, `balance_sheet`, `valuation`) — must be
updated in lockstep with any category add/rename:**
- `stock_template.html`'s `FUND_CATEGORY_META` (~line 1263) — the radar
  chart's axis count and labels come from this JS object, not from the
  data itself. A new category key is invisible until this is updated.
- `analyst.py`'s `_fmt_fundamentals` (~line 111) — hardcodes 5 explicit
  lines into the Gemini prompt by key name, plus a hardcoded `"/5
  categories"` string.

**NOT coupled — safe regardless of category changes:**
- `main.py` — only ever reads `fscore["overall"]`, never looks inside
  `categories`.
- `dashboard_template.html` — only touches the 4 top-level pillars
  (crowd/wall_street/business/market), never reaches into Business's
  sub-categories.
- `supabase_sync.py` + `supabase/schema.sql` — `signal_history` table has
  one column, `business numeric` (the blended overall score only).
- `data/signal_history.json`, `data/analyst_history.json` — same, overall
  score / full AI-analyst-result blobs, not raw category dicts.

**Practical implication:** Phase 1 (pure data fetching) touches none of
this and is fully safe. Phases 2-3 (new category keys) need
`FUND_CATEGORY_META` and `_fmt_fundamentals` updated in the same change.
Phase 4 is safest if the `balance_sheet` **key name** stays the same and
only its underlying math/description text changes — avoids touching the
radar/prompt structure at all.

## The phased plan

### Phase 1 — Data foundation ✅ DONE (2026-08-20)
Goal: fetch and verify, live, everything later phases need, before
building on top of it — no scoring changes.

Built:
- `fundamentals.py`: new `fetch_balance_sheet_history()` (mirrors
  `fetch_financial_history()`'s exact pattern) — Total Assets, Total
  Equity, Working Capital, Retained Earnings, Shares Outstanding,
  quarterly (8) + annual (5). `total_liabilities` is *derived*
  (Total Assets − Total Equity) rather than read as its own row, since
  that row isn't consistently present across tickers (confirmed live:
  missing for NVDA, present for JPM/XOM).
- `fundamentals.py`: added `"ebit"` to `fetch_financial_history()`'s
  existing row map (same income statement already fetched, one more
  field).
- `main.py`: wired both into `run_analyst_pipeline` — new
  `balance_sheet_data` dict, returned alongside the existing five, added
  to the JSON payload as `"balance_sheet_history"`. Purely additive,
  nothing existing changed shape. End-to-end smoke test (real pipeline
  call, NVDA + JPM, including the live Gemini call) passed clean, zero
  regression to existing Business scores.
- `build_sector_benchmarks.py` (standalone script, NOT part of the daily
  pipeline — same pattern as `validate_finbert.py`): downloads
  Damodaran's five datasets, merges them into
  `data/sector_benchmarks.json` (95 industries, full stats: gross/net/
  operating margin, ROE, trailing/forward P/E, 5yr expected growth,
  debt-to-equity). Needs `xlrd` (`pip install xlrd`) to run — deliberately
  NOT added to `requirements.txt`, since the daily pipeline only ever
  reads the static JSON output, never parses Excel itself.
- `data/sector_benchmarks.json`: the built output. Includes
  `industry_mapping` — yfinance's granular `industry` field (confirmed
  live to be far more precise than its coarse `sector` field, e.g.
  "Semiconductors" / "Banks - Diversified" vs. just "Technology" /
  "Financial Services") mapped to Damodaran's industry names, for all 20
  distinct industries actually present on the current 30-ticker
  watchlist. A few mappings are genuine judgment calls (documented
  inline in the script): Credit Services (SOFI/PYPL) → "Financial Svcs.
  (Non-bank & Insurance)", deliberately NOT "Bank (Money Center)"; COIN
  → "Brokerage & Investment Banking"; UNH → "Healthcare Support
  Services". Unmapped industries fall back to `"Total Market (without
  financials)"`.

Verified live (full watchlist, 30 tickers):
- `total_assets`, `total_liabilities`, `retained_earnings`,
  `shares_outstanding`: **30/30**.
- `working_capital`, `ebit`: **28/30** — missing exactly for **SOFI and
  JPM**, both deposit-taking/lending financial companies. This isn't a
  fetch bug: banks structurally don't report a Current Assets/Current
  Liabilities split or a traditional EBIT line (interest expense *is*
  their core business, not a financing cost to strip out). Confirmed
  independently a second way — Damodaran's own dataset shows
  "Bank (Money Center)" with `gross_margin: 1.0` and `operating_margin:
  0.0`, the same structural mismatch from a completely different data
  source. **This is real evidence for Phase 4's planned financial-sector
  carve-out — it needs to cover at least SOFI + JPM, not just JPM.**
- Sector-benchmark sanity check: Semiconductors, Software, Oil/Gas
  numbers all look right against known real-world ranges. One anomaly
  flagged, not yet explained: Restaurant/Dining's aggregate ROE came back
  at ~0.1%, likely one company's unusual capital structure skewing the
  group average — worth a second look whenever Phase 4 actually reads
  this file.

### Phase 2 — Trend & momentum (Piotroski-inspired) ✅ DONE (2026-08-20)
Goal: use the financial/balance-sheet history from Phase 1 to compute
YoY direction signals, not just current-level snapshots.

Built:
- `fundamentals.py`: new `_score_trend()` — 8 Piotroski-inspired binary
  (0/100) YoY signals computed from **annual** data only (fiscal-year
  comparisons, not quarters, matching Piotroski's original design):
  `revenue_trend`, `revenue_accel` (growth rate itself accelerating, not
  just positive — needs 3 years), `eps_trend`, `margin_trend` (net
  margin expanding), `leverage_trend` (liabilities/assets decreasing),
  `liquidity_trend` (working capital/assets improving — None for banks,
  same root cause as Phase 1's SOFI/JPM gap), `dilution_trend` (shares
  outstanding not meaningfully up, 2% tolerance for routine stock comp),
  `retained_earnings_trend`. A 1% noise floor absorbs rounding/
  restatement noise rather than firing on literal >/<. Each signal is
  `None`, never a guessed direction, when either year being compared is
  missing. Deliberately does NOT duplicate Piotroski's accrual signal
  (CFO > Net Income) — that's Phase 3's job, kept as its own visible
  dimension rather than folded in twice.
  Score = average of whatever signals are present, same `_avg`-style
  None-safe pattern as every other category.
- `score_fundamentals()`: new optional `financial_history` /
  `balance_sheet_history` params (default `None`, so existing callers are
  unaffected) add a sixth `trend` category when provided, plus a new
  top-level `trend_signals` field (the raw 8-signal dict) for
  transparency — not nested inside `categories`, which stays a flat
  dict of plain 0-100 numbers so the radar chart's assumptions still
  hold.
- Weight: `trend: 0.15` — a placeholder alongside the other five, which
  the file's own docstring already admits are "reasonable judgment
  calls, not backtested." Phase 6 owns validating all six for real.
- `main.py`: reordered the per-ticker fetch (balance sheet + financial
  history now fetched *before* `score_fundamentals`, not after, so they
  can be passed in) and added `trend_signals` to `fundamentals_data`.
- `analyst.py`'s `_fmt_fundamentals`: added a Trend line to the Gemini
  prompt; the `"/5 categories"` string is now `len(cats)`-derived instead
  of hardcoded, so it won't go stale again at Phase 3+.
- `stock_template.html`'s `FUND_CATEGORY_META`: added the `trend` entry.
  The radar chart derives its axis count from this object already, so no
  other JS changed.

Verified live (real `run_analyst_pipeline` call, NVDA + JPM):
- NVDA: `trend: 62.5` (5/8 signals positive — revenue, EPS, leverage,
  dilution, retained earnings all up; growth *deceleration* off an
  extreme prior-year base, a margin dip, and a working-capital dip all
  correctly read as 0, not hidden).
- JPM: `trend: 57.1`, `liquidity_trend: null` (7/8 signals — the bank
  working-capital gap from Phase 1 flows through cleanly here too, no
  crash, no fabricated value).
- Rendered a real `docs/stock.html` locally (not committed — reverted
  after the check) and visually confirmed in-browser: the radar renders
  as a correct hexagon with all 6 labeled axes for NVDA, and correctly
  shows dashed "n/a" markers for JPM's `cash_flow`/`balance_sheet` (pre-
  existing gap, unrelated to Phase 2) alongside a normal `Trend: 57`
  point — no visual regression.

### Phase 3 — Earnings quality (Sloan accrual check) ✅ DONE (2026-08-20)
Goal: flag companies where reported profit is running ahead of actual
cash generation (Sloan, 1996) — a different question than `growth`
(is profit growing) or `trend` (is profit improving YoY): is THIS YEAR'S
reported profit backed by cash, full stop.

Built:
- `fundamentals.py`: new `fetch_cashflow_history()` — Operating Cash
  Flow, quarterly (8) + annual (5), same shape/pattern as the Phase 1/2
  fetchers. Fetched separately from `fetch_fundamentals()`'s existing
  `operating_cashflow` (a single TTM snapshot) specifically because the
  accrual check needs a cash flow figure tied to the SAME fiscal year as
  net income and total assets — mixing TTM with fiscal-year-end data
  would compare different periods.
- `_ACCRUAL_PTS`: breakpoints grounded in the published "Sloan Ratio"
  interpretation bands (checked live this session, not memory) — -10%
  to +10% is the normal range most healthy businesses cluster in, past
  +/-25% is an unusually large accrual effect. Clamped at the low end
  (not an ever-higher score for ever-more-negative accruals) since very
  extreme negative accruals can themselves reflect one-time effects.
- `_score_earnings_quality()`: accrual ratio = (Net Income − Operating
  Cash Flow) / Total Assets, using the latest single fiscal year (not a
  YoY comparison like `_score_trend` — this is already a same-year
  cross-statement check). `None`, never a guessed ratio, when any of the
  three inputs for that year isn't available.
- `score_fundamentals()`: new optional `cashflow_history` param adds a
  seventh `earnings_quality` category (weight 0.15, same placeholder
  status as `trend`'s), plus a new top-level `earnings_quality_detail`
  field (accrual ratio + the raw NI/CFO figures) for transparency.
- `main.py`, `analyst.py`, `stock_template.html`: same lockstep pattern
  as Phase 2 — fetch reordered before scoring, `earnings_quality_detail`
  added to `fundamentals_data`, new payload key `cashflow_history`, a
  Trend-quality line added to the Gemini prompt, `earnings_quality`
  added to `FUND_CATEGORY_META`.

Verified live (real `run_analyst_pipeline` call, NVDA + JPM):
- Cash flow statement coverage: **2/2** — "Operating Cash Flow" is
  reported uniformly, including for JPM, unlike the balance sheet's
  Working Capital/EBIT rows. Better real coverage than Phase 2's
  `liquidity_trend` signal.
- NVDA: `earnings_quality: 62.4` (accrual ratio 8.4%, inside the normal
  band, scored accordingly).
- JPM: `earnings_quality: 68.1` (accrual ratio 4.6% — inside the normal
  band too, but only because the ratio is scaled by JPM's enormous
  $4.4T asset base).
- **A real limitation surfaced, not just a clean pass:** JPM's raw
  operating cash flow for the year was **−$147.8B**, wildly negative in
  isolation. Under GAAP, a bank's loan growth is counted as an operating
  cash outflow (unlike literally every non-financial industry, where
  loans/receivables aren't the core business) — so a bank's OCF isn't
  really comparable to a non-bank's OCF the way the Sloan framework
  assumes, even though the final ratio happened to land in a reasonable
  range here purely because the denominator is so large. **The AI
  analyst (Gemini) took this at face value** — its actual bearish-factor
  output for JPM this run: *"The earnings quality score of 68.1
  indicates that reported net income is currently outpacing operating
  cash flow, which can signal potential future pressure on liquidity."*
  That's a plausible-sounding read that may be specifically misleading
  for a bank. **This is concrete new evidence that Phase 4/5's
  financial-sector carve-out needs to cover `earnings_quality` too, not
  just `balance_sheet`/`trend`'s working-capital-dependent signals** —
  added to that phase's scope below.
- Confirmed end-to-end in-browser (same `docs-static` local server
  pattern as Phase 2): both tickers' 7-category legend rendered
  correctly (NVDA fully populated, JPM's `cash_flow`/`balance_sheet`
  still `n/a`), and — notably — this was the first run where the AI
  analyst's actual prose visibly reasoned about a Phase 2/3 addition,
  confirming the new categories aren't just computed and stored but are
  reaching the synthesis layer as intended. Test render reverted
  afterward, nothing committed.

### Phase 4 — Sector-relative scoring + leverage-aware profitability ✅ DONE (2026-08-20)
The big structural change, deliberately sequenced after the data
groundwork. Before starting, re-read the actual code (not just this
doc) end to end — confirmed everything in Phases 1-3 matched what was
written here, but that pass also surfaced one real gap this doc hadn't
flagged: `fetch_fundamentals()` fetched yfinance's coarse `sector` field
but never the granular `industry` field that `sector_benchmarks.json`'s
`industry_mapping` actually keys on. Fixed as the first step below.

Built:
- `fundamentals.py`: added `"industry": info.get("industry")` to
  `fetch_fundamentals()`'s return dict — the missing prerequisite for
  everything else in this phase.
- `fundamentals.py`: `_load_sector_benchmarks()` / `_industry_benchmark()`
  — lazy-loads and caches `data/sector_benchmarks.json` once per process,
  maps a ticker's `industry` through the file's own `industry_mapping`
  (falling back to `"Total Market (without financials)"`), returns None
  (not a crash) if the benchmarks file is missing/corrupt or the
  industry doesn't resolve to a real entry.
- `fundamentals.py`: `_relative_or_absolute()` / `_relative_pe()` —
  sector-relative scoring with a graceful fallback to the original fixed
  global breakpoint tables (kept, unchanged) whenever no real benchmark
  is available for that specific ticker/metric. Margins/ROE/growth score
  off the DIFFERENCE vs. the industry benchmark (some Damodaran industry
  averages sit at or near zero — Advertising's net_margin is -0.3% —
  where a ratio blows up or flips sign for no real reason); valuation
  scores off a RATIO since P/E is a strictly-positive multiple and a
  ratio is the natural "cheap/expensive vs. peers" framing. Applied to
  `growth` (both revenue/earnings growth vs. Damodaran's 5yr expected
  growth — same time-horizon caveat noted in Phase 1's research section,
  not resolved, no better free source), `profitability`'s margin
  sub-scores, and `valuation` (matching forward-to-forward or
  trailing-to-trailing P/E, not a mismatched pair).
- `fundamentals.py`: `_dupont_leverage_discount()` — discounts the
  sector-relative ROE sub-score when a ticker's Total Liabilities/Total
  Equity runs above its industry peers' D/E (from
  `sector_benchmarks.json`). Deliberately asymmetric — only ever
  discounts a company MORE levered than peers (capped at 35 points),
  never rewards one that's less levered, matching the research section's
  framing ("ROE inflated purely by debt gets discounted," not a general
  leverage bonus). Untouched (not None) when the leverage comparison
  itself isn't computable.
- `fundamentals.py`: `_score_balance_sheet()` — Altman Z''-Score
  (6.56×WC/TA + 3.26×RE/TA + 6.72×EBIT/TA + 1.05×MVE/TL) replaces the ad
  hoc debt-to-equity + current-ratio blend as the primary `balance_sheet`
  method. **Key name unchanged** — only the math/description changed, so
  the radar chart's axis structure wasn't touched. Financial-sector
  carve-out: falls back to the legacy debt-to-equity + current-ratio
  blend whenever any Altman input (Working Capital, EBIT, Retained
  Earnings, Total Liabilities, market cap) isn't available — detected by
  data availability, not a hardcoded ticker list.
- `fundamentals.py`: `_score_earnings_quality()` — added the
  financial-sector carve-out Phase 3 flagged as in-scope here: returns
  None (not a computed-but-misleading score) whenever the ticker's
  latest annual Working Capital isn't reported, the same structural
  signal `_score_balance_sheet` uses. Reasoning: Phase 3 found a bank's
  operating cash flow isn't comparable to a non-bank's under GAAP (loan
  growth counts as an operating outflow), and the Gemini analyst's prose
  had already read a technically-in-range JPM accrual ratio as a genuine
  earnings-quality concern — a real misleading read, not just an
  imprecise one.
- `score_fundamentals()`: new return fields `balance_sheet_detail`
  (method used + raw Z'' score, parallel to `earnings_quality_detail`)
  and `sector_benchmark_matched` (bool, for transparency).
- `main.py`: `fundamentals_data[ticker]` now carries `industry`,
  `balance_sheet_detail`, and `sector_benchmark_matched` alongside the
  existing fields — additive, same dict shape otherwise.
- `analyst.py`'s `_fmt_fundamentals`: new `_fmt_balance_sheet_detail()`
  tells the Gemini prompt which balance-sheet method was used (Altman
  Z'' with its zone, or the legacy blend with the reason why); added a
  sector-relative-vs-fallback note to the overall-score line; added a
  line clarifying that a leverage discount is baked into the ROE
  sub-score; added a line telling the AI explicitly not to read a
  suppressed (None) earnings-quality score for a bank as a red flag.
- `stock_template.html`'s `FUND_CATEGORY_META`: updated the
  `balance_sheet` description text to reflect the Altman Z''/legacy-blend
  method — key name untouched, so no other JS changed.

Verified live (real `fetch_fundamentals` + `score_fundamentals` calls,
**full 30-ticker watchlist**, not a 1-2 ticker smoke test):
- **30/30 tickers scored with no exceptions.**
- **Sector benchmark matched 30/30** — every watchlist ticker's
  `industry` field resolved to a real Damodaran industry entry (the
  existing 20-industry mapping plus the fallback bucket covered
  everything actually on the watchlist today).
- **Balance sheet: Altman Z'' computed for 27/30, legacy blend for 3.**
  Two are the expected financial-sector carve-out (SOFI, JPM — no
  Working Capital/EBIT, same Phase 1 finding). The third, **MU**, is a
  genuinely new live finding: yfinance's `.info` for MU returned no
  `marketCap` key at all at fetch time (confirmed directly against raw
  `yf.Ticker("MU").info`, not a bug in this code) — the fallback fired
  correctly rather than fabricating a market cap from stale/derived
  numbers. Worth re-checking on a future run since it may be transient.
- **Earnings quality suppressed (None) for exactly SOFI and JPM** — 2/30,
  matching Phase 1's coverage finding precisely, confirming the
  data-driven detection (missing Working Capital) generalizes correctly
  rather than needing a hardcoded ticker list.
- Score distributions look directionally sane on manual spot-check across
  the full table — e.g. IONQ (unprofitable, early-stage) scored
  `profitability: 6.5`; NVDA/MU (both mid-upcycle, well above sector
  averages on growth and margin) scored `profitability` in the 83-85
  range; JPM's pre-existing `balance_sheet: None` gap (both Altman
  inputs AND the legacy blend's current_ratio unavailable for JPM
  specifically) is unchanged from before this phase, not a regression —
  already noted as a pre-existing gap in Phase 2's verification section
  above.
- `python -m py_compile` clean on `fundamentals.py`, `main.py`,
  `analyst.py`. Full end-to-end dashboard render (Gemini analyst calls
  included) not re-run this phase — out of scope for a scoring-logic
  change with this level of live data verification already done;
  worth a full pipeline dry run before the next daily CI run picks
  this up for real.

### Phase 5 — Growth-adjusted valuation ✅ DONE (2026-08-20)
Goal: make `valuation` reference growth instead of scoring P/E in
isolation — even after Phase 4's sector-relative fix, a 40x-P/E grower
and a 40x-P/E non-grower still weren't differentiated by how much
growth they're paying for.

Checked live before building (not memory): PEG interpretation bands
(Peter Lynch's original framework, still the standard citation) —
PEG < 1.0 undervalued vs. growth, 1.0-2.0 reasonably valued, > 2.0
overvalued; and the Rule of 40 threshold (Brad Feld/Bessemer) — revenue
growth % + margin % clearing 40 is the healthy-growth baseline for a
company with no usable P/E.

Built:
- `fundamentals.py`: `_peg_score()` — PEG = P/E ÷ growth rate, using
  earnings growth (the traditional denominator) when positive, falling
  back to revenue growth, returning None (not a garbage ratio) when
  neither is a usable positive number — a negative/near-zero growth
  rate flips PEG's sign or blows it up rather than meaning "very cheap."
  Blended (averaged) with Phase 4's sector-relative P/E score, not a
  replacement — the peer comparison is still real information a pure
  growth-adjustment would throw away.
- `fundamentals.py`: `_rule_of_40_score()` — supplementary read used
  only on the branch where P/E itself is unusable (thin/negative
  earnings), same branch that already fell back to P/S-only scoring.
  Prefers FCF margin over profit margin (checked live: the commonly-
  cited metric at scale for this framework), blended with the existing
  P/S score.
- `score_fundamentals()`: new `valuation_detail` return field (`peg` /
  `rule_of_40` sub-dicts, parallel to `earnings_quality_detail` and
  `balance_sheet_detail`) for transparency.
- `main.py`: `fundamentals_data[ticker]` carries `valuation_detail`
  alongside the existing fields.
- `analyst.py`'s `_fmt_fundamentals`: new `_fmt_valuation_detail()` tells
  the Gemini prompt the actual PEG ratio or Rule-of-40 total and how to
  read it, not just the resulting blended score.

Verified live (full 30-ticker watchlist): **30/30 scored with no
exceptions.** PEG computed for **27/30** (any ticker with a usable P/E
and positive growth); Rule of 40 computed for **2/30** (NBIS, IONQ —
both unprofitable names with no usable P/E). **COIN got neither** and
this is correct, not a gap: it has a real forward P/E (57.1), so it
stays on the PEG branch rather than falling to Rule of 40, and PEG
itself legitimately returns None there because its revenue growth is
negative (-17.3%) — meaningless as a PEG denominator — so it falls back
to the pure sector-relative P/E score alone, same graceful degradation
as Phase 4, confirmed not a bug. One outlier spot-checked in detail:
NBIS's Rule of 40 came back at -255.5 (floored to score 5) — confirmed
against raw fetched numbers (454% revenue growth, but FCF margin of
-709.5%, i.e. burning far more cash than revenue as it scales AI infra
capex) — a real, correctly-computed reading, not a units bug.
`python -m py_compile` clean on all three touched files.

### Phase 6 — Validation, weighting, and a real confidence score — NOT STARTED
Validate the (now six) dimensions' relative weight the way
`validate_finbert.py` validated the Crowd pillar's approach — check
candidate weightings against real subsequent behavior rather than leave
the original hand-picked 0.25/0.20/0.20/0.15/0.20 unexamined a second
time. Build a `business_confidence()` composite parallel to
`crowd_confidence()`: coverage across six dimensions, benchmark-data
freshness, and (once enough `signal_history.json` accumulates) real
backtested weight confidence. This is the "give a score with very high
confidence" capstone.

## Status snapshot

| Phase | What | Status |
|---|---|---|
| 1 | Data foundation (balance sheet fetch + Damodaran sector benchmarks) | ✅ Done, verified live 2026-08-20 |
| 2 | Trend & momentum (Piotroski-style, 6th category) | ✅ Done, verified live 2026-08-20 |
| 3 | Earnings quality (Sloan accrual check, 7th category) | ✅ Done, verified live 2026-08-20 |
| 4 | Sector-relative scoring + leverage-aware ROE + Altman Z'' + bank carve-out (now incl. earnings_quality) | ✅ Done, verified live 2026-08-20 across full 30-ticker watchlist |
| 5 | Growth-adjusted valuation (PEG + Rule of 40) | ✅ Done, verified live 2026-08-20 across full 30-ticker watchlist |
| 6 | Weight validation + real confidence score | Not started |

**Files touched so far:** `fundamentals.py`, `main.py`, `analyst.py`,
`stock_template.html`, `build_sector_benchmarks.py` (new),
`data/sector_benchmarks.json` (new).

**Next step:** Phase 6 (weight validation + real confidence score) —
best revisited once `signal_history.json` has accumulated a few weeks
of real outcomes to backtest the (now seven) category weights against;
backtesting on the few days of history that exist today would mostly be
noise, not signal.
