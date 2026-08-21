# Component inventory — Site Redesign Reset, Phase 0

Every recurring UI pattern across the six live pages, cataloged once so
Phase 1 knows exactly what to consolidate into a shared partial instead
of leaving it hand-copied. Each entry lists every file it currently
appears in and flags real drift found while cataloging (not assumed).

## Navigation bar — 2 incompatible variants, should be 1
- **App variant** (`.site-nav`): `dashboard_template.html`,
  `sentiment_template.html`, `stock_template.html`. Ticker search + nav
  links + auth button. Search placeholder text already drifted
  ("Search ticker or company..." vs "Search ticker...").
  `stock_template.html` has no auth UI at all (see Phase 3).
- **Marketing variant** (`.topnav`): `docs/index.html`, `about.html`,
  `careers.html`. Different markup, different classes, Home/About/
  Careers/one CTA — no ticker search, no auth state at all.
- **Phase 1 target:** one nav component, one markup structure, rendered
  identically on all six pages, differing only in which nav item is
  marked `.active` — this is also Phase 2's navigation fix and Phase 3's
  accounts fix, all three converge on this one component.

## Score badge — 2 sizes, was 2 field names until this session
- Header/primary badge (`.stock-ai-score`, 40px): `stock_template.html`
  only — the composite/ai_score primary+secondary treatment built this
  session.
- Modal badge (`.cm-ai-score`, 25px): `dashboard_template.html`,
  `sentiment_template.html` — still shows only `ai_score`, doesn't
  surface `composite_score` at all (noted in the redesign doc's Phase 4
  as a visual-hierarchy gap to close, not yet done).
- Both independently implement `scoreClass()` (up/down/na by the same
  65/40 thresholds) — identical logic, copied, not shared.

## Pillar dial (0-100 ring per pillar)
- Full version (`pillarDialSvg()`, `.pillar-card`): `dashboard_template.html`,
  `stock_template.html` (via `.pillar-grid`).
- Compact inline version (`miniPillarRow()`, `.mini-pillar`):
  `dashboard_template.html` only, for signal-card rows — same data,
  deliberately denser presentation, genuinely a different component
  (not drift) but worth formalizing as a documented second size of the
  same design, not a one-off.
- `pillarColorHex()` (65/35 thresholds — note: *different* cutoffs from
  `scoreClass()`'s 65/40) is redefined per file.

## Divergence pattern badge
- `DIVERGENCE_META` (icon + label + color class per pattern) redefined
  identically in `dashboard_template.html`, `sentiment_template.html`,
  `stock_template.html` — a 4-entry lookup table, copy-pasted 3x. Flagged
  in the redesign doc's Phase 4 as the product's actual differentiator;
  worth a real, distinct visual treatment once consolidated, not just a
  dedup.

## Card
- `.card` / `.card-title` — consistent styling across app pages, no
  drift found. Marketing pages use a different `.surface` /
  `.value-card` / `.why-tile` / `.signal-bento` family for what's
  visually the same "bordered content block" concept, just never
  unified with the app pages' `.card`.

## Empty / loading state — 4 different implementations, no shared class
- `.chart-empty` (13px text, 44px padding) — `dashboard_template.html`.
- `.chart-empty-timeframe` (12.5px text, 40px/24px padding) — same file,
  a *different* size/padding for a very similar "no data" message.
- `.cm-ai-empty` — text-only, no dedicated visual treatment; **copy
  itself has drifted and is now stale**: `dashboard_template.html:545`
  reads "AI analysis isn't run for every ticker yet — currently limited
  to a small flagship set while the model is being refined," but
  `config.json` shows `flagship_tickers` is already the full 30-ticker
  watchlist (confirmed identical to `watchlist`, per `PRODUCT.md`'s own
  "Decisions locked in") — this empty state is describing a limitation
  that no longer exists. `stock_template.html`'s equivalent already says
  something different: "AI analysis isn't available for this ticker."
- Ad hoc inline-styled loading placeholders (`docs/index.html`: "Loading
  tracked companies…", "Loading signal history…") — not a class at all,
  a one-off `style="text-align:center;padding:60px 0;..."` written twice
  with no shared definition.
- **Phase 1 target:** one `.empty-state` / `.loading-state` component
  with consistent sizing, and the stale copy fixed as part of the same
  pass (ties to Phase 4B).

## Chart engine
- `buildTimeframeChart()` / `selectTimeframe()` / axis-tick generation —
  `dashboard_template.html`'s original, explicitly commented as "ported
  verbatim" into `stock_template.html` and `sentiment_template.html`.
  The single largest block of duplicated JS on the site.

## Auth / account UI
- Full login/signup modal + personal watchlist grid: `dashboard_template.html`
  (27 references), partial copy in `sentiment_template.html` (15
  references), **absent entirely** from `stock_template.html` (0
  references, not even a `nav-auth` stub). This is Phase 3's problem
  directly — cataloged here because it's also a component-duplication
  problem, not just a product-decision problem.

## What this means for Phase 1

Every entry above converges on the same fix: a shared partial per
component (nav, score badge, pillar dial, divergence badge, card, empty/
loading state, chart engine, auth block), included at generation time
via the Jinja2 step agreed for Phase 1, each with one canonical
implementation instead of 2-4 hand-copied ones. `design/tokens.css`
(this same Phase 0 pass) is the token layer every one of these
components should pull from rather than hardcoding values locally.
