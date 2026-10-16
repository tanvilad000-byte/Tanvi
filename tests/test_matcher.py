import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.matching import match_instruments_by_keywords
from src.news_collector import is_generic_roundup


def match_type_of(text):
    results = match_instruments_by_keywords(text)
    return results[0][3] if results else None


def test_nifty_is_a_direct_match():
    assert match_type_of("Nifty 50 hits record high amid strong FII inflows") == "keyword_direct"


def test_rbi_and_sensex_are_direct_matches():
    assert match_type_of("RBI holds rates steady, Sensex reacts positively") == "keyword_direct"


def test_fed_news_alone_is_only_a_weak_macro_match():
    results = match_instruments_by_keywords("Federal Reserve raises interest rates again")
    assert results[0][3] == "keyword_macro"
    assert results[0][1] < 0.5


def test_unrelated_text_does_not_match():
    assert match_instruments_by_keywords("Local bakery wins award for best croissant") == []


def test_generic_roundup_detected():
    assert is_generic_roundup("What are the main events for today?") is True
    assert is_generic_roundup("Nifty 50 surges on Fed decision") is False


# The tests below are the real false positives found when auditing the stored articles.

def test_defense_is_not_nse():
    assert match_instruments_by_keywords("Saudi Civil Defense lifts warnings of potential danger") == []


def test_license_is_not_nse():
    assert match_instruments_by_keywords("Turkey revokes operating license of Iran's Mellat Bank") == []


def test_nse_ipo_story_is_not_a_nifty_story():
    assert match_instruments_by_keywords("NSE IPO Day 1: Issue subscribed 22% in early hours") == []


def test_rbi_inside_other_words_does_not_match():
    assert match_instruments_by_keywords("The satellite left orbit near the turbine plant") == []


def test_nifty_500_is_not_scored_as_nifty_50():
    results = match_instruments_by_keywords("What Nifty 500 returns really look like")
    assert results[0][1] == 0.7


if __name__ == "__main__":
    tests = [fn for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for fn in tests:
        fn()
    print(f"All {len(tests)} matcher tests passed.")
