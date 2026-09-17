import json
import sqlite3


def test_ai_input_json_structure(tmp_path, monkeypatch):
    """
    Test the AI data preparation pipeline using a temporary database
    and temporary output file.
    """

    # Import the module we are testing
    import src.prepare_ai_data as prepare_module

    # Create a temporary database
    db_path = tmp_path / "test.db"

    conn = sqlite3.connect(db_path)

    conn.execute("""
        CREATE TABLE articles (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            source TEXT,
            url TEXT,
            provider TEXT,
            published_at TEXT,
            collected_at TEXT,
            raw_json TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE article_instruments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id TEXT NOT NULL,
            instrument TEXT NOT NULL,
            match_type TEXT,
            match_strength REAL,
            sentiment REAL,
            relevance_score REAL,
            FOREIGN KEY (article_id) REFERENCES articles(id)
        )
    """)

    conn.execute("""
        CREATE TABLE market_candles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            provider TEXT,
            collected_at TEXT
        )
    """)

    # Insert test market data
    conn.execute("""
        INSERT INTO market_candles
        (instrument, timestamp, open, high, low, close, volume, provider, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "NIFTY50",
        "2026-09-17 13:15:00+05:30",
        23322.50,
        23325.25,
        23244.05,
        23248.25,
        0.0,
        "yfinance",
        "2026-09-17T08:30:00+00:00",
    ))

    # Insert test news
    conn.execute("""
        INSERT INTO articles
        (id, title, description, source, url, provider, published_at, collected_at, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "test123",
        "Test NIFTY50 News",
        "Test description",
        "Test Source",
        "https://example.com/test",
        "marketaux",
        "2026-09-17T07:00:00+00:00",
        "2026-09-17T08:30:00+00:00",
        '{"test": true}',
    ))

    conn.execute("""
        INSERT INTO article_instruments
        (article_id, instrument, match_type, match_strength, sentiment, relevance_score)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "test123",
        "NIFTY50",
        "keyword",
        0.6,
        None,
        0.7,
    ))

    conn.commit()
    conn.close()

    # Use the temporary database and output file
    output_path = tmp_path / "ai_input.json"

    monkeypatch.setattr(prepare_module, "DB_PATH", str(db_path))
    monkeypatch.setattr(prepare_module, "OUTPUT_PATH", str(output_path))

    # Run the actual preparation function
    prepare_module.prepare_ai_data()

    # Verify output file was created
    assert output_path.exists()

    # Read generated JSON
    with output_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    # Top-level structure
    assert data["instrument"] == "NIFTY50"
    assert "market" in data
    assert "news" in data

    # Market structure
    market = data["market"]

    assert market["instrument"] == "NIFTY50"
    assert market["open"] == 23322.50
    assert market["high"] == 23325.25
    assert market["low"] == 23244.05
    assert market["close"] == 23248.25

    # News structure
    assert isinstance(data["news"], list)
    assert len(data["news"]) == 1

    article = data["news"][0]

    assert article["article_id"] == "test123"
    assert "title" in article
    assert "source" in article
    assert "url" in article
    assert "published_at" in article
    assert "collected_at" in article
    assert article["instrument"] == "NIFTY50"
    assert article["match_strength"] == 0.6
    assert article["relevance_score"] == 0.7

    # These fields should not be sent to the AI
    assert "raw_json" not in article
    assert "sentiment" not in article
    assert "volume" not in article