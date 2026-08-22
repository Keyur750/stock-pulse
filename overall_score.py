"""
Overall Score Reset, Phase 1 — turns the four pillar 0-100 scores into
one deterministic, backtestable composite_score, instead of leaving "the
overall score" as the AI analyst's own free-form, temperature-sampled
judgment (analyst.py's ai_score — real analysis, but not a reproducible
function of the pillar data, and therefore not fit to be tracked against
forward returns the way PRODUCT.md's Phase 4 track-record work needs).

Pure function, deliberately isolated from every fetching/scoring module
already spread across main.py/fundamentals.py/wallstreet.py/market.py/
sentiment.py — this module only ever combines numbers those already
produce, nothing here calls out to yfinance/Gemini/anything network-
bound. See OVERALL_SCORE_RESET.md for the full research behind every
constant below (meta-analysis inverse-variance weighting, the forecast-
combination puzzle, Grinold-Kahn's Fundamental Law of Active Management,
AAII's sentiment-extremes research, PEAD/momentum/quality horizon
literature, Moody's scorecard-plus-notching precedent) — nothing here is
arbitrary, and none of the constants below should be re-derived from
memory without rereading that doc first.
"""

# Phase 1 prior (OVERALL_SCORE_RESET.md, Step 1), calibrated toward the
# user-confirmed 6-12 month forward-return target — NOT validated
# against real outcomes yet. Phase 2 (recalibrating these against
# data/signal_history.json) is explicitly blocked on data volume, same
# "forecast combination puzzle" discipline (Bates & Granger; Stock &
# Watson 2004) that already keeps every sibling pillar's own weights
# honestly labeled as unweighted placeholders before their own Phase
# 4-7 validation work — fitting weights on the ~week of signal_history
# that exists as of this writing would fit noise, not signal.
#
# Business and Market lead: both are the most horizon-matched pillars at
# 6-12 months (Piotroski's original F-Score result was a 1-year holding
# period; George & Hwang's 52-week-high effect — what market.py's
# `extension` category is built on — shows no long-term reversal at this
# horizon). Wall Street is demoted below what a shorter target would
# justify — its strongest, best-documented edge (EPS-revision Agreement/
# Magnitude, PEAD) is specifically shown to concentrate in the first
# post-announcement quarter and decay rapidly after, i.e. mostly played
# out before 6-12 months. Crowd is smallest — not because retail
# sentiment isn't real, independent information (it is: three
# corroborated sources, a real confidence engine), but because its own
# literature (AAII) shows a NON-monotonic, contrarian-at-extremes
# relationship to exactly this horizon ("above-average returns following
# extreme bearishness... over the following six to twelve months") — the
# wrong shape for a bigger linear weight to capture well. That relationship
# is instead captured by DIVERGENCE_ADJUSTMENT below.
BASE_WEIGHTS = {
    "business": 0.35,
    "market": 0.30,
    "wall_street": 0.20,
    "crowd": 0.15,
}

# Small, capped, asymmetric adjustment keyed to the Divergence Engine's
# classification (main.py's classify_divergence) — same structural role
# as Moody's own scorecard methodology (a weighted-average grid score,
# then a bounded, explicit notching adjustment for what the raw weights
# can't fully capture on their own), applied here to the already-named,
# literature-backed divergence patterns instead of analyst discretion.
# Deliberately asymmetric: the AAII research behind the two discounts is
# specifically about DOWNSIDE mean-reversion risk after a sentiment/price
# extreme, measured at this exact 6-12 month horizon — there's no
# equally strong literature that four-way agreement deserves an equally
# large reward, so the two boosts stay smaller than the two discounts.
# Never large enough to override what the weighted sum itself says.
DIVERGENCE_ADJUSTMENT = {
    "emerging_consensus": 4,
    "under_the_radar": 4,
    "fundamental_deterioration": -7,
    "retail_euphoria": -7,
}

# Fewer than this many real pillar reads isn't a composite at all — same
# "never fabricate" discipline as every pillar's own coverage handling,
# just a stricter threshold since a 1-pillar "composite" is meaningless
# by construction (classify_divergence's own pattern-matching already
# requires 3 of 4 for a *pattern* to fire; this is a separate, lower bar
# for the composite number to exist at all).
MIN_PILLARS_REQUIRED = 2

# A present pillar with no confidence reading at all (should be rare —
# every pillar's confidence fn returns None only when the pillar's own
# score is also None, which the "present" filter below already excludes)
# falls back to a neutral 50, the same "genuinely not assessable, not a
# proven bad signal" convention crowd_confidence()/wallstreet_confidence()
# already use for their own missing-signal terms — never a fabricated
# high or low value.
_NEUTRAL_CONFIDENCE = 50.0


def score_composite(pillar_scores: dict, confidences: dict | None = None,
                     divergence_pattern: str | None = None) -> dict | None:
    """Combines the four 0-100 pillar scores into one deterministic
    composite_score, confidence-weighted (meta-analysis-style precision
    weighting: each present pillar's BASE_WEIGHTS share is scaled by how
    much to trust it for THIS ticker today, then renormalized) and
    adjusted for the Divergence Engine's classification (Step 4 of
    OVERALL_SCORE_RESET.md).

    pillar_scores: {"crowd", "wall_street", "business", "market"} each a
        0-100 score or None — same shape main.py's pillar_scores[ticker]
        already is.
    confidences: same four keys, each that pillar's own 0-100 confidence
        (crowd_confidence / wallstreet_confidence / business_confidence /
        market_confidence) or None. Optional — a missing dict or a
        missing/None entry for a present pillar falls back to
        _NEUTRAL_CONFIDENCE rather than excluding that pillar or crashing.
    divergence_pattern: one of classify_divergence's pattern keys, or
        None — looked up directly in DIVERGENCE_ADJUSTMENT (defaults to
        0 for an unrecognized/None key), not imported from main.py, so
        this module never depends on main.py and stays a pure,
        independently-testable function over already-computed values.

    Returns None if fewer than MIN_PILLARS_REQUIRED pillars are present
    — never a guessed value built from too little to be a real composite.
    Otherwise returns a dict carrying not just the final number but its
    full decomposition (per-pillar weighted contributions, the weights
    actually used, the adjustment applied) — OVERALL_SCORE_RESET.md's
    Phase 3 ("why did the score change") needs exactly this breakdown,
    and it costs nothing to return it now rather than rebuild it later."""
    confidences = confidences or {}
    present = {p: s for p, s in (pillar_scores or {}).items()
               if s is not None and p in BASE_WEIGHTS}
    if len(present) < MIN_PILLARS_REQUIRED:
        return None

    raw_weights = {}
    for p in present:
        conf = confidences.get(p)
        if conf is None:
            conf = _NEUTRAL_CONFIDENCE
        conf = max(0.0, min(100.0, conf))
        raw_weights[p] = BASE_WEIGHTS[p] * conf / 100.0

    weight_total = sum(raw_weights.values())
    if not weight_total:
        # Every present pillar came back with zero confidence -- possible
        # in principle, not expected in practice on real data, but never
        # divide by zero for it.
        return None

    weights = {p: w / weight_total for p, w in raw_weights.items()}
    contributions = {p: round(weights[p] * present[p], 2) for p in present}
    composite_raw = sum(contributions.values())

    adjustment = DIVERGENCE_ADJUSTMENT.get(divergence_pattern, 0)
    composite_score = round(max(0.0, min(100.0, composite_raw + adjustment)), 1)

    return {
        "composite_score": composite_score,
        # Coverage-based, same shape build_signal_snapshot() already uses
        # for its own per-ticker `confidence` field -- a starting point,
        # explicitly flagged in OVERALL_SCORE_RESET.md as upgradable
        # later (Step 5) to weight by each present pillar's own
        # confidence rather than just count them.
        "composite_confidence": round(100.0 * len(present) / len(BASE_WEIGHTS)),
        "coverage": len(present),
        "pillar_contributions": contributions,
        "weights_used": {p: round(w, 3) for p, w in weights.items()},
        "divergence_pattern": divergence_pattern,
        "divergence_adjustment": adjustment,
    }


def composite_confidence_label(score: float | None) -> str:
    """Site Redesign Reset, Phase 4 (research point 7): same High/Medium/
    Low/Unknown thresholds every sibling *_confidence_label() function
    already uses (crowd_confidence_label/wallstreet_confidence_label/
    market_confidence_label/business_confidence_label) -- one label
    scheme, not a second one invented for this specific number. Applies
    validly here even though composite_confidence is coverage-based
    (how many pillars contributed) rather than the sample-size/agreement
    quality the other four measure: both answer the same underlying
    question a label communicates -- how much to trust this score."""
    if score is None:
        return "Unknown"
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"
