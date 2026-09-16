import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone
from src.news_collector import validate_published_at
from src.market_collector import is_valid_candle


def test_valid_recent_timestamp_passes():
    now_iso = datetime.now(timezone.utc).isoformat()
    assert validate_published_at(now_iso) is True


def test_future_timestamp_rejected():
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert validate_published_at(future) is False


def test_malformed_timestamp_rejected():
    assert validate_published_at("not-a-real-date") is False
    assert validate_published_at(None) is False
    assert validate_published_at("") is False


def test_normal_candle_is_valid():
    assert is_valid_candle(100, 105, 98, 102) is True


def test_high_lower_than_open_rejected():
    assert is_valid_candle(100, 95, 90, 92) is False


def test_low_higher_than_close_rejected():
    assert is_valid_candle(100, 108, 110, 102) is False


if __name__ == "__main__":
    test_valid_recent_timestamp_passes()
    test_future_timestamp_rejected()
    test_malformed_timestamp_rejected()
    test_normal_candle_is_valid()
    test_high_lower_than_open_rejected()
    test_low_higher_than_close_rejected()
    print("All validation tests passed.")


def test_html_stripped_from_description():
    from src.news_collector import clean_html_and_truncate
    dirty = "<p>Gold <em>rises</em> as inflation fears grow.</p><p>More text here.</p>"
    result = clean_html_and_truncate(dirty)
    assert "<p>" not in result
    assert "<em>" not in result
    assert "Gold rises as inflation fears grow." in result


def test_description_truncated_at_max_length():
    from src.news_collector import clean_html_and_truncate
    long_text = "word " * 500  # way over 1000 characters
    result = clean_html_and_truncate(long_text, max_length=1000)
    assert len(result) == 1000


def test_empty_description_returns_none():
    from src.news_collector import clean_html_and_truncate
    assert clean_html_and_truncate(None) is None
    assert clean_html_and_truncate("") is None
