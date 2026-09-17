import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.news_collector import match_instruments_by_keywords, is_generic_roundup


def test_nifty_direct_match():
    results = match_instruments_by_keywords("Nifty 50 hits record high amid strong FII inflows")
    instruments = [r[0] for r in results]
    assert "NIFTY50" in instruments


def test_rbi_match():
    results = match_instruments_by_keywords("RBI holds interest rates steady, Sensex reacts positively")
    instruments = [r[0] for r in results]
    assert "NIFTY50" in instruments


def test_no_match_on_unrelated_text():
    results = match_instruments_by_keywords("Local bakery wins award for best croissant")
    assert results == []


def test_generic_roundup_detected():
    assert is_generic_roundup("What are the main events for today?") is True
    assert is_generic_roundup("Nifty 50 surges on Fed decision") is False


def test_global_macro_terms_match_weakly():
    results = match_instruments_by_keywords("Federal Reserve raises interest rate again")
    assert len(results) > 0
    instrument, strength, keywords = results[0]
    assert strength < 0.5  # should be a WEAK match, not a strong one


if __name__ == "__main__":
    test_nifty_direct_match()
    test_rbi_match()
    test_no_match_on_unrelated_text()
    test_generic_roundup_detected()
    test_global_macro_terms_match_weakly()
    print("All matcher tests passed.")
