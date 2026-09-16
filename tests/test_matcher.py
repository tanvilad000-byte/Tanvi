import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.news_collector import match_instruments_by_keywords, is_generic_roundup


def test_strong_eurusd_match():
    results = match_instruments_by_keywords("EUR/USD rises after ECB decision")
    instruments = [r[0] for r in results]
    assert "EURUSD" in instruments


def test_gold_match():
    results = match_instruments_by_keywords("Gold prices hit record high amid inflation fears")
    instruments = [r[0] for r in results]
    assert "XAUUSD" in instruments


def test_no_false_match_on_unrelated_text():
    results = match_instruments_by_keywords("Local sports team wins championship game")
    assert results == []


def test_generic_roundup_detected():
    assert is_generic_roundup("What are the main events for today?") is True
    assert is_generic_roundup("Gold prices surge on Fed decision") is False


def test_multiple_instruments_can_match_one_article():
    results = match_instruments_by_keywords("EUR/USD and GBP/USD both rally as dollar weakens")
    instruments = [r[0] for r in results]
    assert "EURUSD" in instruments
    assert "GBPUSD" in instruments


if __name__ == "__main__":
    test_strong_eurusd_match()
    test_gold_match()
    test_no_false_match_on_unrelated_text()
    test_generic_roundup_detected()
    test_multiple_instruments_can_match_one_article()
    print("All tests passed.")