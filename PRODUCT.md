# Product Foundation

This is the one page every future decision gets checked against. If a new
feature idea doesn't serve what's written here, it waits.

## Who this is for

Retail investors who don't have the time, financial literacy, or tools to
properly research a stock — people currently piecing together a picture
from scattered Reddit threads, headlines, and gut feel, who wouldn't know
where to start reading a 10-K or interpreting an analyst rating. The
target user is you, from before you started building this: someone who
wants to make an informed decision but has no efficient way to get there.

## The core product

One flagship experience: **the Stock Intelligence Page.**

For any ticker, one page answers three questions and combines them into
a single score with a plain-language explanation of *why*:

1. **What is retail saying?** — sentiment, chatter volume, bull/bear split,
   trend over time.
2. **What do Wall Street analysts think?** — consensus rating, price
   targets, estimate revisions.
3. **What do the fundamentals say?** — revenue growth, margins, valuation,
   balance sheet health.

The score is not the product. The *reasoning underneath the score* is the
product — that's what makes this useful to someone who can't do this
analysis themselves.

## What "big" means here

Six months of focused effort is real runway. The discipline that makes a
6-month build actually succeed isn't "build every phase" — it's **get the
flagship page fully working for a small number of stocks first, then
widen.** A genuinely good intelligence page for 10 tickers beats a
half-built pipeline for 5,000. Depth before breadth.

## What's already built (don't rebuild this)

- Multi-source retail sentiment: StockTwits (live) + ApeWisdom (live,
  volume cross-check) — this is a real working version of Pillar 1.
  Reddit's own API is built (`reddit.py`) but dormant — the access
  request was rejected (Reddit denies most personal/hobby projects since
  their late-2025 policy change); not worth chasing further right now.
- News headline sentiment scoring — an early piece of market-narrative
  context.
- Historical sentiment tracking (`data/history.json`) with day-over-day
  deltas and volume-spike baselines — the foundation Pillar 4 (trend
  detection) needs.
- Divergence signals (price vs. chatter, media vs. retail) — a working
  first version of "where do the pillars disagree."
- A live, branded multi-page website with self-hosted charts.

## What's done so far

1. **Fundamentals pillar** — `fundamentals.py`, free via `yfinance`, 5
   sub-scores (growth/profitability/cash flow/balance sheet/valuation)
   plus a weighted overall.
2. **The analyst model** — `analyst.py` reads fundamentals + real
   sentiment + real recent price action + real matched news for each
   flagship ticker and produces a score, verdict, and reasoned
   bullish/bearish/risks/catalysts — verified on real data (correctly
   surfaced Meta's Reality Labs losses and AI capex spend as real
   factors, not just plugging numbers into a formula). Wired into
   `main.py` (scoped to `flagship_tickers` only, rate-limited, retries
   once on 429s), persisted to `data/analyst_history.json` daily, and
   surfaced in the dashboard's chart modal. Running on Gemini's free
   flash-tier model (`gemini-flash-latest`) — genuinely free, already
   producing good output. Known limitation: the actual flagship model
   (`gemini-3.1-pro`) has **zero free quota** right now — true
   frontier-model quality (Gemini Pro paid tier, or Claude) requires
   turning on billing. `MODEL` in `analyst.py` is a one-line change
   whenever that's worth it.
3. **Cut the site down to exactly the flagship set** (2026-08-12) — the
   watchlist, trending discovery, Market Pulse, and Sector Heatmap were
   all removed. Right now the *entire* site — Signals, Leaders, Most
   Discussed, Watchlist, charts, AI analysis — covers only the flagship
   tickers, nothing else. This is deliberate: prove the Stock
   Intelligence experience is genuinely good on a small, well-understood
   set before adding breadth back. Market Pulse and Sector Heatmap are
   built and shelved (`market_data.py` still has the functions), not
   deleted — they come back once breadth is the actual next priority.
4. **Full visual redesign** (2026-08-12) — moved off the dark teal/violet
   theme (rejected twice on "too dark" feedback) to a light-primary
   system grounded in real design research: navy/blue as the trust
   color, a sparing gold accent, Fraunces + Public Sans typography.
   Applied consistently across all four pages. All existing JS/
   functionality (chart modal, sparklines, AI Analysis, filters)
   preserved — only the visual layer changed.
5. **Added 5 "bad fundamentals" tickers** (2026-08-12) — see the
   flagship ticker set note below for why and what it showed.

## What's next, in order

1. **The Stock Intelligence Page itself** — right now the AI analysis
   lives inside the chart modal as a section. The real next step is
   giving each flagship ticker its own dedicated page: three pillar
   scores, an overall score, and the plain-English "why," properly laid
   out instead of tucked into a modal.
2. **Real analyst data (Pillar 2, Wall Street)** — once the page's shape
   is proven, decide on a budget and pick a data provider for genuine
   analyst consensus (free tiers exist but are thin).
3. **Breadth** — bring back Market Pulse, Sector Heatmap, and a wider
   ticker universe with search, once the flagship experience is solid.
4. **Calibration** — once `analyst_history.json` has weeks of real
   score-vs-outcome data, build the layer that checks whether the scores
   actually predicted anything and corrects for it. See the "own model"
   discussion below.
5. **Everything past that** (early-signal detection, etc.) — after the
   above works and real people have used it.

## Decisions locked in

- **Budget** (2026-08-12): $0/month right now. Up to ~$100/month is
  approved once there's a concrete reason to spend it — not spent by
  default. The analyst model runs on Gemini's free API tier; upgrading
  model quality (Gemini paid tier, or Claude) is a one-line change in
  `analyst.py` whenever it's worth paying for.
- **Flagship ticker set** (2026-08-12, revised twice): META, AMZN, NOW,
  NVDA, RDDT, NBIS, SOFI, IONQ, PANW, TEAM, INTC, BA, NKE, SBUX, PTON.
  This is now the *entire* set the site covers — not a subset of a
  larger watchlist. (SpaceX was originally requested but isn't publicly
  traded; Atlassian/TEAM was added in its place.) The last five —
  Intel, Boeing, Nike, Starbucks, Peloton — were added deliberately as
  the opposite case from the first ten: real, multi-year revenue
  declines and margin compression, chosen specifically to test whether
  the model actually calls a bad setup bad instead of drifting bullish
  by default. It does — Boeing scored 35/100 (the lowest on the site),
  Intel and Peloton 45, Nike and Starbucks 55, all clearly separated
  from the growth names' 70s-90s range. Retail sentiment on all five
  stayed "Leaning Bullish" or "Neutral" the same day, which is itself
  a useful, honest finding: the crowd's mood and the fundamentals-
  driven score aren't the same signal, and the site shouldn't pretend
  they are.
- **Model pin, not alias** (2026-08-12): `analyst.py`'s `MODEL` is pinned
  to `gemini-3.1-flash-lite`, deliberately not a `-latest` alias. Learned
  this the hard way: `gemini-flash-latest` silently repointed to
  `gemini-3.6-flash` mid-project, which turned out to cap free usage at
  20 requests/day — quietly broke the whole flagship set in one run.
  Also improved the prompt/schema the same day: added a "reasoning"
  field the model fills before answering, banned generic filler
  ("regulatory scrutiny" with nothing named), and required every
  risk/catalyst to name a specific real thing. Verified improvement on
  META — it went from vague "regulatory scrutiny" to naming the actual
  FTC antitrust suit, the EU's DMA, and state AG lawsuits over youth
  mental health harms.
- **On building our own model** (2026-08-12): explored training/fine-
  tuning a proprietary model to replace Gemini — not realistic at this
  scale (frontier models cost $100M+ to train). The real differentiation
  is the data (multi-source sentiment nobody else combines this way),
  the methodology (transparent fundamentals scoring, balanced-by-design
  prompting), and eventually a calibration layer that learns to correct
  the LLM's score against what actually happened — genuinely proprietary,
  actually buildable, sits on top of a frontier model rather than
  replacing it.

## What's explicitly out of scope for now

No trading, no brokerage integration, no user accounts, no mobile app, no
portfolio management, no chatbot. Those are real, but they're Phase 10+
problems — solving them now would slow down the one thing that actually
matters first: proving the Stock Intelligence Page is genuinely useful.
