"""
Sentiment scoring using VADER, tuned slightly for retail-trading slang
(VADER's base lexicon doesn't know "moon", "bagholder", etc.).
Runs fully offline — no API key or network call needed for scoring itself.
"""

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()

# Retail-trading slang not in VADER's default lexicon.
# Scale is roughly -4 (very negative) to +4 (very positive).
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


def score_text(text: str) -> float:
    """Returns a compound sentiment score from -1 (very bearish) to +1
    (very bullish)."""
    if not text or not text.strip():
        return 0.0
    return _analyzer.polarity_scores(text)["compound"]


def label_for_score(score: float) -> str:
    if score >= 0.35:
        return "Bullish"
    if score >= 0.1:
        return "Leaning Bullish"
    if score <= -0.35:
        return "Bearish"
    if score <= -0.1:
        return "Leaning Bearish"
    return "Neutral"


def score_message(msg: dict) -> float:
    """Score a StockTwits message. If the author self-tagged sentiment
    (Bullish/Bearish), that's weighted heavily since it's a direct signal;
    it's blended with VADER on the text for nuance. Untagged messages fall
    back to VADER alone."""
    body = msg.get("body", "") or ""
    vader_score = score_text(body)

    entities = msg.get("entities") or {}
    sentiment = entities.get("sentiment")
    tagged = sentiment.get("basic") if sentiment else None

    if tagged == "Bullish":
        return 0.7 * 0.6 + 0.3 * vader_score
    if tagged == "Bearish":
        return 0.7 * -0.6 + 0.3 * vader_score
    return vader_score


def classify_message(msg: dict) -> str:
    """Classify a message as 'bullish', 'bearish', or 'neutral' — using the
    author's own tag when present (StockTwits), otherwise a VADER threshold
    on the text. Used for bull/bear counting, separate from the continuous
    score used for ranking."""
    entities = msg.get("entities") or {}
    sentiment = entities.get("sentiment")
    tagged = sentiment.get("basic") if sentiment else None
    if tagged == "Bullish":
        return "bullish"
    if tagged == "Bearish":
        return "bearish"

    s = score_text(msg.get("body", "") or "")
    if s >= 0.2:
        return "bullish"
    if s <= -0.2:
        return "bearish"
    return "neutral"
