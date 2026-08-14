"""
Message-level sentiment for retail chatter (StockTwits/Reddit).

Two-tier approach, in order of trust:
1. Self-tagged messages (StockTwits lets a poster tag their own message
   Bullish/Bearish) — this is ground truth, a trader stating their own
   stance, and is weighted accordingly.
2. Everything else is read by an LLM (batched, one call per ticker, same
   "batch before you pay" pattern as news_ranker.py) rather than a
   lexicon tool — an LLM can read sarcasm, negation, and financial slang
   in context, which a keyword-matcher fundamentally can't. VADER is kept
   only as an offline fallback for when the LLM is unavailable or a call
   fails, so the pipeline never breaks.

This replaced a pure-VADER approach after live testing showed it was
structurally biased: self-tagged messages were being averaged in with a
lexicon-scored majority that clustered near zero, diluting even a
strongly bearish-tagged population (e.g. PTON at 13 bear vs 4 bull tags)
back to a "Neutral" label. See PRODUCT.md for the full writeup.
"""

import json
import re
import time

from llm_client import get_client, MODEL
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()

# Retail-trading slang not in VADER's default lexicon — only used by the
# offline fallback path now, not the primary LLM path.
_SLANG = {
    "moon": 3.0, "mooning": 3.0, "rocket": 2.5, "🚀": 3.0,
    "tendies": 2.0, "bullish": 2.5, "calls": 1.0, "long": 0.8,
    "buy the dip": 1.5, "diamond hands": 1.5, "hodl": 1.0,
    "undervalued": 1.5, "breakout": 1.5, "squeeze": 1.5,
    "bearish": -2.5, "puts": -1.0, "short": -0.8, "dump": -2.0,
    "dumping": -2.0, "bagholder": -2.5, "bagholders": -2.5,
    "overvalued": -1.5, "rug pull": -3.0, "crash": -2.5,
    "bankruptcy": -3.0, "delisted": -2.5, "scam": -2.5,
    "dead cat bounce": -1.5, "top signal": -1.0,
}
_analyzer.lexicon.update(_SLANG)

# Tagged messages are direct, stated opinions — trusted more than an
# inferred read of untagged text, both in per-message magnitude and in
# how heavily they count toward a ticker's aggregate score.
TAG_SCORE = {"Bullish": 0.6, "Bearish": -0.6}
TAGGED_WEIGHT = 2.0
UNTAGGED_WEIGHT = 1.0
LLM_SENTIMENT_SCORE = {"bullish": 0.4, "bearish": -0.4, "neutral": 0.0}

# A weighted average of bounded per-message scores can never exceed the
# most extreme individual score — so avg_sentiment is mathematically
# bounded to [-0.6, +0.6], not the [-1, +1] a naive normalization would
# assume. Anything rescaling avg_sentiment to a 0-100 score should divide
# by this, not by 1.0, or it silently compresses the real range into
# ~20-80 and never reaches the ends of the scale.
MAX_SCORE_MAGNITUDE = max(abs(v) for v in TAG_SCORE.values())

# Provisional — set from the shape of the new scoring formula, not yet
# calibrated against a real distribution of live results the way the
# Wall Street pillar's thresholds were. Revisit once a few days of
# LLM-scored data exist to look at.
BULLISH_THRESHOLD = 0.30
LEANING_BULLISH_THRESHOLD = 0.10
BEARISH_THRESHOLD = -0.30
LEANING_BEARISH_THRESHOLD = -0.10

SENTIMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "The number of the message this classification is for."},
                    "sentiment": {
                        "type": "string",
                        "enum": ["bullish", "bearish", "neutral"],
                        "description": "The poster's stance on the stock: bullish (expects it to go up / positive view), bearish (expects it to go down / negative view), or neutral (no clear directional opinion — a question, a fact, banter, or a joke/meme with no real stance).",
                    },
                },
                "required": ["index", "sentiment"],
            },
        },
    },
    "required": ["items"],
}

PROMPT = """You are reading retail trader chat about {ticker} from StockTwits/Reddit. For each \
numbered message below, classify the poster's stance on the stock as bullish, bearish, or \
neutral.

- bullish = they expect the stock to go up, or hold a positive view of it
- bearish = they expect the stock to go down, or hold a negative view of it
- neutral = no clear directional opinion — a question, a factual statement, off-topic banter, \
or a joke/meme with no real stance

Read for actual meaning, not just keywords — watch for sarcasm ("yeah great quarter 🙄") and \
negation ("not bullish on this at all"). These are casual, slang-heavy retail trader messages,
not formal writing.

MESSAGES:
{messages_block}

Respond with a classification for every numbered message, using its number as "index"."""


def score_text(text: str) -> float:
    """VADER compound score, -1 (very bearish) to +1 (very bullish).
    Offline fallback path only — see module docstring."""
    if not text or not text.strip():
        return 0.0
    return _analyzer.polarity_scores(text)["compound"]


def label_for_score(score: float) -> str:
    if score >= BULLISH_THRESHOLD:
        return "Bullish"
    if score >= LEANING_BULLISH_THRESHOLD:
        return "Leaning Bullish"
    if score <= BEARISH_THRESHOLD:
        return "Bearish"
    if score <= LEANING_BEARISH_THRESHOLD:
        return "Leaning Bearish"
    return "Neutral"


def tag_of(msg: dict):
    entities = msg.get("entities") or {}
    sentiment = entities.get("sentiment") or {}
    return sentiment.get("basic")


def _extract_retry_delay(exc, default=45):
    m = re.search(r"retry in (\d+(?:\.\d+)?)s", str(exc))
    return float(m.group(1)) + 2 if m else default


def _fallback_classify(text: str) -> str:
    s = score_text(text)
    if s >= 0.2:
        return "bullish"
    if s <= -0.2:
        return "bearish"
    return "neutral"


def classify_messages_llm(ticker: str, messages: list) -> dict:
    """One batched Gemini call classifying every message in one shot —
    same principle as news_ranker.py. Returns {index: 'bullish'|'bearish'|
    'neutral'}, or {} if no client is available or the call fails (caller
    falls back to VADER per-message, not silently skips scoring)."""
    if not messages:
        return {}

    client = get_client()
    if client is None:
        return {}

    messages_block = "\n".join(
        f"{i}. {(m.get('body') or '').strip()[:280]}" for i, m in enumerate(messages)
    )
    prompt = PROMPT.format(ticker=ticker, messages_block=messages_block)

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": SENTIMENT_SCHEMA,
                    "temperature": 0.1,
                    "max_output_tokens": 2000,
                },
            )
            items = json.loads(response.text)["items"]
            return {d["index"]: d["sentiment"] for d in items}
        except Exception as e:
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            if is_rate_limit and attempt == 0:
                wait = _extract_retry_delay(e)
                print(f"  [sentiment] {ticker} rate-limited, waiting {wait:.0f}s and retrying once...")
                time.sleep(wait)
                continue
            print(f"  [sentiment] {ticker} LLM classification failed: {type(e).__name__}: {e}")
            return {}
    return {}


def classify_and_score_messages(ticker: str, messages: list) -> list:
    """Classifies every message as bullish/bearish/neutral and assigns a
    score + weight, preferring the author's own tag (ground truth) when
    present and an LLM read of the text otherwise — falling back to VADER
    only if the LLM is unavailable or fails. Returns the same messages
    with `_sentiment`, `_score`, and `_weight` attached."""
    tagged, untagged = [], []
    for m in messages:
        tag = tag_of(m)
        if tag in TAG_SCORE:
            m["_sentiment"] = tag.lower()
            m["_score"] = TAG_SCORE[tag]
            m["_weight"] = TAGGED_WEIGHT
            tagged.append(m)
        else:
            untagged.append(m)

    if untagged:
        llm_results = classify_messages_llm(ticker, untagged)
        for i, m in enumerate(untagged):
            sentiment = llm_results.get(i) or _fallback_classify(m.get("body") or "")
            m["_sentiment"] = sentiment
            m["_score"] = LLM_SENTIMENT_SCORE.get(sentiment, 0.0)
            m["_weight"] = UNTAGGED_WEIGHT

    return tagged + untagged


def weighted_average(scored_messages: list) -> float:
    total_weight = sum(m["_weight"] for m in scored_messages)
    if not total_weight:
        return 0.0
    return sum(m["_score"] * m["_weight"] for m in scored_messages) / total_weight


MARKET_INSIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "insight": {
            "type": "string",
            "description": "One to two sentences summarizing today's real crowd sentiment picture across the covered securities — overall direction, which specific securities are driving it, and whether the shift is broad or narrow across the group. Factual and specific, referencing only the real data given. No hype, no generic filler, no speculation about causes not shown in the data.",
        },
    },
    "required": ["insight"],
}

INSIGHT_PROMPT = """You are writing a one-to-two sentence summary of today's retail crowd \
sentiment picture for a financial intelligence dashboard, based only on the real data below. \
Name the actual securities driving the picture — don't generalize. No hype, no filler, no \
speculation about causes not shown in the data. If most securities show little day-over-day \
change, say so plainly instead of manufacturing drama.

TODAY'S SENTIMENT SNAPSHOT (ticker: label, score/100, change vs yesterday, mentions in 24h):
{snapshot_block}

Write the summary now."""


def build_market_insight(watchlist_grid: list) -> str | None:
    """One real LLM call per day synthesizing the day's aggregate crowd
    sentiment into a short natural-language summary — real breadth counts
    and real movers as input, not a fabricated narrative. Returns None if
    the LLM is unavailable or the call fails, so the page can show an
    honest empty state rather than templated text pretending to be
    AI-written."""
    rows = [r for r in watchlist_grid if r.get("avg_sentiment") is not None]
    if not rows:
        return None

    client = get_client()
    if client is None:
        return None

    lines = []
    for r in rows:
        score = round((r["avg_sentiment"] / MAX_SCORE_MAGNITUDE + 1) * 50)
        delta_txt = ""
        if r.get("delta") is not None:
            delta_score = r["delta"] * (50 / MAX_SCORE_MAGNITUDE)
            delta_txt = f", change {delta_score:+.1f} vs yesterday"
        lines.append(f"{r['ticker']}: {r.get('label', 'Neutral')}, {score}/100{delta_txt}, {r.get('mentions', 0)} mentions")
    prompt = INSIGHT_PROMPT.format(snapshot_block="\n".join(lines))

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": MARKET_INSIGHT_SCHEMA,
                "temperature": 0.25,
                "max_output_tokens": 300,
            },
        )
        return json.loads(response.text)["insight"]
    except Exception as e:
        print(f"  [sentiment] market insight generation failed: {type(e).__name__}: {e}")
        return None
