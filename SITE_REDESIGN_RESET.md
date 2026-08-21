# Site Redesign Reset — from three copy-pasted pages to one coherent product

Written 2026-08-21, following a live audit of the actual generated
output (not the templates read in isolation) that surfaced a cluster of
structural problems in the same conversation this doc grew out of: the
same ~25-field payload embedded whole into three ~5MB HTML files with no
per-page slicing; zero shared CSS/JS anywhere, so identical UI logic is
hand-copied across files (this is exactly how the `ai_score` rename
silently broke three separate pages earlier the same session — see git
log); a full Supabase-backed accounts/personal-watchlist system live in
2 of 3 app pages and entirely undocumented in `PRODUCT.md`; and a
landing-page primary nav of `Home | About | Careers | [one CTA button]`
that doesn't link to Sentiment Intelligence — a real, first-class
product page — anywhere a first-time visitor can see. This doc is the
phased plan to fix all of it, in the same research-grounded, phased
shape as `FULL_FUNDAMENTAL_RESET.md` / `MARKET_PILLAR_RESET.md` /
`WALL_STREET_PILLAR_RESET.md` / `OVERALL_SCORE_RESET.md`.

**Scope note, stated up front:** the "industry standard" answer for a
site like this at a real fintech company is a React/Next.js app with a
component library and an API-backed data layer. This doc does **not**
propose that — it would throw away exactly what makes Undertow work
today (zero budget, static GitHub Pages hosting, Python-only backend, no
build tooling, built and maintained through Claude Code sessions). Every
recommendation below is filtered through that constraint: adopt the
*principles* real fintech design systems use, in a form that still ships
as static HTML/CSS/vanilla JS from a Python pipeline.

## The actual gap (confirmed by reading the generated output, not assumed)

1. **Data duplication.** `main.py`'s `payload` dict (~25 fields —
   pillar scores, AI analyst output, fundamentals, financial/balance-
   sheet/cashflow history, 9-timeframe OHLCV for every ticker, news,
   material events) is passed unfiltered into `render_dashboard()`,
   `render_sentiment_page()`, and `render_stock_page()` (`main.py:1240-
   1269`). Each of `docs/dashboard.html`, `docs/sentiment.html`,
   `docs/stock.html` is ~5MB — each carrying data the page in question
   never touches.
2. **No shared CSS/JS.** Zero shared stylesheet/script files exist.
   Each of the three app templates has its own complete inline
   `<style>` block and its own hand-copied JS functions — the chart
   engine and AI-score renderer are labeled "ported verbatim" in their
   own comments, an explicit admission of copy-paste. Any shared change
   has to be hand-applied 3x and is easy to miss in one place, which is
   exactly what happened with the `ai_score` rename this session.
3. **Undocumented, inconsistent accounts system.** `dashboard_template.html`
   has a fully wired Supabase auth system (login/signup forms, a
   hardcoded Supabase URL + anon key, real `watchlists`/`watchlist_items`
   tables, an `on_auth_user_created` signup trigger) — confirmed live,
   not vestigial. `sentiment_template.html` has a partial copy.
   `stock_template.html` has **none of it** — no login state, no
   `nav-auth` element at all, so a logged-in user's session context
   disappears on any ticker detail page. This directly contradicts
   `PRODUCT.md`'s "no user accounts... explicitly out of scope" and is
   the exact "Milestone A" gap `CLAUDE.md` already flagged as
   unreconciled.
4. **Inconsistent page-generation model.** `dashboard.html`/`sentiment.html`/
   `stock.html` are generated daily from root templates + the pipeline;
   `index.html`/`about.html`/`careers.html` are hand-authored files that
   live **only** in `docs/`, no source template anywhere — a second,
   completely different content workflow hiding in the same folder. A
   stray `auth_test.html` sandbox also sits in the repo root.
5. **Landing-page navigation buries real pages.** `index.html`'s entire
   primary nav is `Home | About | Careers | Explore the Intelligence →`
   — one opaque CTA button standing in for the actual product. Sentiment
   Intelligence isn't linked anywhere on the landing page; it only
   surfaces inside a *second*, different nav bar that exists once you're
   already on `dashboard.html`. The real secondary destinations (Live
   Dashboard, `#signals-block`, `#watchlist`, disclaimer) exist only in
   the footer, not the primary nav a first-time visitor actually reads.
6. **No systematic responsive or theming layer.** Media queries exist
   (5-10 per file) but were added ad hoc, not from a defined breakpoint
   scale. No `prefers-color-scheme` support and no theme toggle — one
   hardcoded dark theme everywhere. No PWA manifest.
7. **Uncontrolled repo growth.** `.git` is already 26MB after ~3 weeks;
   `docs/dashboard.html` alone has 32 full-file-rewrite commits so far.
   Three ~5MB files get fully regenerated and permanently retained in
   history every single daily run, with no pruning — a compounding cost,
   not a one-time one.

## Research foundations

**1. Hidden/buried navigation measurably costs users.** Nielsen Norman
Group's navigation research finds that hiding real destinations behind a
menu icon or a single generic CTA reduces how often people use that
navigation at all compared to a visible menu, and that [unclear
navigation causes a meaningful share of visitors to abandon a site
within seconds](https://www.nngroup.com/topic/navigation/) of landing.
Their recommended pattern is a **hybrid nav**: show the 3-7 real
top-level destinations directly, collapse only genuinely secondary items
— not "one CTA button standing in for the whole product," which is
`index.html`'s current pattern. NN/g also finds [sticky headers increase
discoverability of what's in them](https://www.nngroup.com/topic/navigation/),
which matters directly for `stock_template.html`'s current total absence
of a nav bar.

**2. Core Web Vitals are the concrete, measurable performance bar.**
Google's 2026 thresholds: [LCP under 2.5s, INP under 200ms, CLS under
0.1, each measured at the 75th percentile of real visits](https://www.corewebvitals.io/core-web-vitals).
A ~5MB embedded JSON blob parsed synchronously on page load is a direct,
checkable LCP/INP liability — this gives Phase 6 below a concrete pass/
fail bar instead of a vague "feels slow" complaint.

**3. Design-token-first architecture is what every real fintech design
system is actually built from.** [Consistent tokens for color,
typography, spacing, and state are the foundational layer fintech design
systems are built on](https://www.kindgeek.com/blog/fintech-design-system),
themed via CSS variables — which Undertow is already halfway toward
(`--bull`/`--bear`/`--amber`/`--text-faint` already exist as CSS custom
properties in every file) — the gap isn't the *concept*, it's that the
same tokens are redefined three separate times instead of living in one
place. [Stripe's design system is widely cited as the fintech reference
point](https://www.designsystems.one/design-systems/stripe-design) for
exactly this reason: one token system, one component set, applied
everywhere, not per-page.

**4. Component libraries exist for this stack without abandoning it.**
Tooling like [Tremor — Tailwind-based, ships KPI cards/charts/tables you
compose yourself rather than a full opinionated template](https://www.kindgeek.com/blog/fintech-design-system)
— shows the middle path between "hand-roll everything three times" and
"rewrite in React": a component *vocabulary*, not a framework migration.
This doc doesn't mandate adopting any specific library (Phase 0 decides
that), but it's the proof this middle path is a normal industry pattern,
not a compromise unique to Undertow's constraints.

## Design principles this implies

1. **One source of truth per concern.** One token file, one nav
   component, one score-badge renderer, one chart engine — included into
   every page at generation time, never hand-copied again.
2. **Every page gets only the data it needs.** The payload gets sliced
   per page at generation time, not embedded whole three times.
3. **Flat, visible, identical navigation everywhere.** The same nav
   renders on every single page (including the landing page and
   `stock.html`), showing real destinations directly — no page is the
   product's front door while hiding the product behind one CTA.
4. **The accounts question gets resolved, not left half-built.** Either
   finished consistently across all pages or deliberately shelved
   everywhere — never live in 2 of 3 pages while the product doc denies
   it exists.
5. **Never break what already works.** `main.py`'s pillar-scoring
   pipeline, the four-pillar engine, the Divergence Engine — none of
   this doc touches that logic. This is a presentation-layer and
   information-architecture rebuild on top of data the backend already
   computes correctly.
6. **Measurable, not just "looks better."** Every visual/performance
   phase below has a concrete bar (Core Web Vitals numbers, WCAG contrast
   ratios, a defined breakpoint set) — not a subjective "make it look
   fresh" sign-off with nothing to check it against.

## Proposed phased plan

### Phase 0 — Design system foundation ✅ tokens + inventory done (2026-08-21), not yet wired in
**Goal:** one token source, one component inventory, before any page is
touched.
- **Done:** `design/tokens.css` — canonical token set, verified against
  all six live pages before writing it (confirmed the three app pages'
  `:root` blocks were byte-identical, zero drift there; confirmed the
  three marketing pages had only a subset — missing every `-soft`/
  `-border`/`-dim` variant, `surface-2/3`, `text-secondary`/`text-faint`,
  `radius-md/lg`, `shadow-md` — meaning marketing pages structurally
  couldn't do things the app pages can, like a tinted score badge or
  muted secondary copy). Also formalizes a type scale (32 distinct
  ad hoc font-size values found across the six pages, many 0.5px apart
  from a neighbor — collapsed to 9 deliberate steps, each mapped to the
  real cluster it replaces) and a 4px-based spacing scale (22 distinct
  ad hoc px values found in `dashboard_template.html` alone, collapsed
  similarly).
- **Done:** `design/COMPONENT_INVENTORY.md` — every recurring UI pattern
  cataloged with every file it currently appears in: nav (2 incompatible
  variants), score badge, pillar dial, divergence badge, card, empty/
  loading state (4 different implementations, no shared class — and one
  genuinely **stale** piece of copy found in the process: `dashboard_
  template.html:545`'s AI-empty-state text claims analysis is "currently
  limited to a small flagship set," but `config.json` shows
  `flagship_tickers` has been the full 30-ticker watchlist all along),
  chart engine, auth/account UI.
- **Not yet done:** none of this is wired into any live page yet — that's
  Phase 1's job (the Jinja2 partial-include step). This phase only
  produced the foundation Phase 1 will include.
- **Decision resolved (2026-08-21):** open to a small build step —
  interpreted as Jinja2 templating for shared partials, staying
  Python-only (no Node/npm), not a JS component-library adoption. Flagged
  to the user as the working interpretation; open to correction if a
  bigger shift (e.g. a Node-based library like Tremor) was actually
  intended.

### Phase 1 — Templating & data architecture ⏳ IN PROGRESS (2026-08-21)
**Goal:** kill the copy-paste and duplication at the source, mechanically,
before any visual changes.

**Done — nav/auth/CSS consolidation:**
- Jinja2 adopted (already installed, added to `requirements.txt`),
  wired into `main.py` via a `JINJA_ENV` (`FileSystemLoader([ROOT,
  templates/])`) — `render_dashboard`/`render_sentiment_page`/
  `render_stock_page` now call `JINJA_ENV.get_template(...).render(...)`
  instead of raw `str.replace("/*__DATA__*/", ...)`.
- `templates/partials/nav.html.j2` — one nav component for all three app
  pages, parameterized by `active_page`. Preserves each page's real,
  pre-existing content differences (dashboard's in-page anchors,
  sentiment's lack of a search box) rather than silently redesigning nav
  content — that's still Phase 2's job. Fixes two real gaps in the
  process: `stock_template.html`'s brand link pointed at
  `dashboard.html` instead of `index.html` (bug, now consistent with the
  other two pages), and `stock_template.html` had no `nav-auth` element
  at all (Phase 3's "finish accounts everywhere" decision required it).
- `templates/partials/auth_modal.html.j2` + `auth_base.js.j2` +
  `auth_nav_state.js.j2` — the login/signup modal and its client/form
  logic, previously hand-copied into `dashboard_template.html` and
  `sentiment_template.html` (with `stock_template.html` having none),
  now one source each. `dashboard_template.html` keeps its own extended
  `renderAuthState()` (drives the personal watchlist sidebar — real
  additional behavior for that one page, correctly left unshared);
  `sentiment_template.html`/`stock_template.html` both use the shared
  minimal nav-only version. `stock_template.html`'s pre-existing
  *second*, duplicate `sbClient` (used only for live ticker-snapshot
  polling) was merged into the one shared client rather than left as two
  separate Supabase client instances on the same page.
- `design/tokens.css` + `design/components.css` (nav/auth/search-result
  CSS, extracted and verified against real per-file diffs — dashboard
  and sentiment's copies were identical except sentiment was missing one
  `:disabled` rule; stock's `.site-nav`/`.nav-search` had two harmless
  width/padding variants, dropped in favor of the canonical version)
  copied into `docs/` at generation time and linked via `<link>` in all
  three app templates, replacing three independently hand-maintained
  `:root` blocks and CSS rule sets.
- **Verified:** each of the three templates dry-renders cleanly through
  Jinja2 in isolation (no unresolved `{% include %}` tags, no leftover
  `/*__DATA__*/` placeholder, exactly one `sbClient`/`SUPABASE_URL`
  declaration per rendered page, nav/auth markup present where expected)
  — checked directly, not assumed. A real end-to-end run through the
  live pipeline is in progress as of this writing to confirm the same
  holds with real fetched data end to end.
- **One real hazard hit and understood, not a code bug:** a pipeline run
  kicked off before this edit pass was still executing (using the old,
  pre-Jinja2 `main.py` already loaded in memory) when these template
  edits landed on disk. Templates are re-read from disk at render time,
  so that already-running process's old `str.replace("/*__DATA__*/", ...)`
  found nothing to replace once the placeholder had been swapped for
  `{{ payload_json }}`, and wrote the literal unrendered placeholder into
  `docs/dashboard.html`. Not a flaw in the new code — a race between
  concurrent file edits and an already-running process holding the old
  module in memory. Resolved by waiting for that run to fully exit before
  triggering a fresh one; worth remembering for any future mid-run edit.

**Not yet done:**
- Payload slicing (`_dashboard_payload`/`_sentiment_payload`/
  `_stock_payload`) — next up once the current verification run confirms
  the nav/CSS work is solid end to end.
- Consolidating `index.html`/`about.html`/`careers.html` onto the same
  generation model — deferred to a later Phase 1 batch; they still live
  only in `docs/` with no source template.
- `auth_test.html` cleanup — deferred alongside the above.

### Phase 2 — Information architecture & navigation
**Goal:** every real page reachable in one click, identically, from
everywhere — this is the fix for the "Explore the Intelligence" problem
directly.
- Flatten the primary nav to reflect the real product, present on **every**
  page including the landing page and `stock.html`:
  `Undertow | Dashboard | Sentiment Intelligence | [ticker search] | About | [account]`
  — 5-6 top-level items, inside NN/g's recommended range, no destination
  hidden behind a single generic CTA.
- Make the nav sticky (per the NN/g finding above) so it stays
  discoverable while scrolling long pages like the Dashboard grid.
- Consider real per-ticker static pages (`/stock/NVDA.html`) generated
  at build time instead of the current `?t=NVDA` query-param routing —
  trivial to generate since the pipeline already loops over every
  ticker, and makes a ticker page bookmarkable/shareable/linkable, which
  matters for a product whose pitch is "here's why this stock's pillars
  disagree." (Query-param routing can stay as an alias/redirect if
  changing this breaks anything currently linking to it.)
- Demote About/Careers to genuinely secondary weight (smaller, or
  grouped) since they're not product destinations, without removing them
  from the primary nav entirely — they still need to be one click away,
  just not competing visually with Dashboard/Sentiment.

### Phase 3 — Accounts & personalization decision
**Goal:** resolve the accounts question before Phase 2's nav is
finalized, since the nav's rightmost element depends on the answer.
- **This is a product decision the user makes, not a design call.**
  Two honest paths:
  - **Finish it:** wire `stock_template.html` into the same auth state
    as the other two pages, decide what an account unlocks beyond a
    watchlist (alerts? saved screens? nothing more yet?), update
    `PRODUCT.md` to state accounts exist and why.
  - **Shelve it deliberately:** remove the login UI from every page
    until it's ready, keep the Supabase tables/trigger in place for
    later, note in `PRODUCT.md` that this was built then paused (not
    silently absent).
- Either path removes the current state (live and half-built in 2 of 3
  pages, denied in the product doc), which is the one option this phase
  rules out.

### Phase 4 — Visual redesign pass
**Goal:** the actual "fresh look," now built on a stable foundation
instead of polish applied on top of duplication.
- Hierarchy discipline: one dominant number per view, secondary context
  smaller and quieter — the pattern already established this session for
  `composite_score`/`ai_score` on the stock header extends to every
  score surface site-wide.
- Density calibrated per page: Dashboard grid can stay information-dense
  (Bloomberg-terminal style is appropriate for a scanning view); a single
  stock's detail page should breathe more, closer to how a focused
  single-instrument view reads on Robinhood/Public.com.
- The four Divergence Engine patterns (Emerging Consensus / Retail
  Euphoria / Fundamental Deterioration / Under-the-Radar) get a real,
  distinct visual signature — this is Undertow's actual differentiator
  per `PRODUCT.md`'s own "moat" framing, and today it's a small icon+
  label pill. Worth designing so a user learns to recognize each pattern
  at a glance, the way a "Smart Score" badge is instantly recognizable
  on competitor sites.
- Standardize empty/loading/error states as real designed components
  (Phase 0's inventory), not ad hoc per-page text — currently inconsistent
  across files (e.g. `cm-ai-empty`'s copy and styling isn't shared).

### Phase 4B — Content & copy audit
**Goal:** the actual sentence-level pass requested alongside this doc —
where wording genuinely helps or hurts, called out with the exact
current text, not a rewrite for its own sake. Worth saying plainly
first: most of the marketing copy on `about.html`/`careers.html` and
the landing page's hero is **already strong and distinctive** — specific,
self-aware, confident ("A competitor can copy the interface in a
weekend. They can't copy years of recorded signals," "Small team,
honest about it," "a wishlist, not a req"). Nothing below asks to redo
that voice. The real, findable issues are narrower and structural:

- **"Intelligence" is overloaded — it now names five unrelated things.**
  The tagline ("Market intelligence for the modern investor"), the nav
  CTA ("Explore the Intelligence →"), a specific widget ("MARKET
  INTELLIGENCE MAP" — `index.html:454`), a page name ("Stock
  Intelligence" in the breadcrumb — `stock_template.html:381`), and
  another page name ("Sentiment Intelligence" — `sentiment_template.html:632`
  and the nav item pointing to it). None of these are the same concept,
  but they all borrow the same word, so a first-time visitor genuinely
  can't tell whether "Sentiment Intelligence" and "Stock Intelligence"
  are two different features or the same feature inconsistently named —
  which undercuts Phase 2's flattened-nav fix before it even ships.
  **Fix:** reserve "Intelligence" for the brand-level tagline only. Nav
  items become plain nouns — `Dashboard`, `Sentiment` — and the stock
  page's breadcrumb drops "Stock Intelligence" entirely (the ticker
  symbol is already the specific label there; "Stock Intelligence" adds
  a word without adding information). Give the hero widget its own name
  that isn't "Intelligence" again — e.g. "Signal Map."
- **The same destination has three different link labels.** All three
  go to `dashboard.html`: the hero's primary CTA says "Explore the
  Intelligence" (`index.html:433`), the nav bar's CTA says "Explore the
  Intelligence →" (`index.html:421`, consistent with the hero), but the
  page's own closing CTA band says "Open the live dashboard →"
  (`index.html:634`) — a different phrase for the identical link, on the
  same page. **Fix:** pick one. "Open the Dashboard" is the more literal,
  action-oriented option, and it's also the phrase Phase 2's flattened
  nav will need anyway once "Dashboard" is a plain top-level nav item
  rather than something hidden behind "the Intelligence" — so settling
  this now avoids re-deciding it during Phase 2.
- **Two landing-page sections re-explain the same four pillars back to
  back.** "THE FOUR SIGNALS" bento grid (`index.html:519-568`) and "WHY
  UNDERTOW" (`index.html:599-612`) both walk through Crowd/Wall Street/
  Business/Market within a few hundred pixels of each other, with
  overlapping but not identical framing — e.g. the Crowd bento tile and
  the "Retail sentiment" why-tile both describe cross-checking StockTwits/
  Reddit/Google Trends in slightly different words. A fifth why-tile,
  "Emerging narratives," references the News Intelligence pipeline
  (`news_ranker.py`) without that pipeline being introduced anywhere else
  on the page — it reads like an orphaned addition, not part of either
  section's actual argument. **Fix:** this is a content-structure problem
  as much as a wording one — merge into one authoritative explanation of
  the four pillars, used once, and let "WHY UNDERTOW" earn its own space
  with something it doesn't already own elsewhere on the page — real
  competitive differentiation, which exists in detail in
  `COMPETITIVE_INTELLIGENCE.md` and currently never surfaces on the site
  at all.
- **The hero's headline number isn't the same thing as a ticker's score,
  and nothing says so.** Confirmed by reading the JS: `imap-overall`
  (`index.html:892`) is a plain unweighted `average()` of the four pillar
  scores across every tracked company, labeled "Bullish"/"Bearish"/
  "Mixed" (`index.html:894`) — a different concept from a single ticker's
  `composite_score` (confidence-weighted, divergence-adjusted, per
  `overall_score.py`), shown in the same "—/100" format, right next to
  the same four pillar names a visitor will later see on a stock page.
  Nothing distinguishes "this is a market-wide average" from "this is
  this stock's score." **Fix:** either label it explicitly ("Market-wide
  average" or similar) or, once Phase 2's real per-ticker pages exist,
  consider whether the hero should show a real ticker's real
  `composite_score` instead of inventing a third, simpler calculation
  that only exists in this one widget.
- **Minor, mechanical inconsistencies** that Phase 1's shared-nav-partial
  work will resolve as a side effect, not worth a standalone fix: the
  ticker search placeholder reads "Search ticker or company..." on
  `dashboard_template.html` and "Search ticker..." on `stock_template.html`
  — same feature, two different pages, two different placeholder strings,
  because (per Phase 1's own finding) there's no shared nav component
  for them to inherit from yet.

### Phase 5 — Responsive & accessibility
**Goal:** a defined, systematic breakpoint scale and an explicit
accessibility bar, not ad hoc media queries.
- Formalize a small breakpoint set (e.g. 480 / 760 / 1080px, values
  already appearing informally across files today) and apply it
  consistently from Phase 0's tokens, mobile-first.
- Real device testing of the dense grids/pillar dials at narrow widths —
  currently unverified below whatever each file's ad hoc breakpoints
  happen to cover.
- WCAG 2.1 AA contrast check on the existing dark palette (score colors
  on tinted backgrounds — `--bull`/`--bear`/`--amber` on their `-soft`
  variants — haven't been checked against a contrast ratio target).
- **Decision needed:** add a light theme / `prefers-color-scheme`
  support, or commit deliberately to dark-only as a brand choice (many
  serious trading tools do this on purpose — Bloomberg Terminal is
  dark-only). Either is fine; flagged as a decision, not a default.

### Phase 6 — Performance
**Goal:** meet the Core Web Vitals bar (LCP < 2.5s, INP < 200ms, CLS <
0.1 at p75) on every page, concretely checkable, not just "feels faster."
- Falls out mostly from Phase 1's payload slicing.
- Lazy-load chart history: fetch a timeframe's OHLCV only when that
  chart is actually opened, instead of embedding all 9 timeframes for 30
  tickers on every page load.
- Logo/image optimization audit (`logos.py`'s cached PNGs — check
  format/compression, not just that caching exists).
- Repo-growth mitigation: consider whether `docs/*.html`'s daily full
  rewrites need indefinite git history retention, or whether a periodic
  history-squash / Git LFS / other mitigation is worth adopting given
  the 26MB-in-3-weeks trajectory — a separate, smaller decision from the
  rest of this doc, noted here since Phase 1's slicing will reduce but
  not eliminate the growth rate.

### Phase 7 — Modern features layer
**Goal:** the "modern functions" a 2026 fintech product is expected to
have, added deliberately, each with a real reason — not feature-checklist
padding.
- **Command-palette-style search (Cmd/Ctrl+K):** the ticker search
  already exists as a component; promoting it to a global keyboard
  shortcut is a small addition with outsized "this feels modern" payoff,
  and a well-established pattern in trading/dev tools.
- **Skeleton loading states** for the live Supabase polling
  (`pollTickerSnapshot`/`pollQuotes`) instead of blank space while data
  arrives.
- **A lightweight comparison view** (2-3 tickers side by side across the
  four pillars) — a natural extension of data the pipeline already
  computes per ticker, no new backend work.
- **A "what changed" surface** once `OVERALL_SCORE_RESET.md`'s Phase 3
  (day-over-day composite decomposition) lands — this is a UI home for
  data that phase already plans to produce.
- **PWA manifest** (installable, "add to home screen") — low effort
  given the site is already static and mostly read-only.
- Each of these is additive and independently shippable — none is a
  prerequisite for the phases above.

### Phase 8 — QA & rollout discipline
**Goal:** a live, daily-updated, no-staging-environment site needs a
real checklist before visual changes ship, since a broken render
currently just ships to whoever visits that day.
- A short manual QA checklist (per page, per breakpoint, run against the
  local `docs-static` preview server already configured in
  `.claude/launch.json`) before any Phase 4/5 change is committed.
- Consider a preview branch (GitHub Pages supports a second deployment
  target) so visual changes can be checked live before merging to `main`
  — optional, given this project's "no PR workflow, direct-to-main"
  convention; noted as a real trade-off, not assumed.

## Sequencing

**0 → 1 → 3 → 2 → 4/4B → 5 → 6 → 7 → 8**, roughly. Foundation and
architecture come before the accounts decision; the accounts decision
resolves before navigation is finalized (Phase 2 depends on it); visual
polish (4) and the copy audit (4B) sit on top of a stable architecture —
4B specifically should land *with* or just after Phase 2, since several
of its fixes (the "Intelligence" naming collision, the CTA-label
inconsistency) are really navigation-and-labeling decisions wearing a
copy-audit hat, not independent of Phase 2's own nav work; performance
(6) validates what Phase 1 already mostly fixed; modern features (7) and
QA discipline (8) layer on last. Phases can overlap in practice — this
is a dependency order, not a strict calendar.

## What changes in code (high-level — each phase's own detailed plan
comes when that phase is actually scoped for building)

- **New:** a shared design-token file, shared nav/footer/component
  partials, per-page payload-slicing functions in `main.py`.
- **`main.py`:** `render_dashboard`/`render_sentiment_page`/
  `render_stock_page` each take a sliced payload instead of the same
  full dict; template loading gains a partial-include step.
- **Templates:** `dashboard_template.html`/`sentiment_template.html`/
  `stock_template.html` shrink substantially once shared logic moves
  into partials; `index.html`/`about.html`/`careers.html` gain real root
  templates instead of living only in `docs/`.
- **`PRODUCT.md`:** updated once Phase 3's accounts decision is made,
  either way.
- **Nothing in `analyst.py`/`fundamentals.py`/`wallstreet.py`/`market.py`/
  `sentiment.py`/`overall_score.py`** — this doc is entirely presentation
  and information-architecture; the four-pillar engine is untouched.

## Status snapshot

| Phase | What | Status |
|---|---|---|
| 0 | Design token foundation + component inventory | Tokens + inventory written (`design/tokens.css`, `design/COMPONENT_INVENTORY.md`) — not yet wired into any page |
| 1 | Shared partials + payload slicing | Not started — next up |
| 2 | Flat, identical navigation everywhere | Not started |
| 3 | Accounts: finish everywhere (decided 2026-08-21) | Not started — decision made, build pending |
| 4 | Visual redesign pass | Not started — depends on Phases 0-1 |
| 4B | Content & copy audit | Findings documented above; fixes not applied — pairs with Phase 2 |
| 5 | Responsive breakpoint system + accessibility bar | Not started — depends on Phase 0 |
| 6 | Performance (Core Web Vitals bar) | Not started — mostly falls out of Phase 1 |
| 7 | Modern features (Cmd+K search, comparison view, PWA, etc.) | Not started — independently shippable |
| 8 | QA/rollout checklist | Not started |

**Decisions resolved (2026-08-21):**
1. Accounts: **finish it everywhere** (Phase 3) — not shelved.
2. Build tooling: **open to a small build step**, interpreted as Jinja2
   templating only, staying Python/no-Node (Phase 0) — flagged to the
   user as the working interpretation, open to correction.
3. Starting point: **Phase 0, in order** — not jumping ahead.
4. Rollout cadence: **build further ahead, review in batches** rather
   than a confirm-every-small-step loop.

**Still open — will surface at the relevant phase, not blocking start:**
1. Dark-only as a deliberate brand choice, or add real light-theme
   support? (Phase 5)
2. Real per-ticker static URLs vs. keep `?t=` query-param routing? (Phase 2)

**Next step:** Phase 1 — wire `design/tokens.css` and the components
cataloged in `design/COMPONENT_INVENTORY.md` into a real Jinja2 partial-
include step in `main.py`, and slice the payload per page.
