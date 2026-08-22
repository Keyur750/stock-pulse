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

**Added 2026-08-21, after a deliberate deep-research pass across current
industry practice and award-winning competitor products** — the user
asked directly whether this plan, as written, would produce the best
possible product, not just a cleaner one. These points changed or added
concrete goals to the phases below rather than sitting as background
reading; each affected phase now says so explicitly.

**5. A single multi-axis shape reads faster than N separate gauges, when
N is small and the shape itself is the message.** Simply Wall St's
"Snowflake" — a single polygon across 5 axes (value/growth/performance/
health/dividends) whose size and color shift as data updates — is the
most-cited, most-recognizable visual device in this exact competitor set
([Simply Wall St Help Center](https://support.simplywall.st/hc/en-us/articles/360001740916-How-does-the-Snowflake-work)).
Not accidental: [radar/spider charts are the right tool specifically
when "the shape of a multi-dimensional profile is the message," not when
exact values matter](https://fastercapital.com/content/Radar-Charts--How-to-Use-Radar-Charts-to-Show-Your-Attributes-and-Scores.html)
— and they get genuinely confusing past ~6-7 axes or with many
overlapping series, neither of which applies to Undertow's four pillars.
Four radial dials shown separately (this doc's original Phase 4 plan)
asks the viewer to visually integrate four numbers themselves; a single
four-axis shape does that integration for them, the same job the
Snowflake already does for Simply Wall St. Directly serves `PRODUCT.md`'s
"moat" — a genuinely different-shaped four-axis glyph across Emerging
Consensus/Retail Euphoria/Fundamental Deterioration/Under-the-Radar would
be a recognizable Undertow-only visual mark, not just a color pill. See
Phase 4.

**6. "Why did this move" belongs embedded at the point of the move, not
in a separate panel.** Public.com's "Key Moments" feature embeds short
AI-generated explanations of a stock's price action directly on the
price chart itself, at the point where the move happened, rather than in
a separate summary block ([Public.com AI Agents](https://public.com/ai-agents)).
This is the clearest 2026 industry validation of exactly the problem
Undertow's Divergence Engine already solves one level up (why pillars
disagree, not why price moved) — the design lesson transfers directly:
the divergence badge's "why" (already generated by the AI analyst,
currently only reachable in a modal/detail view) should surface at the
point on the chart/timeline where the divergence actually fired. See
Phase 4.

**7. Users tolerate low confidence fine, as long as it's visible and
paired with a next step.** [Confidence scores are a communication
problem as much as a technical one](https://xite.ai/blogs/why-your-ai-product-needs-a-confidence-score-and-how-to-design-one/)
— [research on trust in financial AI interfaces specifically finds that
an adviser (human or AI) who explains reasoning and acknowledges
uncertainty reads as more credible, not less](https://ergomania.eu/explainable-ai-xai-ux-design-finance/).
Undertow already computes real per-pillar confidence
(`crowd_confidence`/`wallstreet_confidence`/`business_confidence`/
`market_confidence`) and a composite `composite_confidence` — none of it
has a real visual pattern in any template today. A real, buildable
component, not new backend work. See Phase 4.

**8. WCAG 2.2 is the forward-looking target, not 2.1.** [WCAG 2.2 is
backward-compatible with 2.1 — 77 of its 78 criteria plus 9 new ones —
so a page meeting 2.2 AA automatically meets 2.1 AA](https://www.levelaccess.com/blog/wcag-2-2-aa-summary-and-checklist-for-website-owners/),
and [the EU's EN 301 549 standard has already adopted 2.2, with the US
Section 508 refresh expected to follow](https://ratedwithai.com/blog/wcag-2-1-vs-2-2).
No reason to target the older version when the newer one is a strict
superset. See Phase 5.

**9. Retail-investing UX in 2026 is mobile-first by default, not
desktop-then-breakpoints.** [Robinhood's mobile-first design and
streamlined onboarding are explicitly credited with setting the fintech
UX standard other apps now follow](https://stockbrokerreview.com/trading-platforms/robinhood-app-review)
— mobile isn't a responsive afterthought for this category, it's the
primary surface. This doc's original plan treated mobile as Phase 5's
breakpoint/device-testing pass; the design and component decisions in
Phase 4 now assume a phone-sized viewport as the primary case from the
start, not a retrofit. See Phase 4/5.

**10. This product's stated target user specifically needs a first-run
explanation, and nothing in this doc's original plan provided one.**
`PRODUCT.md` names the target user as someone who "wouldn't know where
to start reading a 10-K" — and [2026 retail-investing UX research
repeatedly cites lightweight first-touch education (contextual
explainers, guided tours, micro-education tied to a real action) as a
differentiator specifically for this audience](https://lollypop.design/blog/2026/june/trading-app-design/).
Nothing in this doc's original Phases 0-8 taught a first-time visitor
what "Retail Euphoria" or "Under-the-Radar" mean the first time they see
one. See the new Phase 4C.

**11. A PWA's install-prompt strategy matters more than the manifest.**
[2026 is described as the turning point for PWA ROI on both iOS and
Android](https://dev.to/riteshkokam/pwa-in-2026-why-progressive-web-apps-still-matter-55p1),
but [the browser's default install prompt is easy to miss — products
with the highest adoption use a custom in-app prompt shown after a real
activation moment, not on first load, and see 35-50% higher install
rates as a result](https://www.orbix.studio/blogs/progressive-web-apps-saas-complete-guide).
See Phase 7.

**12. Skeleton screens measurably beat spinners for perceived speed, not
just aesthetics.** [Users perceive identical load times as ~20-30%
faster with a skeleton screen shaped like the eventual content than with
a spinner](https://www.onething.design/post/skeleton-screens-vs-loading-spinners) —
the concrete reason this doc's existing Phase 7 skeleton-loading item is
worth building properly (shaped per section) rather than treating as a
generic shimmer. See Phase 7.

**13. Dark-only is validated, not just conventional.** [~70-83% of
mobile users prefer dark mode, and trading-specific tools benefit
further from dark UI's chart contrast for real-time data](https://oozou.com/blog/dark-mode-vs-light-mode-ui-design-considerations-and-user-preferences-297)
— on top of Bloomberg Terminal already being the canonical dark-only
reference point this doc cites elsewhere. Doesn't force Phase 5's
still-open light-theme decision by itself (that stays a deliberate
choice either way), but confirms staying dark-only would be
well-supported, not a lazy default. See Phase 5.

**14. Command palettes are table stakes now, but only after real
navigation exists.** [Cmd+K is now standard across Linear/Vercel/GitHub/
Notion/Raycast](https://outdraw-academy.gitbook.io/ux-patterns/command-palette),
but [the same sources are explicit that a command palette is a shortcut
on top of visible navigation, not a fix for confusing navigation](https://uxpatterns.dev/patterns/advanced/command-palette)
— direct confirmation that this doc's existing sequencing (Phase 2's
flat nav before Phase 7's Cmd+K) was already the right order. See Phase 7.

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

### Phase 1 — Templating & data architecture ✅ DONE, verified live (2026-08-21)
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

**Done — payload slicing + static-page wiring (implemented this session,
not yet live-verified):**
- `_DASHBOARD_PAYLOAD_KEYS`/`_SENTIMENT_PAYLOAD_KEYS`/`_STOCK_PAYLOAD_KEYS`
  + `_slice_payload()` in `main.py` — each page's key list built by
  literally grepping every `DATA.<key>` access (and bracket/spread forms)
  in that page's own template, not guessed. Confirmed `wallstreet`/
  `balance_sheet_history`/`cashflow_history` are fetched and used
  elsewhere (pillar scoring, Supabase sync, signal history) but rendered
  by none of the three templates today — excluded from all three sliced
  payloads rather than carried as dead weight. Dry-verified against a
  synthetic full payload (correct key sets, no leftover Jinja tags) before
  a live pipeline run.
- `render_static_pages()` — `index_template.html`/`about_template.html`/
  `careers_template.html` (confirmed byte-identical to the prior
  hand-maintained `docs/` versions before wiring them in) now render
  through the same `JINJA_ENV` as the three app pages, writing
  `docs/index.html`/`about.html`/`careers.html` instead of being
  hand-edited directly. Dry-verified byte-identical output (aside from a
  pre-existing trailing-newline quirk already present in the other three
  pages' generated output).
- `auth_test.html` — already removed (confirmed via `git status`, not a
  remaining task).
- **Live-verified (2026-08-21):** a full `main.py` run against real data
  confirmed all three sliced pages are measurably smaller than the prior
  ~5.5-5.6MB (dashboard 4.97MB, sentiment 4.92MB, stock 5.01MB — roughly
  10-12% smaller each), `wallstreet`/`balance_sheet_history`/
  `cashflow_history` are completely absent from all three pages' embedded
  data (not just smaller — actually excluded), zero leftover Jinja tags,
  and exactly one `sbClient`/`SUPABASE_URL` declaration per app page. This
  run also incidentally proved a real design goal under real failure
  conditions: it hit Gemini's free-tier daily quota (500 requests/day,
  exhausted by running the full pipeline twice in one day) and only
  5/30 tickers got a fresh AI analyst read — but `composite_score`
  (computed independently of the AI call, per `OVERALL_SCORE_RESET.md`)
  was still 30/30, and every failure degraded gracefully to the existing
  honest-empty-state pattern rather than crashing or fabricating a value.
  **Phase 1 is complete.**

### Phase 2 — Information architecture & navigation ✅ DONE (2026-08-21)
**Goal:** every real page reachable in one click, identically, from
everywhere — this is the fix for the "Explore the Intelligence" problem
directly.
- **Done:** flattened the primary nav to `Dashboard | Sentiment | About
  (demoted) | Careers (demoted) | Open the Dashboard`, present on all
  six pages (the three app pages via `nav.html.j2`, the three marketing
  pages via their own `.topnav` markup — not yet merged into one shared
  component, see note below). Fixes the exact "Sentiment Intelligence
  isn't linked anywhere on the landing page" gap this doc opened with.
  Also unified the three different labels that all pointed at
  `dashboard.html` into one ("Open the Dashboard") — Phase 4B's
  already-decided copy fix, applied now since it's the same surface.
- **Done:** demoted About/Careers visually (smaller, muted text via a
  `.nav-secondary` class) without removing them from the primary nav —
  still one click away everywhere.
- **Already done before this phase started, confirmed not re-needed:**
  sticky nav — `.site-nav-wrap`/`.nav-wrap` were already `position:
  sticky` on all six pages from earlier work.
- **Done:** real per-ticker static pages — `docs/stock-{TICKER}.html`,
  one per flagship ticker, generated by `main.py`'s
  `render_stock_ticker_pages()`. Flat filenames in `docs/` (not a
  `docs/stock/` subdirectory as first sketched) — `stock_template.html`'s
  CSS links and logo images are relative paths that assume the page
  sits next to `tokens.css`/`components.css`/`logos/`; nesting one
  directory deeper would have silently 404'd every one of them, caught
  before it shipped, not after. Each page only embeds its own ticker's
  slice of the 9 per-ticker dicts (`_per_ticker_stock_payload`) — the
  same size-discipline as Phase 1's payload slicing, verified so 30
  pages don't reintroduce a 150MB regression. `?t=TICKER` query routing
  stays live as an alias (`render_stock_page()`, unchanged). A stale-page
  cleanup step removes any `stock-{TICKER}.html` whose ticker later
  drops out of the flagship set, so a shrink never leaves a permanently
  orphaned, unlinked page behind.
- **Done:** ticker-search JS ported onto `sentiment.html` — it had none
  at all before (confirmed zero references to `nav-search` in its
  script). Adapted, not copy-pasted verbatim: dashboard's version
  navigates via a global `[data-ticker]` click delegation this page
  doesn't have, so the ported version calls `openChartModal()` directly
  on click instead, matching how every other click-to-chart element on
  this page already works. `DATA.composite` is empty here (not one of
  `_SENTIMENT_PAYLOAD_KEYS`) — the existing composite→`ai_score`
  fallback in the copied rendering logic already handles that
  gracefully, confirmed rather than assumed. Incidental side effect
  worth noting: this also silently fixed Phase 4B's flagged "two
  different search placeholder strings" finding — both other app pages
  already read the placeholder from this same shared `nav.html.j2`
  partial since Phase 1, so unifying sentiment onto it left exactly one
  placeholder string, not two.
- **Not yet done:** full component-level merge of the marketing pages'
  nav onto the app pages' shared `.site-nav` (COMPONENT_INVENTORY.md's
  original Phase 1 aspiration) — content is now flattened and
  consistent everywhere, but the marketing pages still use their own
  `.topnav` CSS rather than `design/components.css`. Deferred to Phase 4
  deliberately: that's a real visual-layer change (different markup,
  different hover/active treatment), not the "mechanical, before any
  visual changes" work this phase's own principle calls for.
- **Verified, two passes:** (1) dry-rendered all six pages through
  Jinja2 with synthetic multi-ticker data — confirmed no cross-ticker
  data leakage in any per-ticker file, correct `PAGE_TICKER` baked value
  per file, generic `stock.html` unaffected, stale-file cleanup actually
  removes a dropped ticker's page. (2) **Real-data verification without
  touching Gemini at all** — the AI-quota gap only affects generated
  *text* (ai_score, verdicts, market insight), not any of what Phase 2
  actually changed, so real fundamentals/market/wall-street/price-history
  data (free, non-AI `yfinance`+SEC EDGAR sources) was pulled for 3 real
  tickers (NVDA/BA/JPM — a strong grower, a real weak name, a financial
  for the sector-benchmark path) and rendered through the actual pipeline
  functions in ~11 seconds. Real results: composite scores computed
  correctly with real partial coverage (`crowd` skipped, `coverage: 3`) —
  NVDA 76.3, BA 58.4 (appropriately low, matches Boeing's real
  struggles), JPM 71.4; real per-ticker file sizes ~211-213KB each,
  confirmed flat regardless of total ticker count (each page only pays
  for its own ticker's slice + a ~98KB fixed overhead); zero
  cross-contamination on real nested data; zero leftover Jinja tags. At
  real 30-ticker scale this projects to ~210KB per per-ticker page
  (20-25x smaller than today's single ~5MB `stock.html`) and a ~3.4MB
  generic page — a real, checked number, not a guess. **Fully verified.**

### Phase 3 — Accounts & personalization decision ✅ DONE (2026-08-21)
**Goal:** resolve the accounts question before Phase 2's nav is
finalized, since the nav's rightmost element depends on the answer.
- **Finish it everywhere** — decided 2026-08-21, not shelved.
- `stock_template.html` wired into the same auth state as the other two
  pages, as a side effect of Phase 1's nav/auth consolidation
  (`templates/partials/nav.html.j2`/`auth_modal.html.j2` gave it a real
  `nav-auth` element and shared login/signup modal where it previously
  had none at all).
- **What an account unlocks — decided directly by the user, 2026-08-21:**
  the existing personal watchlist, and nothing more for now. No alerts,
  no saved screens — a deliberate scope decision, not a default, so
  accounts don't quietly grow without a real need driving each addition.
- `PRODUCT.md` updated to state accounts exist and why, replacing its
  previously-inaccurate "no user accounts... explicitly out of scope"
  line — this also closes the "Milestone A" reconciliation gap
  `CLAUDE.md` had flagged as unresolved.

### Phase 4 — Visual redesign pass ⏳ IN PROGRESS (2026-08-21)
**Goal:** the actual "fresh look," now built on a stable foundation
instead of polish applied on top of duplication. Expanded 2026-08-21
after a deep external-research pass — several items below are new
concrete goals, not just polish, each citing the research point that
drove it (see "Research foundations" above).
- Hierarchy discipline: one dominant number per view, secondary context
  smaller and quieter — the pattern already established this session for
  `composite_score`/`ai_score` on the stock header extends to every
  score surface site-wide.
- Density calibrated per page: Dashboard grid can stay information-dense
  (Bloomberg-terminal style is appropriate for a scanning view); a single
  stock's detail page should breathe more, closer to how a focused
  single-instrument view reads on Robinhood/Public.com.
- **Mobile-first, not a desktop-then-breakpoints retrofit** (research
  point 9) — every component's phone-width layout gets decided as part
  of this same pass, not left for Phase 5 to patch in afterward.
- **✅ Done: a single four-axis shape as the primary pillar glyph**, not
  four separate radial dials shown side by side (research point 5) —
  `pillarShapeSvg()` in `stock_template.html`, placed above the existing
  pillar-grid in the "Four-Pillar Read" card (dials + per-pillar
  reasoning stay as the drill-down underneath, not replaced). Reuses
  `DIVERGENCE_META`'s existing up/down/warn/info color classes so a
  fired divergence pattern tints the shape the same way its own badge
  already reads, one color language rather than two. A pillar with no
  real score is never plotted as if it scored 0 — it draws as a small
  dashed hollow marker at center and is excluded from the filled
  polygon entirely, so the shape's area only ever reflects pillars that
  actually have data. Verified against real NVDA/BA/JPM data (same
  no-Gemini check as Phase 2's) and visually confirmed in the browser —
  caught and fixed one real bug before it shipped: the first viewBox was
  too narrow and clipped the "Wall St" label past its edge, found via
  `getBBox()` measurement, not assumed fixed by eye.
- **✅ Done: the divergence "why" surfaces in context, at the point it
  fired** (research point 6) — a one-line plain-English explanation now
  renders directly under the divergence badge itself, everywhere the
  badge appears (dashboard's chart modal, sentiment's chart modal and
  detail pane, the stock page's sentiment strip including its live
  Supabase-polling refresh path). Deliberately **not** AI-generated text
  pulled from a modal — these are the same plain-English pattern
  definitions already in `PRODUCT.md`'s "moat" section (single source:
  `templates/partials/divergence_meta.js.j2`, replacing three identical
  hand-copied `DIVERGENCE_META` objects `COMPONENT_INVENTORY.md` already
  flagged), so the "why" is always present even on a day the AI analyst
  call itself fails — a real, current concern given today's Gemini quota
  exhaustion, not a hypothetical one. **Two real, previously-invisible
  bugs found and fixed while extracting this:** `sentiment_template.html`
  read `pillars.divergence` in two separate places (the chart-modal badge
  and the detail-pane button) — a field that never existed on
  `DATA.pillar_scores[sym]` (only `crowd`/`wall_street`/`business`/
  `market` do), so the divergence badge has silently never rendered
  anywhere on the Sentiment Intelligence page. Fixed both to the same
  `DATA.signals` lookup `dashboard_template.html`'s own (working) version
  already used. Verified against real data with a deliberately-forced
  Retail Euphoria case (confirmed via live DOM inspection, not just
  static HTML) and confirmed the negative case renders zero why-spans
  when no pattern fires.
- **✅ Done: a real confidence-indicator component** (research point 7) —
  a filled/hollow 3-dot scale (`confidenceDotsHtml()`, one shared
  `templates/partials/confidence_indicator.js.j2`) reusing the exact
  High/Medium/Low/Unknown thresholds every `*_confidence_label()`
  function already returns, not a new scale invented for the frontend.
  Added `composite_confidence_label()` to `overall_score.py` (the one
  pillar-adjacent confidence with no existing label function) for the
  same reason. Shown per-pillar on the stock page's Four-Pillar Read
  card (`wallstreet` added back to `_STOCK_PAYLOAD_KEYS`/
  `_PER_TICKER_STOCK_KEYS` now that a real template need exists, per
  Phase 1's own "add a key the day a template needs it" rule) and as the
  composite's own aggregate confidence next to the score badge on all
  three app pages.
  **This also closed a real, already-flagged gap while extending the
  dashboard/sentiment chart modal:** both modals showed only `ai_score`,
  never `composite_score` — exactly what `COMPONENT_INVENTORY.md`'s
  Phase 0 pass had already flagged. Both now show composite as primary
  with `ai_score` secondary, matching the stock page's header pattern.
  **A serious regression found and fixed only by actually executing the
  page in a browser, not by grepping/dry-rendering the template source:**
  the ticker-search JS added to `sentiment_template.html` in the earlier
  Phase 2 commit declared `const searchInput`, which collided with this
  page's own pre-existing Securities-table filter box (already named
  `searchInput`) — a `SyntaxError` that silently broke the *entire*
  inline script on load, not just search. Confirmed via the live commit
  history that `docs/sentiment.html` itself was never actually
  regenerated with the broken template (the daily pipeline hasn't run
  since, blocked on quota), so this never reached the live site, but it
  would have on the next real run had this not been caught now. Fixed
  by renaming every name in that block to a `navSearch*`-prefixed
  variant. **Separately, `_SENTIMENT_PAYLOAD_KEYS` was also missing
  `signals`**, which independently blocked the divergence badge/why-text
  fix from the previous commit from ever actually rendering on this page
  (the JS was correct; `DATA.signals` itself just didn't exist in the
  sliced payload) — both gaps only surfaced by loading the rendered page
  live and calling `openChartModal()` in the browser console, checking
  real DOM output, not by re-reading the template source. **The lesson,
  stated plainly for future phases:** a dry Jinja render or a text grep
  confirms code is present in the output; it does not confirm the code
  executes without error. Live browser verification is now the standard
  for any change touching a `<script>` block, not an optional extra.
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
- **A live WCAG 2.2 AA contrast check on every color decision made in
  this phase, as it's made** (research point 8) — not deferred entirely
  to Phase 5's audit; see Phase 5 for why this is now checked twice, not
  once, and why the target version moved from 2.1 to 2.2.

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

### Phase 4C — First-run onboarding
**Goal:** teach a first-time visitor to read Undertow's actual
differentiator, since nothing in this doc's original plan did that
(research point 10). `PRODUCT.md` names the target user as someone who
"wouldn't know where to start reading a 10-K" — but a first-time visitor
landing on a stock page showing "Retail Euphoria" has no way to learn
what that means without already knowing the product. Lightweight, not a
full tutorial system:
- A short, dismissible contextual explainer the first time a divergence
  pattern is shown (e.g. "Retail Euphoria: crowd chatter is hot, but
  Wall Street and the business itself haven't confirmed it yet" — the
  same plain-English definitions already in `PRODUCT.md`'s "moat"
  section, surfaced in-product instead of only in a planning doc).
  Dismiss once, remember via `localStorage`, no account required.
- A one-time first-run tour on the stock page's four-axis pillar glyph
  (Phase 4) explaining what each axis means, shown once per browser,
  never re-shown or nagging.
- Deliberately not gated behind Phase 3's accounts decision — this
  should work identically for a logged-out first-time visitor, since
  that's who needs it most.
- Sequenced after Phase 4 (needs the four-axis glyph and divergence
  in-context surfacing to exist first) but before Phase 7, since it's
  closer to core product education than a "modern feature" add-on.

### Phase 5 — Responsive & accessibility
**Goal:** a defined, systematic breakpoint scale and a verified
accessibility bar, not ad hoc media queries.
- Formalize a small breakpoint set (e.g. 480 / 760 / 1080px, values
  already appearing informally across files today) and apply it
  consistently from Phase 0's tokens, mobile-first — the actual
  mobile-first layout decisions now happen in Phase 4 (research point 9);
  this phase's job is verifying them systematically across the full
  breakpoint set, not originating them here for the first time.
- Real device testing of the dense grids/pillar dials at narrow widths —
  currently unverified below whatever each file's ad hoc breakpoints
  happen to cover.
- **WCAG 2.2 AA** contrast check on the existing dark palette (score
  colors on tinted backgrounds — `--bull`/`--bear`/`--amber` on their
  `-soft` variants — haven't been checked against a contrast ratio
  target). Upgraded from this doc's original 2.1 AA target (research
  point 8) — 2.2 is a strict superset of 2.1, so there's no cost to
  targeting the newer version. This is the full systematic pass across
  every existing surface; the live spot-check on Phase 4's own new color
  decisions happens as those decisions are made (see Phase 4), so a
  failure here doesn't mean redoing finished visual work from scratch.
- **Decision (research-supported now, not just conventional — research
  point 13):** dark-only stays the deliberate brand choice, not a gap —
  the same instinct that already cites Bloomberg Terminal here holds up
  against real dark-mode preference data (~70-83% of mobile users prefer
  dark mode; dark UI measurably helps chart contrast for real-time
  trading data). Not forcing a `prefers-color-scheme` light theme just
  because it's technically possible; revisit only if real user feedback
  asks for it.

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
padding. **Reordered 2026-08-21** by how much each one actually
differentiates Undertow, not alphabetically or by ease of build (research
points 11/12/14).
- **A lightweight comparison view** (2-3 tickers side by side across the
  four pillars) — moved to the top of this list. A real extension of the
  actual moat (side-by-side divergence comparison across tickers), where
  Cmd+K below is parity with every other modern SaaS tool, not
  differentiation. A natural extension of data the pipeline already
  computes per ticker, no new backend work.
- **A "what changed" surface** once `OVERALL_SCORE_RESET.md`'s Phase 3
  (day-over-day composite decomposition) lands — this is a UI home for
  data that phase already plans to produce.
- **Command-palette-style search (Cmd/Ctrl+K):** the ticker search
  already exists as a component; promoting it to a global keyboard
  shortcut is a small addition with outsized "this feels modern" payoff,
  and a well-established pattern in trading/dev tools. Research point 14
  confirms this pattern assumes real visible navigation already exists —
  exactly why this doc sequences it after Phase 2's nav flattening, not
  before.
- **Skeleton loading states**, shaped to match each section (a card
  skeleton for the watchlist grid, a line skeleton for a chart) rather
  than one generic shimmer, for the live Supabase polling
  (`pollTickerSnapshot`/`pollQuotes`) instead of blank space while data
  arrives — research point 12 shows a shape-matched skeleton measurably
  beats a spinner for perceived speed, not just looks, which is why it's
  worth building properly rather than deprioritizing.
- **PWA manifest** (installable, "add to home screen") — low effort
  given the site is already static and mostly read-only, and genuinely
  worth it now, not just a checkbox (research point 11: 2026 is a real
  inflection point for PWA adoption on both iOS and Android). The
  install *prompt strategy* matters more than the manifest itself: a
  custom prompt shown after a real activation moment (e.g. a second
  visit, or viewing a third stock page) rather than the browser's
  default first-load prompt sees meaningfully higher adoption — build
  the trigger logic, not just the manifest.
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

**0 → 1 → 3 → 2 → 4/4B/4C → 5 → 6 → 7 → 8**, roughly. Foundation and
architecture come before the accounts decision; the accounts decision
resolves before navigation is finalized (Phase 2 depends on it); visual
polish (4), the copy audit (4B), and onboarding (4C, added 2026-08-21
after a deep external-research pass) sit on top of a stable architecture
— 4B specifically should land *with* or just after Phase 2, since several
of its fixes (the "Intelligence" naming collision, the CTA-label
inconsistency) are really navigation-and-labeling decisions wearing a
copy-audit hat, not independent of Phase 2's own nav work; 4C depends on
4's four-axis glyph and in-context divergence surfacing existing first.
**One deliberate change from this doc's first draft:** the WCAG contrast
check used to live entirely in Phase 5, checked only after Phase 4's
colors were already chosen — it now happens twice, live as each color
decision is made in Phase 4, and systematically across every surface in
Phase 5, so a failed check doesn't mean redoing finished visual work.
Performance (6) validates what Phase 1 already mostly fixed; modern
features (7, reordered by actual differentiation rather than ease of
build) and QA discipline (8) layer on last. Phases can overlap in
practice — this is a dependency order, not a strict calendar.

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
- **New (added after the 2026-08-21 research pass, Phases 4/4C/2):** a
  four-axis pillar-shape component (supplementing, not replacing, the
  four separate radial dials); a confidence-indicator component reusing
  the existing `*_confidence_label()` functions; an in-context divergence
  explanation surfaced on the chart/timeline itself; a lightweight
  first-run onboarding/tour component (`localStorage`-backed, no account
  required); per-ticker static page generation in `main.py`
  (`docs/stock/{TICKER}.html` or similar) alongside the existing
  `?t=TICKER` query-param page, kept as a redirect/alias.
- **`PRODUCT.md`:** updated once Phase 3's accounts decision is made,
  either way.
- **Nothing in `analyst.py`/`fundamentals.py`/`wallstreet.py`/`market.py`/
  `sentiment.py`/`overall_score.py`** — this doc is entirely presentation
  and information-architecture; the four-pillar engine is untouched.

## Status snapshot

| Phase | What | Status |
|---|---|---|
| 0 | Design token foundation + component inventory | ✅ Tokens + inventory written, wired into all three app pages (Phase 1's nav/auth/CSS consolidation, verified live 2026-08-21) |
| 1 | Shared partials + payload slicing + static-page wiring | ✅ Done, fully verified live (2026-08-21) — nav/auth/CSS consolidation, payload slicing, and index/about/careers Jinja2 wiring all confirmed against a real pipeline run |
| 2 | Flat navigation everywhere; per-ticker static URLs; ticker search on every app page | ✅ Done, verified with real data (2026-08-21); full marketing-nav component merge deliberately deferred to Phase 4 (visual-layer work) |
| 3 | Accounts: finish everywhere, unlocks watchlist only for now | ✅ Done (2026-08-21) — wired via Phase 1, scope decided by user, `PRODUCT.md` updated |
| 4 | Visual redesign pass — now includes the four-axis pillar glyph, in-context divergence "why," confidence-indicator component, mobile-first layout, live WCAG 2.2 checks | Not started — depends on Phases 0-1 |
| 4B | Content & copy audit | Findings documented above; fixes not applied — pairs with Phase 2 |
| 4C | First-run onboarding (added 2026-08-21 after external research pass) | Not started — depends on Phase 4 |
| 5 | Responsive breakpoint system + WCAG 2.2 AA accessibility bar | Not started — depends on Phase 0 |
| 6 | Performance (Core Web Vitals bar) | Not started — mostly falls out of Phase 1 |
| 7 | Modern features, reprioritized by differentiation: comparison view → "what changed" → Cmd+K → skeleton loading → PWA (with a real install-prompt strategy) | Not started — independently shippable |
| 8 | QA/rollout checklist | Not started |

**Decisions resolved (2026-08-21):**
1. Accounts: **finish it everywhere** (Phase 3) — not shelved.
2. Build tooling: **open to a small build step**, interpreted as Jinja2
   templating only, staying Python/no-Node (Phase 0) — flagged to the
   user as the working interpretation, open to correction.
3. Starting point: **Phase 0, in order** — not jumping ahead.
4. Rollout cadence: **build further ahead, review in batches** rather
   than a confirm-every-small-step loop.
5. Account scope: **watchlist only, nothing more for now** — no alerts,
   no saved screens (Phase 3).

**Still open — will surface at the relevant phase, not blocking start:**
1. Dark-only as a deliberate brand choice, or add real light-theme
   support? (Phase 5) — research since this doc's first draft supports
   dark-only as the right default (research point 13), but the final
   call is still the user's, not assumed here.

**Resolved since this doc's first draft (deep external-research pass,
2026-08-21):**
1. Real per-ticker static URLs — **decided: yes, build them**, replacing
   `?t=TICKER` query routing (kept as a redirect/alias). See Phase 2.

**Next step:** Phase 2 is fully done and verified (nav flattened, real
per-ticker static pages, ticker search on all three app pages). Per the
sequencing above, **Phase 4B (copy fixes)** is next, paired with Phase 2
per the sequencing note — the "Intelligence" naming collision and CTA-
label fixes are ready to apply. Phase 4's expanded scope (four-axis
glyph, in-context divergence, confidence component, mobile-first, live
contrast checks, plus the deferred marketing-nav component merge) and
the new Phase 4C (onboarding) are documented and ready to scope after
that — nothing from the 2026-08-21 research pass was left out of this
plan. A full live pipeline run (with fresh AI analyst text) is still
worth doing once Gemini's quota resets, but as a routine daily refresh,
not a blocker on any further building.
