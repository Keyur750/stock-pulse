"""
Phase 4 (crowd score engine) validation step -- NOT part of the daily
pipeline, run by hand.

Question this answers: does FinBERT actually read retail chat well enough
to be trusted as a confidence signal in the crowd pillar, or does it hit
the same "reads tone, not meaning" failure real-world research found on
financial headlines (see PRODUCT.md-style research notes from this
session -- FinBERT scored 16.8% accuracy on genuine positive catalysts in
a 991-headline study, vs. 82.7% on neutral)?

Undertow has something those headline studies didn't: real self-tagged
ground truth already flowing through the pipeline -- StockTwits lets
posters tag their own message Bullish/Bearish (sentiment.py's TAG_SCORE).
This script pulls live tagged messages across the watchlist, strips the
tag, and asks three independent readers to guess it back:

1. FinBERT (ProsusAI/finbert) -- the candidate being evaluated.
2. Gemini (sentiment.py's existing classify_messages_llm) -- the
   pipeline's current untagged-message reader, for a same-data baseline.
3. VADER (sentiment.py's score_text) -- the old fallback, for a floor.

Reports per-class accuracy (bullish/bearish, not just overall -- a model
that's great on one class and terrible on the other looks fine on an
aggregate number and isn't) and whether FinBERT's own confidence score
tracks its actual correctness, which is the specific property Phase 4
would need if FinBERT's probability were used as a per-message weight.

Usage: python validate_finbert.py [--tickers N] [--max-per-ticker N]
"""

import argparse
import sys
import time
from collections import defaultdict

from stocktwits import fetch_symbol_stream
from sentiment import tag_of, score_text, classify_messages_llm

import json
with open("config.json", encoding="utf-8") as f:
    WATCHLIST = json.load(f)["watchlist"]


def fetch_tagged_sample(tickers: list, max_age_hours: float = 48.0,
                         hard_limit: int = 400) -> list:
    """Real tagged (ground-truth) messages across the given tickers.
    Widened to 48h (vs. the pipeline's 24h) purely to get a large enough
    tagged sample in one run -- tags are ~25% of volume, so 24h on a
    handful of tickers risks a thin, noisy sample."""
    tagged = []
    for i, sym in enumerate(tickers):
        print(f"  [{i+1}/{len(tickers)}] fetching {sym}...", file=sys.stderr)
        messages = fetch_symbol_stream(sym, max_age_hours=max_age_hours, hard_limit=hard_limit)
        for m in messages:
            tag = tag_of(m)
            if tag in ("Bullish", "Bearish"):
                m["_true_label"] = tag.lower()
                m["_ticker"] = sym
                tagged.append(m)
    return tagged


def load_finbert():
    from transformers import pipeline
    print("  loading ProsusAI/finbert...", file=sys.stderr)
    return pipeline("sentiment-analysis", model="ProsusAI/finbert", revision="main")


def run_finbert(clf, messages: list, batch_size: int = 16) -> list:
    """Returns list of (label, confidence) aligned to `messages`. FinBERT's
    labels are positive/negative/neutral -- mapped to bullish/bearish/
    neutral to compare against the bullish/bearish ground truth."""
    texts = [(m.get("body") or "")[:512] for m in messages]
    label_map = {"positive": "bullish", "negative": "bearish", "neutral": "neutral"}
    out = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        results = clf(batch, truncation=True)
        for r in results:
            out.append((label_map.get(r["label"], "neutral"), r["score"]))
    return out


def run_gemini(messages: list, max_batch: int = 50) -> list:
    """Reuses the pipeline's real untagged-message path -- same model,
    same batching *shape* as production. Critically, chunks each ticker's
    messages to max_batch (production caps the whole sample at 60 via
    sentiment_sample_size before this is ever called) -- sending Gemini an
    uncapped batch overflows max_output_tokens and truncates the JSON
    response mid-string, which silently defaults every message in that
    call to 'neutral' rather than raising. That's a test-harness bug, not
    a real reading of Gemini's quality, so it must not happen here."""
    by_ticker = defaultdict(list)
    for i, m in enumerate(messages):
        by_ticker[m["_ticker"]].append((i, m))

    out = [None] * len(messages)
    for ticker, items in by_ticker.items():
        for start in range(0, len(items), max_batch):
            chunk = items[start:start + max_batch]
            idxs, msgs = zip(*chunk)
            results = classify_messages_llm(ticker, list(msgs))
            for local_i, global_i in enumerate(idxs):
                out[global_i] = results.get(local_i, "neutral")
            time.sleep(3.0)  # matches config.json's sentiment_call_sleep_seconds
    return out


def run_vader(messages: list) -> list:
    out = []
    for m in messages:
        s = score_text(m.get("body") or "")
        if s >= 0.2:
            out.append("bullish")
        elif s <= -0.2:
            out.append("bearish")
        else:
            out.append("neutral")
    return out


def report(name: str, true_labels: list, pred_labels: list, confidences: list = None):
    print(f"\n=== {name} ===")
    n = len(true_labels)
    correct = sum(1 for t, p in zip(true_labels, pred_labels) if t == p)
    print(f"Overall accuracy: {correct}/{n} = {correct/n:.1%}")

    # Per-class: of the messages truly tagged X, how often did the
    # classifier say X? This is the number the headline study showed
    # can hide a bad model -- 82.7% neutral / 16.8% positive averages out
    # to something that looks okay in aggregate.
    for cls in ("bullish", "bearish"):
        idxs = [i for i, t in enumerate(true_labels) if t == cls]
        if not idxs:
            continue
        cls_correct = sum(1 for i in idxs if pred_labels[i] == cls)
        print(f"  True {cls:8s} (n={len(idxs):4d}): predicted correctly {cls_correct}/{len(idxs)} = {cls_correct/len(idxs):.1%}")

    # Confusion matrix
    labels = ["bullish", "bearish", "neutral"]
    print("  Confusion matrix (rows=true, cols=predicted):")
    print("           " + "".join(f"{l:>10s}" for l in labels))
    for t in ("bullish", "bearish"):
        row = [sum(1 for tt, pp in zip(true_labels, pred_labels) if tt == t and pp == l) for l in labels]
        print(f"  {t:9s}" + "".join(f"{v:>10d}" for v in row))

    if confidences:
        # Does FinBERT's own confidence track whether it was actually
        # right? This is the property Phase 4 needs if the plan is to use
        # FinBERT's probability as a per-message weight.
        print("  Confidence-bucketed accuracy (does high confidence mean more likely correct?):")
        buckets = [(0.0, 0.6), (0.6, 0.8), (0.8, 0.95), (0.95, 1.01)]
        for lo, hi in buckets:
            idxs = [i for i, c in enumerate(confidences) if lo <= c < hi]
            if not idxs:
                continue
            b_correct = sum(1 for i in idxs if pred_labels[i] == true_labels[i])
            print(f"    conf [{lo:.2f}-{hi:.2f}) n={len(idxs):4d}: {b_correct/len(idxs):.1%} correct")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", type=int, default=len(WATCHLIST),
                         help="How many watchlist tickers to sample (default: all)")
    parser.add_argument("--max-per-ticker", type=int, default=400)
    args = parser.parse_args()

    tickers = WATCHLIST[:args.tickers]
    print(f"Fetching tagged ground-truth messages across {len(tickers)} tickers...")
    tagged = fetch_tagged_sample(tickers, hard_limit=args.max_per_ticker)
    print(f"\nCollected {len(tagged)} self-tagged (ground-truth) messages.")
    if len(tagged) < 30:
        print("Too few tagged messages to draw a real conclusion -- widen --tickers or re-run later.")
        return

    true_labels = [m["_true_label"] for m in tagged]

    print("\nRunning FinBERT...")
    finbert_clf = load_finbert()
    finbert_out = run_finbert(finbert_clf, tagged)
    finbert_labels = [l for l, c in finbert_out]
    finbert_conf = [c for l, c in finbert_out]

    print("Running Gemini (same pipeline path as production)...")
    gemini_labels = run_gemini(tagged)

    print("Running VADER (fallback baseline)...")
    vader_labels = run_vader(tagged)

    report("FinBERT (ProsusAI/finbert)", true_labels, finbert_labels, finbert_conf)
    report("Gemini (current production path)", true_labels, gemini_labels)
    report("VADER (old fallback)", true_labels, vader_labels)

    print(f"\nSample: {len(tagged)} messages across {len(tickers)} tickers, "
          f"{sum(1 for l in true_labels if l == 'bullish')} bullish / "
          f"{sum(1 for l in true_labels if l == 'bearish')} bearish (real StockTwits self-tags).")


if __name__ == "__main__":
    main()
