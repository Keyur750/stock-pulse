"""
Shared Gemini client — extracted from analyst.py once a second module
(news_ranker.py) needed the same client/model instead of duplicating
the lazy-init-and-cache logic across two AI-calling modules.

Deliberately pinned, not "-latest". The "-latest" aliases silently
repoint to newer models over time — gemini-flash-latest moved to
gemini-3.6-flash mid-project, which turned out to have a free-tier cap
of just 20 requests/day (vs. flash-lite's much larger allowance), and
quietly zeroed out our quota. Pin to a specific model with known quota
headroom; re-evaluate deliberately, not by surprise.
"""

import os

MODEL = "gemini-3.1-flash-lite"

_client = None
_client_checked = False


def get_client():
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("  [llm] GEMINI_API_KEY not set — skipping AI-dependent features.")
        return None
    try:
        from google import genai
    except ImportError:
        print("  [llm] google-genai not installed — skipping AI-dependent features.")
        return None
    try:
        _client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"  [llm] failed to init Gemini client: {type(e).__name__}: {e}")
        _client = None
    return _client
