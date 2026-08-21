"""
The analyst model — the synthesis layer that turns raw fundamentals,
retail sentiment, and news into one reasoned score and narrative, the way
a human analyst would. This is deliberately NOT a fixed formula: a
weighted-average score can't know that a company's growth is strong *for
its size*, or that a pending lawsuit matters more than a clean balance
sheet ratio. That kind of judgment needs an LLM reading the actual
context, not thresholds.

Uses Gemini's free API tier by default (no cost, no card required — see
README). The call is isolated in _call_model() so swapping to a paid
provider (Claude, GPT) later is a small, contained change, not a rewrite.
"""

import json
import re
import time

from llm_client import get_client, MODEL

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {
            "type": "string",
            "description": "Your private working-through BEFORE answering: what's actually "
                            "distinctive about this company right now (not generic sector "
                            "commentary), what specific named events/lawsuits/products/"
                            "competitors matter, and how the fundamentals/sentiment/news "
                            "agree or conflict. This is where you think out loud — the fields "
                            "below should be the *conclusions* of this reasoning, not a "
                            "restatement of the input numbers.",
        },
        "overall_score": {"type": "integer", "description": "0-100, overall investment-worthiness read"},
        "verdict": {"type": "string", "description": "One sharp, specific phrase — not generic. Bad: 'Strong company with some risk.' Good: 'Ad-driven cash machine funding a capex bet the market hasn't fully priced.'"},
        "summary": {"type": "string", "description": "3-5 sentences, written for a retail investor. Must include at least one specific named thing (a product, a competitor, a lawsuit, a segment) — not just growth/margin percentages restated in prose."},
        "bullish_factors": {"type": "array", "items": {"type": "string"}, "description": "4-6 reasons to be optimistic. Each must be a full sentence explaining WHY it matters, not a restated stat. Bad: '28% revenue growth.' Good: '28% revenue growth is unusually strong for a company already this large, suggesting the core ad business isn't maturing yet.'"},
        "bearish_factors": {"type": "array", "items": {"type": "string"}, "description": "4-6 reasons for caution, same rule — explain the mechanism, don't just restate a number."},
        "key_risks": {"type": "array", "items": {"type": "string"}, "description": "3-5 SPECIFIC named risks — an actual lawsuit, regulation, competitor, or execution dependency by name. Banned: generic phrases like 'regulatory scrutiny' or 'market risk' with nothing named. If you genuinely don't know a specific name, say what KIND of thing to watch for and why, don't fabricate a name."},
        "key_catalysts": {"type": "array", "items": {"type": "string"}, "description": "3-5 SPECIFIC upcoming or ongoing events that could move the stock, named concretely (a product launch, an earnings date, a segment inflection) — not vague 'continued growth.'"},
        "pillar_reads": {
            "type": "object",
            "description": "One short, specific read per pillar — what that source of judgment believes and why, not a restatement of its score.",
            "properties": {
                "crowd": {"type": "string", "description": "1-2 sentences: what retail chatter believes right now and why — name the actual theme (a product, a catalyst, a fear), not just 'bullish' or 'bearish.'"},
                "wall_street": {"type": "string", "description": "1-2 sentences: what Wall Street analysts think and why, referencing the actual rating/target data given. If coverage is thin or absent, say so plainly instead of inventing a view."},
                "business": {"type": "string", "description": "1-2 sentences: what the fundamentals actually show, in plain language — not a restatement of the category scores."},
                "market": {"type": "string", "description": "1-2 sentences: where the stock already sits relative to its own recent range and trend, and whether that means a bullish or bearish thesis is already priced in versus still fresh — this is the one pillar that's explicitly about context, not verdict."},
            },
            "required": ["crowd", "wall_street", "business", "market"],
        },
    },
    "required": ["reasoning", "overall_score", "verdict", "summary", "bullish_factors", "bearish_factors", "key_risks", "key_catalysts", "pillar_reads"],
}

PROMPT_TEMPLATE = """You are a senior equity research analyst — the kind whose notes \
institutional investors actually pay for, not a summary bot. You're writing for a retail \
investor who is smart but time-poor: they will immediately recognize and distrust generic \
filler ("strong fundamentals," "regulatory risk," "competitive pressure") because it could \
apply to literally any company. Your job is to say the specific thing that's actually true \
about THIS company right now.

Rules:
- Weigh numbers IN CONTEXT. A "moderate" growth rate can be excellent for a company this \
size, or weak for a smaller one — reason about what's normal for a company of this scale \
and sector, don't just react to the raw percentage.
- Never just restate a number you were given — explain the mechanism behind it. Not "margins \
are 34.8%" but what that margin implies (pricing power? a temporary cost cut? scale?).
- Use your knowledge of this specific company's well-known, named situation — actual \
lawsuits, actual product lines, actual competitors, actual management decisions — the way an \
informed analyst would. If something might be time-sensitive or you're not fully certain \
it's still current, say so ("as of my knowledge" / "reportedly") rather than stating it as \
verified fact — but a hedge is not an excuse to be vague. Name the specific thing even while \
hedging on its current status.
- Do not invent specific numbers (dollar figures, dates, percentages) that aren't given to \
you in the data below or that you're not confident are well-established public knowledge.
- Give a genuinely balanced view — real bullish AND real bearish factors, not cheerleading. \
If the data is mixed, say so plainly rather than splitting the difference vaguely.
- This is analysis for education, not a buy/sell recommendation — avoid instructive \
language like "you should buy."
- Fill "reasoning" first and actually use it to think — don't write it as an afterthought \
summary of the other fields.
- For "pillar_reads.market" specifically: explicitly reason about whether the bullish or \
bearish case is already reflected in where the stock is trading relative to its own recent \
range — a stock already up sharply and near its highs needs different framing than one that \
hasn't moved, even if the underlying thesis is identical. This is the core reason this pillar \
exists — don't skip the reasoning and just restate the numbers.

TICKER: {ticker} — {name} ({sector})

FUNDAMENTALS / BUSINESS (from live financial data, scored 0-100 per category):
{fundamentals_block}

RETAIL SENTIMENT / CROWD (from StockTwits/Reddit chatter today):
{sentiment_block}

WALL STREET / ANALYST CONSENSUS (from live analyst rating and price-target data):
{wallstreet_block}

MARKET CONTEXT (price relative to its own recent range — use this to judge what's already \
priced in, do not reason about valuation in a vacuum):
{price_block}
{market_block}

RECENT NEWS HEADLINES (may be sparse — use general knowledge to fill context, but flag what's from these headlines vs. what's background knowledge):
{news_block}

Respond with the synthesis described above."""


def _fmt_balance_sheet_detail(fundamentals, bs_detail):
    if not bs_detail:
        return "not available"
    if bs_detail.get("method") == "altman_z_double_prime":
        z = bs_detail.get("z_score")
        zone = "safe zone" if z > 2.6 else ("distress zone" if z < 1.1 else "grey zone")
        return f"Altman Z''-Score {z} ({zone} — bankruptcy-risk composite from working capital, retained earnings, EBIT & liabilities relative to assets/market cap)"
    return (f"debt/equity {fundamentals.get('debt_to_equity')}, current ratio {fundamentals.get('current_ratio')} "
            f"(bank/lender-style balance sheet — no reported working capital or EBIT, so Altman Z'' isn't computable; scored on the legacy debt/liquidity blend instead)")


def _fmt_valuation_detail(val_detail):
    if not val_detail:
        return ""
    peg = val_detail.get("peg")
    r40 = val_detail.get("rule_of_40")
    if peg:
        return f" (PEG ratio {peg['peg']} — growth-adjusted; Lynch framework: <1.0 undervalued vs. growth, 1.0-2.0 reasonable, >2.0 overvalued)"
    if r40:
        return f" (Rule of 40: revenue growth + margin = {r40['rule_of_40']} — supplementary read for a name with no P/E to score, 40+ is the healthy-growth baseline)"
    return ""


def _fmt_fundamentals(fundamentals, fscore):
    if not fundamentals or not fscore:
        return "Not available."
    cats = fscore.get("categories", {})
    # Coverage denominator derived from the categories dict itself, not
    # hardcoded -- Business pillar Phase 2 added a 6th category (trend)
    # and more will follow; a fixed "/5" would silently go stale.
    sector_note = ("scored sector-relative vs. industry peers (Damodaran benchmarks)"
                   if fscore.get("sector_benchmark_matched")
                   else "no industry benchmark match — scored on fixed global breakpoints")
    lines = [
        f"- Overall fundamentals score: {fscore.get('overall')}/100 (data coverage: {fscore.get('coverage')}/{len(cats)} categories; growth/profitability/valuation {sector_note})",
        f"- Growth score: {cats.get('growth')}/100 — revenue growth {_pct(fundamentals.get('revenue_growth'))}, earnings growth {_pct(fundamentals.get('earnings_growth'))}",
        f"- Profitability score: {cats.get('profitability')}/100 — profit margin {_pct(fundamentals.get('profit_margin'))}, operating margin {_pct(fundamentals.get('operating_margin'))}, ROE {_pct(fundamentals.get('return_on_equity'))} (ROE discounted when leverage runs well above industry peers — DuPont logic, so a high ROE built mostly on debt scores lower than the same ROE built on margin/efficiency)",
        f"- Cash flow score: {cats.get('cash_flow')}/100 — FCF margin {_pct(fundamentals.get('fcf_margin'))}",
        f"- Balance sheet score: {cats.get('balance_sheet')}/100 — {_fmt_balance_sheet_detail(fundamentals, fscore.get('balance_sheet_detail'))}",
        f"- Valuation score: {cats.get('valuation')}/100 — forward P/E {fundamentals.get('forward_pe')}, trailing P/E {fundamentals.get('trailing_pe')}, P/S {fundamentals.get('price_to_sales')}{_fmt_valuation_detail(fscore.get('valuation_detail'))}",
        f"- Trend score: {cats.get('trend')}/100 — year-over-year direction across revenue, margins, leverage & dilution (Piotroski-inspired; a rising score means the business is getting healthier, not just currently healthy)",
        f"- Earnings quality score: {cats.get('earnings_quality')}/100 — net income vs. operating cash flow (Sloan accrual check; a low score means reported profit is running ahead of actual cash generation, a real warning sign even when every other score looks strong; None for banks/lenders where operating cash flow isn't comparable under GAAP — don't read a missing score here as a red flag)",
        f"- Market cap: {fundamentals.get('market_cap')}",
    ]
    return "\n".join(lines)


def _pct(v):
    return f"{v * 100:.1f}%" if isinstance(v, (int, float)) else "n/a"


def _fmt_sentiment(sentiment):
    if not sentiment or not sentiment.get("mentions"):
        return "No meaningful retail chatter recorded today."
    lines = [
        f"- {sentiment['mentions']} messages today, {sentiment.get('bullish_pct', 0)}% bullish / {sentiment.get('bearish_pct', 0)}% bearish",
        f"- Overall label: {sentiment.get('label')}",
    ]
    examples = sentiment.get("examples") or []
    if examples:
        lines.append("- Example real messages from retail chatter:")
        for ex in examples[:3]:
            lines.append(f"  \"{ex.get('title', '')}\"")
    return "\n".join(lines)


def _signed_pct(v):
    return f"{v:+.1f}%" if isinstance(v, (int, float)) else "n/a"


def _fmt_revision_detail(label, detail):
    if not detail:
        return f"- {label}: not available (no EPS-estimate-revision activity in the last 30 days)"
    ratios_or_pcts = detail.get("net_ratios") or detail.get("pct_of_price") or {}
    parts = [f"{p}={v:+.2f}" if v is not None else f"{p}=n/a" for p, v in ratios_or_pcts.items()]
    return f"- {label}: {detail['score']}/100 ({', '.join(parts)})"


def _fmt_rating_momentum(detail):
    if not detail:
        return "- Rating momentum (dated upgrade/downgrade activity, recency-weighted): not available (no rating changes in the lookback window — a real, meaningful state, not a data gap; a stale or already-fully-priced-in consensus reads as flat momentum here, not missing data)"
    return (f"- Rating momentum (dated upgrade/downgrade activity, recency-weighted): {detail['score']}/100 "
            f"(net signal {detail['net_momentum_shrunk']:+.2f} from {detail['included_actions']} rating "
            f"change(s) in the lookback window, weighted toward more recent and bolder moves)")


def _fmt_wallstreet(wallstreet, wscore):
    if not wallstreet or not wscore or not wscore.get("overall"):
        return "Not available — little or no analyst coverage."
    # Coverage denominator derived from the categories dict itself, not
    # hardcoded -- Wall Street pillar Phase 2 added revision_agreement/
    # revision_magnitude and Phase 3 replaced revision_trend with
    # rating_momentum; a fixed "/3" would silently go stale, the same
    # bug Business pillar Phase 2 already had to fix once for
    # _fmt_fundamentals.
    cats = wscore.get("categories", {})
    lines = [
        f"- Overall Wall Street score: {wscore.get('overall')}/100 (data coverage: {wscore.get('coverage')}/{len(cats)} categories)",
        f"- Consensus rating: {wallstreet.get('recommendation_key', 'n/a')} "
        f"(mean {wallstreet.get('recommendation_mean')} on a 1=Strong Buy...5=Strong Sell scale), "
        f"from {wallstreet.get('num_analysts')} analysts",
        f"- Mean price target: ${wallstreet.get('target_mean_price')} "
        f"({_signed_pct(wallstreet.get('upside_pct'))} vs current price)",
        f"- Analyst tone shift over roughly the last 3 months: "
        f"{_signed_pct(wallstreet.get('revision_delta_pct'))} change in the bullish-rated share of coverage",
        _fmt_revision_detail("EPS-estimate revision agreement (net share of analysts revising up vs. down, last 30 days)",
                              wscore.get("revision_agreement_detail")),
        _fmt_revision_detail("EPS-estimate revision magnitude (size of the estimate change, scaled by price, last 30 days)",
                              wscore.get("revision_magnitude_detail")),
        _fmt_rating_momentum(wscore.get("rating_momentum_detail")),
    ]
    return "\n".join(lines)


def _fmt_market(market, mscore):
    if not market or not mscore or not mscore.get("overall"):
        return "Not available."
    # Coverage denominator derived from the categories dict itself, not
    # hardcoded -- Market pillar Phase 1 proactively fixed this the same
    # staleness bug _fmt_fundamentals and _fmt_wallstreet each had to fix
    # once, rather than waiting to discover it again once a future phase
    # adds a 4th/5th category.
    cats = mscore.get("categories", {})
    lines = [
        f"- Overall market/momentum score: {mscore.get('overall')}/100 (data coverage: {mscore.get('coverage')}/{len(cats)} categories)",
        f"- {_signed_pct(market.get('pct_from_52w_high'))} from its 52-week high, "
        f"{_signed_pct(market.get('pct_from_52w_low'))} from its 52-week low",
        f"- {_signed_pct(market.get('pct_from_50d_avg'))} vs its 50-day average, "
        f"{_signed_pct(market.get('pct_from_200d_avg'))} vs its 200-day average",
        f"- Daily realized volatility: {market.get('daily_volatility_pct')}% (higher = choppier trading)",
    ]
    return "\n".join(lines)


def _fmt_price(price):
    if not price or price.get("price") is None:
        return "Not available."
    lines = [f"- Current price: ${price['price']:.2f}", f"- Today's change: {price.get('change_pct', 0):+.2f}%"]
    period_chg = price.get("period_change_pct")
    period_days = price.get("period_days")
    if period_chg is not None and period_days:
        lines.append(f"- Change over the last {period_days} days: {period_chg:+.1f}%")
    return "\n".join(lines)


def _fmt_news(news_items):
    if not news_items:
        return "No specific headlines matched to this ticker today."
    lines = []
    for n in news_items[:10]:
        lines.append(f"- [{n.get('source', '')}] {n.get('title', '')}")
    return "\n".join(lines)


def _extract_retry_delay(exc, default=60):
    """The API returns a suggested wait time in its error payload on 429s
    (e.g. "Please retry in 54.3s"). Use it when present so we wait exactly
    as long as needed instead of guessing."""
    m = re.search(r"retry in (\d+(?:\.\d+)?)s", str(exc))
    return float(m.group(1)) + 2 if m else default


def analyze_stock(ticker: str, name: str, sector: str, fundamentals: dict | None,
                   fscore: dict | None, sentiment: dict | None, price: dict | None,
                   news_items: list, wallstreet: dict | None = None, wscore: dict | None = None,
                   market: dict | None = None, mscore: dict | None = None) -> dict | None:
    """Runs one ticker through the analyst model. Returns the parsed
    response dict, or None if no API key is configured or the call fails
    after one retry (never raises — a failed AI analysis shouldn't break
    the whole run). Retries once on rate-limit (429) errors, since the
    free tier's per-minute limit is easy to brush against across several
    tickers in one run."""
    client = get_client()
    if client is None:
        return None

    prompt = PROMPT_TEMPLATE.format(
        ticker=ticker, name=name or ticker, sector=sector or "unknown sector",
        fundamentals_block=_fmt_fundamentals(fundamentals, fscore),
        sentiment_block=_fmt_sentiment(sentiment),
        wallstreet_block=_fmt_wallstreet(wallstreet, wscore),
        price_block=_fmt_price(price),
        market_block=_fmt_market(market, mscore),
        news_block=_fmt_news(news_items),
    )

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": RESPONSE_SCHEMA,
                    "temperature": 0.4,
                    "max_output_tokens": 3000,
                },
            )
            return json.loads(response.text)
        except Exception as e:
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            if is_rate_limit and attempt == 0:
                wait = _extract_retry_delay(e)
                print(f"  [analyst] {ticker} rate-limited, waiting {wait:.0f}s and retrying once...")
                time.sleep(wait)
                continue
            print(f"  [analyst] {ticker} analysis failed: {type(e).__name__}: {e}")
            return None
    return None
