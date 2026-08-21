# Product Foundation

This is the one page every future decision gets checked against. Rewritten
2026-08-13, then revised the same day after outside investor feedback on
the first rewrite — see "The moat" below, which is the single biggest
change: the four-pillar model is a good product, not yet a moat, and this
doc now says explicitly what would make it one.

## The positioning — what Undertow actually is

Not a bigger data feed than TipRanks. Not a better black-box score than
Danelfin. Not prettier fundamentals than Simply Wall St.

**Undertow is the "why" layer.** Every competitor shows you pillars side
by side — sentiment here, analyst ratings there, fundamentals somewhere
else — and leaves you to reconcile them yourself. Nobody says *why* they
agree or disagree, or what it means when they do.

Not: `TSLA = 72.`
But: *here is what everyone believes, here is why they believe it, and
here is where those beliefs conflict.*

That reconciliation is a real product differentiator. It is **not yet a
moat** — outside review (2026-08-13) correctly pointed out that Simply
Wall St already claims "thousands of data points combined into
AI-visualized analysis" across 120,000+ stocks. "Put data in one place
and use AI to explain it" is reproducible by a well-funded competitor in
a quarter. The actual moat has to be built deliberately, and it's
narrower than the whole product.

## The moat: Divergence + Change + Track Record

If the rest of this doc gets forgotten, these three should not.

1. **Divergence.** Not just Crowd vs. AI (already built — see "What's
   built"), but every pairwise pillar comparison: Crowd↔Wall Street,
   Crowd↔Business, Crowd↔Market, Wall Street↔Business, Business↔Market,
   and three-way combinations. Classified into named, recognizable
   patterns — not a generic "these disagree" flag:
   - 🔥 **Emerging Consensus** — all four pillars moving the same
     direction. High alignment.
   - ⚠️ **Retail Euphoria** — Crowd moving hard while Wall Street and
     Business stay flat. Conviction running ahead of support.
   - 🧨 **Fundamental Deterioration** — price and sentiment rising while
     Business metrics are actually falling.
   - 💎 **Under-the-Radar** — Wall Street/Business improving while Crowd
     attention hasn't caught up yet.
   A competitor can add an "AI summary" box in a sprint. They can't as
   easily copy a named taxonomy that's already been validated against
   real outcomes.
2. **Change, not state.** The product shouldn't primarily report "Crowd
   sentiment = 72." It should report "Crowd sentiment went from 51 → 72
   in 5 days while Business and Wall Street stayed flat" — a
   sentiment-led move looks completely different from a fundamentals-led
   one, and only a system with real daily history can tell them apart.
   Call this **Signal Velocity** — see Phase 4.
3. **Track record.** A competitor can copy the UI over a weekend. They
   cannot instantly recreate years of timestamped signals and what
   actually happened afterward. This is the compounding moat — it gets
   stronger every day the product runs and weaker for nobody who starts
   later. See Phase 4.

**The AI is not the moat, and shouldn't be treated as one.** The actual
proprietary stack is: data → cleaning → entity/ticker identification →
sentiment → narrative extraction → historical database → four-pillar
methodology → divergence detection → signal classification → AI
synthesis. The AI sits at the *end* of that pipeline, reasoning over
infrastructure a competitor would have to rebuild from scratch — it is
not a shortcut around building that infrastructure, and time shouldn't
go into "our AI is smarter," because it won't be; OpenAI/Google/
Anthropic will always win that fight.

## Who this is for

Retail investors who don't have the time, financial literacy, or tools to
properly research a stock — people currently piecing together a picture
from scattered Reddit threads, headlines, and gut feel, who wouldn't know
where to start reading a 10-K or interpreting an analyst rating. The
target user is you, from before you started building this.

## Two companies hiding inside this idea — we're building one of them

**Company A — Investment Intelligence.** "Help me understand the market."
This is Undertow.

**Company B — Brokerage.** "Let me buy and sell the stock." Vastly more
complicated, regulated differently, not what we're building now or
implicitly by accident.

Users come to Undertow to **Discover → Understand → Compare → Monitor →
Investigate.** Trading, if it ever happens, happens later through a
regulated brokerage partner — not inside Undertow.

**Open regulatory risk, not yet resolved:** CIRO and the Canadian
Securities Administrators issued guidance (Dec 2025) that offering
opinions on the merits of a security, or making recommendations, can
constitute regulated "advice" depending on how it's presented — and a
disclaimer doesn't automatically settle that. A 0-100 score with a
verdict on a specific security is closer to "opinion on the merits of a
security" than casual framing suggests. Outside review confirmed this is
exactly the right thing to keep flagged, and was explicit that the fix
is **not** clever wording ("not financial advice") — it's getting
Canadian securities counsel to look at actual product behavior before
monetization or real user growth. Keep this warning exactly where it is
until that review happens.

## The intelligence engine — four pillars, one synthesis layer

The original model had three pillars (Retail / Analysts / Fundamentals).
Revised to four, because convergence without price context is misleading:
retail bullish + analysts bullish + fundamentals bullish *and the stock
already up 150%* is a completely different situation than the same
convergence on a stock that hasn't moved. The old model couldn't tell
those apart. The new one has to. Outside review confirmed this
specific revision — moving from 3 pillars to 4 with Market added — as
the single best structural decision in the blueprint so far.

1. **Crowd** — *What is retail saying?* StockTwits (live), Reddit
   (built, dormant — API access rejected), ApeWisdom (live, independent
   mention-volume cross-check). Google Trends is the next easy addition
   (free, genuinely independent attention signal via `pytrends`).
   YouTube is a real planned addition too, not excluded — it needs a
   dedicated adapter plus real noise-filtering (bot/spam detection,
   engagement-weighting) before its comments are trustworthy input, the
   same kind of build Reddit and ApeWisdom already were — see Phase 2.
   X remains excluded: its API is paywalled, which breaks the $0
   discipline outright — a budget problem, not a filtering problem.
2. **Wall Street** — *What are professionals expecting?* Not built yet.
   Previously assumed to need a paid data provider ("free tiers are
   thin") — turns out `yfinance`, already a dependency, exposes real
   analyst data (`recommendations`, `analyst_price_targets`) for free.
   This closes faster than originally scoped.
3. **Business** — *What is actually happening inside the company?*
   Renamed from "Fundamentals" for clarity, otherwise unchanged. Outside
   review confirmed the rename: "Fundamentals" makes people think
   P/E-and-EPS-only, "Business" is broad enough to eventually hold
   management quality, insider activity, and competitive position
   without a redesign. Built: `fundamentals.py`, five category scores
   (growth / profitability / cash flow / balance sheet / valuation),
   free via `yfinance`.
4. **Market** — *Where does the market already have this priced?* Not
   built yet, and the newest pillar. Momentum, distance from 52-week
   high/moving averages, realized volatility, relative strength — almost
   entirely computable for free from price history we already fetch for
   every ticker. Short interest is spotty-but-sometimes-available via
   `yfinance`. Options flow is real paid-data territory — out of scope
   for now, not a v1 requirement.

**Synthesis layer:** the AI analyst (`analyst.py`) reads all four
pillars and explains *why* they agree or disagree — "retail believes X
because [named things], analysts are concerned about Y, fundamentals
show Z, and the stock is already [extended / fresh]." This isn't new
infrastructure — `analyst.py`'s existing schema (bullish/bearish
factors, risks, catalysts) already proves an LLM can reason about real
data instead of restating it. Planned schema extensions (see Phase 2 and
Phase 4): group insight *by pillar* instead of by direction; a
narrative-level sentiment taxonomy (bullish/bearish chatter tagged by
*reason* — valuation, growth, earnings, product, management, macro,
catalyst, competition, technical, M&A — so "71% bullish" becomes "71%
bullish, top reasons: earnings 31%, AI demand 24%, new product 17%");
and two new output fields — "what would change this view more bullish"
and "what would change it more bearish" — explicit counterfactual
triggers, not just a static verdict.

## What's built (condensed — see git history for detail)

- Multi-source Crowd data: StockTwits + ApeWisdom live; Reddit built and
  dormant (access rejected, revisit if that ever changes).
- News headline sentiment, kept distinct from retail chatter.
- Business pillar: `fundamentals.py`, five category scores + weighted
  overall.
- AI analyst (`analyst.py`, Gemini free tier, pinned model — see
  "Decisions locked in"): reads Business + Crowd + price + news, produces
  a reasoned score/verdict/summary/factors, not a fixed formula.
- Self-hosted price charts (no external embed) with a sentiment-history
  overlay — real gaps left as gaps, fixed -1..1 scale, not autoscaled.
- Crowd-vs-AI divergence signal — the seed of the Divergence Engine (see
  "The moat" above): fires when retail chatter and the AI's
  fundamentals-driven score disagree sharply (`main.py`,
  `compute_signals`). Needs expanding into full pairwise pillar
  comparison once Wall Street and Market exist — see Phase 2.
- History-saving dedupe fix: same-day re-runs used to silently duplicate
  "today," corrupting volume-spike baselines and sentiment trends —
  fixed, existing history files cleaned.
- Flagship set: 15 tickers — the original 10 growth/momentum names plus
  5 deliberately weak ones (INTC, BA, NKE, SBUX, PTON — real revenue
  decline / margin compression) added specifically to test whether the
  AI calls a bad setup bad. It does (Boeing scored 35/100, lowest on the
  site) even when retail chatter stayed bullish the same day. Outside
  review specifically endorsed continuing this kind of adversarial
  testing — "that is how we stop ourselves from building an AI that just
  tells investors what they want to hear."
- Full visual redesign: light navy/blue/gold system (Fraunces + Public
  Sans), replacing three failed dark-theme attempts, grounded in actual
  design research rather than another guess.
- Site structure: `docs/index.html` (marketing home), `about.html`,
  `careers.html` (static), `dashboard.html` (the only page regenerated
  daily, via `main.py`).

## Roadmap — one sequence, old and new combined

Phases are ordered by what has to be true before the next phase is worth
doing. Depth before breadth still governs sequencing: don't widen the
ticker universe or the geography before the engine itself is genuinely
good on a small, well-understood set. Outside review specifically
endorsed keeping the flagship universe small — "I'd rather see Undertow
produce an exceptionally good intelligence report on 15 stocks than
mediocre automated reports on 8,000."

### Phase 1 — Competitive intelligence ✅ (2026-08-13)
Full research across all 10 competitors in `COMPETITIVE_INTELLIGENCE.md`.
Headline finding, confirmed independently across all 10, not something
we went looking to prove: **none of them do real cross-pillar
divergence reconciliation** — every one either fuses everything into a
single opaque score, or is deep in one pillar with a weak/fake/missing
crowd layer (Stock Rover's "Sentiment" score is actually a technical/
momentum score in disguise), or delivers "why" as noisy human opinion
instead of systematic reconciliation (Seeking Alpha). Nobody has a
timestamped track record of divergence-specific calls. This is real,
independently-validated whitespace for "The moat" above, not marketing
self-flattery.

Two things worth carrying forward as live risks, not just findings:
**Wealthsimple acquired Fey** (Aug 2025) specifically to build AI
research (earnings analysis, NL screening, news) — validates the whole
"why layer" opportunity but means our most natural Canadian partner
(Phase 8) could plausibly build a competing feature within a year or
two; current scope is surfacing information, not divergence
reconciliation, but the window isn't indefinite. **Simply Wall St's
"Charlie"** AI agent already markets "not a black box, shows sourced
reasoning" — rhetorically close to our own positioning. One honest
self-check: TipRanks' crowd-sentiment analog (200,000+ real linked
brokerage portfolios, revealed-preference buy/sell flow) may be more
rigorous than our chat-based Crowd pillar, which is corroborated across
sources but still self-reported and bot-susceptible — StockTwits' own
well-documented bot/spam problem is exactly why we don't trust one
feed, and validates a decision made early in the project, not a new
concern. See `COMPETITIVE_INTELLIGENCE.md` for full per-competitor
detail (pricing, UX, data sources, sourced user complaints,
differentiation analysis for each).

### Phase 2 — Complete the four-pillar engine + the Divergence Engine ✅ (2026-08-13)
Built and verified live on all 15 flagship tickers:

- **Market pillar** (`market.py`) — extension (distance from 52-week
  high), trend (position vs. 50d/200d moving averages), stability
  (realized volatility from price history already fetched). Free via
  `yfinance` fields already available. Live test: PTON (down 41% from
  its 52-week high) scored 28; NVDA (near its high, trending) scored 66
  — the pillar behaves as intended.
- **Wall Street pillar** (`wallstreet.py`) — consensus rating, mean
  price target upside, and a 3-month recommendation-trend read (proxy
  for estimate revisions, since `yfinance` doesn't expose clean
  EPS/revenue revision history). Real, useful finding from live
  testing: sell-side ratings cluster structurally bullish across the
  board (analysts rarely issue Sell ratings) — even Boeing scored
  76/100 on Wall Street consensus. This isn't a scoring bug, it's a
  real, well-known market phenomenon — the Divergence Engine uses a
  separately-calibrated threshold for this pillar specifically (55/78
  vs. 35/65 for the other three) rather than distorting the score to
  force a comparable distribution.
- **Google Trends** (`trends.py`, `pytrends`) — a real, independent
  Crowd attention cross-check, but genuinely unreliable in practice:
  live testing hit HTTP 429 after a single request with only a 1.5s
  gap between calls. Shipped with a 20s base delay and one retry on
  rate-limit, which recovered most tickers (14/15 on the first full
  run) — partial failures are expected and handled gracefully, not a
  bug to chase further right now.
- **`analyst.py` schema extension** — added a `pillar_reads` field (one
  short, specific "why" per pillar) alongside the existing bullish/
  bearish/risks/catalysts fields, additive rather than a breaking
  rewrite. Verified live on Boeing: the Market pillar reasoning
  correctly identified that the stock trading above both moving
  averages meant "the market has already priced in a recovery" — the
  exact reasoning this pillar exists to enable.
- **The Divergence Engine** (`main.py`, `classify_divergence`) — full
  pairwise comparison across all four normalized pillar scores,
  classified into the four named patterns from "The moat." Live on the
  first real run: META, NVDA, and AMZN all classified as
  **Under-the-Radar** (Wall Street + Business both strong, retail
  hasn't caught up), INTC classified as **Retail Euphoria** (crowd hot,
  neither Wall Street nor Business confirming). No ticker forced into a
  pattern that didn't fit — most days most tickers won't match
  anything, which is correct, not a gap.
- **Signal history recording started** (`data/signal_history.json`) —
  every flagship ticker's four pillar scores, divergence classification,
  a real computed confidence measure (share of the 4 pillars with
  actual data), and price, recorded from this run forward. `confidence`
  is real, not a placeholder; `market_regime` is deliberately left out
  until a real market-wide volatility classification exists — no
  unexplained numbers.
- **UI**: the chart modal now shows a divergence badge (when one fired)
  plus four radial pillar dials with the AI's per-pillar reasoning
  underneath each — the TSLA mockup from earlier in the roadmap
  discussion, made real, not a mockup anymore.

YouTube as a Crowd source was intentionally not built this round —
still correctly sequenced as the bigger, more open-ended item; revisit
once the four core pillars have been running for a while.

## News Intelligence System (2026-08-13)

Triggered by a real complaint, not a roadmap item: the News section was
mixing genuinely important company news, irrelevant filler ("Jim
Cramer" style tips), and missing real stories (a live example: an
NVIDIA/Goldman Sachs/BlackRock financing deal wasn't showing up). Root
cause: the pipeline only pulled from generic "top stories" RSS feeds
and matched tickers after the fact — those feeds are curated for "what's
broadly interesting today," not "what happened at this company," so
real company news competes for space with unrelated general content and
often loses.

Researched the free options properly rather than guessing (2026-08-13):
Alpha Vantage's News API is capped at 25 requests/day — not viable at
15-ticker daily scale, ruled out. GDELT is powerful (free, updates every
15 min, near-Reuters-quality global coverage) but requires BigQuery/raw
file queries and CAMEO event interpretation — disproportionate to what
this dashboard needs right now, noted as a known option, not pursued.
Finnhub has a genuinely generous free tier (60 calls/min, real
per-company news) but needs a new signup/API key — deferred rather than
block today's build on a new credential; a clean fast-follow once
wanted, as a second independent source for corroboration.

**The design — three tiers, each answering a different question, not
one bigger ranked pile:**

1. **Material Events** — SEC EDGAR 8-K filings, the ground-truth
   materiality signal. Companies are *legally required* to file an 8-K
   within 4 business days of a material event (a new agreement, an
   acquisition, an executive departure, a lawsuit outcome) — this isn't
   an editorial judgment call, it's the regulatory definition of
   "important." Free, official, no API key. Verified live
   (2026-08-13): `data.sec.gov/submissions/CIK{cik}.json`, filtered by
   each flagship ticker's own CIK (from the free, official
   `sec.gov/files/company_tickers.json` mapping), returns clean,
   precise, per-company 8-Ks with real item codes (5.02 = officer
   departure, 2.02 = earnings, 1.01 = material agreement, etc.) —
   mapped to plain-English labels. Deliberately *not* run through the
   LLM filter/rank step: if it's here, it's material by definition, no
   grading needed. (Note: SEC's full-text search-by-company-name was
   tested first and rejected — it free-text-matches the word
   "Nvidia" anywhere in any filing, including an unrelated shell
   company's filing that just mentioned the name in passing. Filtering
   by CIK directly via the submissions endpoint is precise; searching
   by name is not.)
2. **Company News** — `yfinance.Ticker(symbol).news`, verified live to
   already work well (immediately surfaced the exact NVIDIA/Goldman
   Sachs/BlackRock deal used as the original complaint's example) —
   real outlets (Reuters, Bloomberg, Motley Fool), already a
   dependency, no new integration cost. Filtered and ranked by one
   *batched* Gemini call per ticker (not one call per headline — same
   "batch before you pay" principle already locked in for narrative
   taxonomy) that separates real company-specific news from generic
   advice/opinion/listicle content and grades importance 1-5.
3. **Market News** — the existing generic RSS feeds (Yahoo/MarketWatch/
   CNBC), unchanged, kept as ambient "what's the market talking about
   today" context — explicitly not ranked against company news, since
   that's not the job it's doing.

Implementation: `sec_filings.py` (Tier 1), `fetch_ticker_news()` added
to `news_fetcher.py` (Tier 2 source), new `news_ranker.py` (Tier 2
filter/rank), `llm_client.py` extracted from `analyst.py` so the Gemini
client/model logic isn't duplicated across two AI-calling modules.
Dashboard splits News into three visually distinct sections instead of
one mixed list.

**Built and verified live (2026-08-13), including the original
complaint's exact example.** Real run across all 15 flagship tickers:
Material Events found real 8-Ks for 4/15 tickers (RDDT, IONQ, INTC,
NKE — correctly labeled, e.g. "Officer or director departure" for a
5.02); Company News kept ranked items for 12/15 tickers, 24 items shown
sorted by importance. Confirmed the fix directly: NVDA's Company News
now includes "Nvidia partners with Goldman Sachs, BlackRock to fund
AI build-out" at importance 4/5 — the exact story that was missing
before this system existed. Also confirmed the filter side works, not
just the inclusion side: raw `yfinance` results for BA included a real
Boeing-Archer Aviation deal alongside an unrelated Lumen Technologies
board appointment and a generic "Defense ETFs to buy" listicle — the
ranker kept the two Boeing-relevant items and correctly discarded the
rest.

### Phase 3 — Surface it properly: the Stock Intelligence Page
A real dedicated page per ticker, not a modal: overall score, four
pillar sub-scores, the Divergence Engine's classification and
narrative, the Business category breakdown (bars — data already
computed, currently invisible), the sentiment/price overlay (done).
Everything from here down assembles onto this page.

### Phase 4 — History, velocity, and explainability
The compounding moat. Signal recording itself starts back in Phase 2,
the moment pillar scores exist — this phase is about what gets built on
top of that accumulating record. Formalize the signal schema:
timestamp, ticker, all four pillar scores, divergence classification,
AI synthesis, a confidence measure, price, market regime, and signal
type. Two fields need real definitions before they mean anything, not
placeholders: **confidence** should reflect actual data coverage
(fundamentals completeness, message volume adequacy), and **market
regime** should be a real computed classification (tied to the Market
pillar's volatility work), not an assumed label. Build on top of the
accumulating record:
- **Signal Velocity** — change, not state (see "The moat"): sentiment
  that moved 51→72 in 5 days reads completely differently from
  sentiment that's been flat at 72 for a month.
- **"Why did the score change?"** — a diff between two stored snapshots
  ("−13 points: Business −2, analyst revisions −4, Crowd −1, Market
  −6 — primary reason: earnings estimates revised down while price
  broke below the 50-day average"). Structurally cheap once pillar
  scores are stored historically; mostly a presentation problem once
  Phase 2-3 exist.
- **"What would change our view?"** — the AI's own bullish/bearish
  trigger fields (see synthesis layer above), surfaced directly instead
  of buried in a summary paragraph.
- **Narrative taxonomy** — tagging bullish/bearish chatter by *reason*,
  not just direction. Built via **batching**: send the AI ~20-30
  messages in a single call and have it return a structured tag per
  message, instead of one call per message — turns ~900 calls/day into
  ~30, back within the free tier. Paid capacity is explicitly off the
  table for now — if batching turns out not to be enough, that's a
  decision to make later with real evidence in hand, not something to
  plan around today.
- **Track record**: "when Undertow flagged this exact combination
  before, here's what happened." Ship incrementally as time windows
  actually mature, not all at once — 7-day and 30-day outcomes become
  real within the first month of Phase 2 recording; 90-day and 180-day
  outcomes only exist after 3 and 6 months respectively. Show what's
  real as it becomes real, rather than holding the whole feature back
  until the slowest window matures. This is the single highest-trust
  feature available at this scale, and the actual compounding moat — a
  competitor starting today can't back-fill years of timestamped
  signals, and every day we wait to start recording is a day of lead
  time we're giving up for free.

### Phase 5 — User / product-market validation
Not another blueprint — this doc already is one. What's actually needed
here is testing it against real usage: does Undertow help someone
understand a stock better than what they're already using? Informed by
Phase 1's competitive research and real people using Phases 2-4.

### Phase 6 — Data architecture & legal/regulatory review
Which sources are usable *commercially*, not just technically.
`yfinance`, StockTwits, ApeWisdom, and news feeds are fine for building
and validating the prototype — **the commercial product should not be
architected around "yfinance is free."** The eventual shape is licensed/
permitted data → normalized internal representation → intelligence, not
scrape-whatever-works-today. Bundled with the regulatory-advice question
flagged above; both need real outside review before this phase closes,
not self-certification.

### Phase 7 — Beta
25-100 real investors. Ask "what did you use it for," not "do you like
it" — that's how the real product gets discovered, not assumed.

### Phase 8 — Canadian Investor Mode
The wedge: TSX/TSXV, Canadian banks/energy/materials/mining/REITs,
CAD/USD effects, Canadian dividend stocks, Canadian economic narratives.
Real and defensible — the TSX is ~37% financials as of August 2026, a
completely different composition from the S&P 500, so pillar weighting
for RY.TO can't just reuse NVDA's logic. Deliberately sequenced after
the core engine is proven on the current 15 — this is breadth, and
breadth waits. Outside review explicitly confirmed this sequencing:
prove Undertow helps with a stock at all, then prove it works for
Canadian stocks, then decide whether Canada becomes the wedge.

### Phase 9 — Monetization
Free / Pro ($15-25/mo) / Premium ($40-60/mo) / Professional ($100+/mo) /
API-B2B — hypotheses, not decisions. Set by competitor pricing (Phase 1)
and real user behavior (Phase 7), not upfront guessing.

### Phase 10 — Geographic expansion
UK + Europe, then global. Last on purpose.

### The daily-habit framing (threaded through Phases 2-4)
The long-term shape isn't "a stock analysis website," it's a market-
intelligence operating system retail investors open every morning:
what changed overnight, stocks gaining/losing retail conviction,
pillar disagreements, sentiment disconnected from fundamentals, biggest
narratives, analyst estimate changes. This is a reorganization of the
existing Signals section (plus Phase 4's velocity/why-changed work) into
a scannable morning brief, not new infrastructure — worth keeping in
mind while building Phases 2-4 so the pieces naturally assemble into
this shape later instead of needing a rebuild.

## Decisions locked in

- **Budget** (2026-08-12): $0/month right now, ~$100/month approved when
  there's a concrete reason. The AI analyst runs on Gemini's free tier;
  upgrading model quality is a one-line change in `analyst.py`.
- **Flagship ticker set** (updated 2026-08-16): META, AMZN, NOW, NVDA,
  RDDT, NBIS, SOFI, IONQ, PANW, TEAM, INTC, BA, NKE, SBUX, PTON, TSLA,
  COIN, BABA, DIS, PYPL, AMD, MU, JPM, XOM, UNH, PFE, SNAP, CVNA, CRWD, T
  — 30 tickers, the entire site's coverage right now. The 2026-08-16
  addition (AMD, MU, JPM, XOM, UNH, PFE, SNAP, CVNA, CRWD, T) filled real
  sector gaps that had zero coverage — financials, energy, healthcare,
  telecom — and kept the adversarial-testing discipline going (UNH,
  PFE, SNAP, CVNA are real, currently-weak names, not just growth
  darlings). Keep adding deliberately adversarial names as the set
  evolves, not just ones likely to score well.
- **Model pin, not alias** (2026-08-12): `analyst.py`'s `MODEL` is
  pinned explicitly, never a `-latest` alias — one silently repointed
  mid-project and zeroed out free quota for a day. Re-evaluate model
  choice deliberately, verified live, never from docs/memory.
- **The AI is infrastructure, not the moat** (2026-08-13): don't spend
  time trying to make "Undertow AI" smarter than frontier models — spend
  it on the data/methodology/divergence/track-record stack in "The
  moat" above, which sits underneath the AI and is what a competitor
  actually can't copy quickly.
- **Batch before you pay** (2026-08-13): when a feature needs far more
  AI calls than the free tier comfortably allows (e.g., narrative
  taxonomy classifying every message individually — ~900/day would be
  60x the current daily AI-analyst usage), batch many items into one
  call instead. Paid capacity stays off the table for now — same
  instinct that found yfinance's free analyst data instead of assuming
  a paid provider was needed. Revisit paying only if batching proves
  genuinely insufficient, decided later with real evidence, not now.
- **Start recording before the feature exists** (2026-08-13): signal
  history for the track-record moat should start accumulating the
  moment pillar scores exist (Phase 2), not wait for the analysis
  features built on top of it (Phase 4) to be finished. History can't
  be back-filled; every day of delay is permanent.

## Explicitly out of scope right now

No brokerage integration, no trade execution, no mobile app, no chatbot.
Not because they're wrong ideas — because building them now would slow
down the one thing that has to be true first: the four-pillar engine and
its divergence/change/track-record moat are genuinely good on a small,
well-understood set of stocks.

**Accounts — resolved 2026-08-21, no longer out of scope.** A minimal
account system (Supabase auth, a personal watchlist) exists and is now
wired consistently across all three app pages (Dashboard/Sentiment/Stock
Intelligence) — this doc previously said "no user accounts," which was
already inaccurate by the time it was written (the underlying Supabase
tables/auth predate this doc) and stayed unreconciled until
`SITE_REDESIGN_RESET.md`'s Phase 3 caught and fixed the inconsistency
(2 of 3 pages had it, 1 didn't, and this doc denied any of it existed).
**Deliberately kept minimal, not because building more was hard:** an
account unlocks the watchlist and nothing else for now — no alerts, no
saved screens, no personalization beyond that — a direct decision, not a
default, so accounts don't quietly grow scope without a real reason
driving each addition. Revisit only when a specific need justifies it.
