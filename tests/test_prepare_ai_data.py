import json
from pathlib import Path


def test_ai_input_json_structure():
    """
    Verify that the generated AI input file has the required structure.
    """

    file_path = Path("data/processed/ai_input.json")

    assert file_path.exists(), "AI input JSON file does not exist"

    with file_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    # Top-level structure
    assert data["instrument"] == "NIFTY50"
    assert "market" in data
    assert "news" in data

    # Market structure
    market = data["market"]

    assert market["instrument"] == "NIFTY50"
    assert "timestamp" in market
    assert "open" in market
    assert "high" in market
    assert "low" in market
    assert "close" in market

    # News structure
    assert isinstance(data["news"], list)
    assert len(data["news"]) > 0

    for article in data["news"]:
        assert "article_id" in article
        assert "title" in article
        assert "source" in article
        assert "url" in article
        assert "published_at" in article
        assert "collected_at" in article
        assert article["instrument"] == "NIFTY50"
        assert "match_strength" in article
        assert "relevance_score" in article

        # These should not be passed from Data Engineer to AI
        assert "raw_json" not in article
        assert "sentiment" not in article
        assert "volume" not in article