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
import os
import re
import time

# Deliberately pinned, not "-latest". The "-latest" aliases silently
# repoint to newer models over time — gemini-flash-latest moved to
# gemini-3.6-flash mid-project, which turned out to have a free-tier cap
# of just 20 requests/day (vs. flash-lite's much larger allowance),
# and quietly zeroed out our quota. Pin to a specific model with known
# quota headroom; re-evaluate deliberately, not by surprise.
MODEL = "gemini-3.1-flash-lite"

_client = None
_client_checked = False

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
    },
    "required": ["reasoning", "overall_score", "verdict", "summary", "bullish_factors", "bearish_factors", "key_risks", "key_catalysts"],
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

TICKER: {ticker} — {name} ({sector})

FUNDAMENTALS (from live financial data, scored 0-100 per category):
{fundamentals_block}

RETAIL SENTIMENT (from StockTwits/Reddit chatter today):
{sentiment_block}

RECENT PRICE ACTION (do not reason about valuation in a vacuum — factor in whether recent \
strength/weakness already prices in what you're about to say):
{price_block}

RECENT NEWS HEADLINES (may be sparse — use general knowledge to fill context, but flag what's from these headlines vs. what's background knowledge):
{news_block}

Respond with the synthesis described above."""


def _get_client():
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("  [analyst] GEMINI_API_KEY not set — skipping AI analysis.")
        return None
    try:
        from google import genai
    except ImportError:
        print("  [analyst] google-genai not installed — skipping AI analysis.")
        return None
    try:
        _client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"  [analyst] failed to init Gemini client: {type(e).__name__}: {e}")
        _client = None
    return _client


def _fmt_fundamentals(fundamentals, fscore):
    if not fundamentals or not fscore:
        return "Not available."
    cats = fscore.get("categories", {})
    lines = [
        f"- Overall fundamentals score: {fscore.get('overall')}/100 (data coverage: {fscore.get('coverage')}/5 categories)",
        f"- Growth score: {cats.get('growth')}/100 — revenue growth {_pct(fundamentals.get('revenue_growth'))}, earnings growth {_pct(fundamentals.get('earnings_growth'))}",
        f"- Profitability score: {cats.get('profitability')}/100 — profit margin {_pct(fundamentals.get('profit_margin'))}, operating margin {_pct(fundamentals.get('operating_margin'))}, ROE {_pct(fundamentals.get('return_on_equity'))}",
        f"- Cash flow score: {cats.get('cash_flow')}/100 — FCF margin {_pct(fundamentals.get('fcf_margin'))}",
        f"- Balance sheet score: {cats.get('balance_sheet')}/100 — debt/equity {fundamentals.get('debt_to_equity')}, current ratio {fundamentals.get('current_ratio')}",
        f"- Valuation score: {cats.get('valuation')}/100 — forward P/E {fundamentals.get('forward_pe')}, trailing P/E {fundamentals.get('trailing_pe')}, P/S {fundamentals.get('price_to_sales')}",
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
                   news_items: list) -> dict | None:
    """Runs one ticker through the analyst model. Returns the parsed
    response dict, or None if no API key is configured or the call fails
    after one retry (never raises — a failed AI analysis shouldn't break
    the whole run). Retries once on rate-limit (429) errors, since the
    free tier's per-minute limit is easy to brush against across several
    tickers in one run."""
    client = _get_client()
    if client is None:
        return None

    prompt = PROMPT_TEMPLATE.format(
        ticker=ticker, name=name or ticker, sector=sector or "unknown sector",
        fundamentals_block=_fmt_fundamentals(fundamentals, fscore),
        sentiment_block=_fmt_sentiment(sentiment),
        price_block=_fmt_price(price),
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
