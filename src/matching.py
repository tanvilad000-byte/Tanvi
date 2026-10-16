"""Keyword matching and scoring for NIFTY50 news. Every matching rule lives here."""
import re
from datetime import datetime, timezone

INSTRUMENT = "NIFTY50"
MIN_MATCH_STRENGTH = 0.35

# Words that point straight at the Indian market.
DIRECT_KEYWORDS = {
    "nifty 50": 0.9, "nifty50": 0.9,
    "sensex": 0.8,
    "nifty": 0.7, "indian market": 0.7, "indian stock": 0.7,
    "indian equities": 0.7, "dalal street": 0.7,
    "reserve bank of india": 0.6, "rbi": 0.6, "indian rupee": 0.6,
    "rupee": 0.5, "fii": 0.5, "dii": 0.5,
}

# Global news that can move Indian markets, but only indirectly.
MACRO_KEYWORDS = {
    "federal reserve": 0.4, "fed rate": 0.4,
    "inflation": 0.3, "oil price": 0.3, "crude oil": 0.3, "interest rate": 0.3,
}


def _compile(keywords):
    # \b means "word boundary": "rbi" no longer matches inside "orbit" or "turbine",
    # and "nifty 50" no longer matches inside "nifty 500".
    # The optional "s" lets "interest rate" also match "interest rates".
    return {kw: re.compile(r"\b" + re.escape(kw) + r"s?\b", re.IGNORECASE) for kw in keywords}


_DIRECT = _compile(DIRECT_KEYWORDS)
_MACRO = _compile(MACRO_KEYWORDS)


def match_instruments_by_keywords(text):
    """Returns [] or [(instrument, strength, matched_keywords, match_type)].

    match_type is "keyword_direct" when the text names the Indian market itself,
    and "keyword_macro" when it only has global macro terms (Fed, oil, inflation).
    """
    direct = [kw for kw, pattern in _DIRECT.items() if pattern.search(text)]
    if direct:
        strength = max(DIRECT_KEYWORDS[kw] for kw in direct)
        return [(INSTRUMENT, strength, direct, "keyword_direct")]

    macro = [kw for kw, pattern in _MACRO.items() if pattern.search(text)]
    if macro:
        strength = max(MACRO_KEYWORDS[kw] for kw in macro)
        if strength >= MIN_MATCH_STRENGTH:
            return [(INSTRUMENT, strength, macro, "keyword_macro")]

    return []


def compute_recency_score(published_at_iso):
    published = datetime.fromisoformat(published_at_iso.replace("Z", "+00:00"))
    hours_old = (datetime.now(timezone.utc) - published).total_seconds() / 3600
    return max(0.0, min(1.0, 1 - hours_old / 72))


def compute_relevance_score(match_strength, published_at_iso):
    recency = compute_recency_score(published_at_iso)
    return round(0.7 * match_strength + 0.3 * recency, 3)
