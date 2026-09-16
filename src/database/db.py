import json
import sqlite3
from contextlib import contextmanager

DB_PATH = "data/trading.db"


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source TEXT,
                url TEXT,
                provider TEXT,
                published_at TEXT,
                collected_at TEXT,
                raw_json TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_candles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                provider TEXT,
                collected_at TEXT,
                UNIQUE(instrument, timestamp)
            )
        """)
        existing_columns = [row[1] for row in conn.execute("PRAGMA table_info(articles)")]
        if "description" not in existing_columns:
            conn.execute("ALTER TABLE articles ADD COLUMN description TEXT")


def get_existing_article_ids():
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM articles").fetchall()
        return {row[0] for row in rows}


def save_articles(article_records):
    with get_connection() as conn:
        for record in article_records:
            a = record["article"]
            conn.execute(
                """
                INSERT INTO articles (id, title, source, url, provider, published_at, collected_at, raw_json, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (a["id"], a["title"], a["source"], a["url"], a["provider"],
                 a["published_at"], a["collected_at"], a["raw_json"], a.get("description")),
            )
            for inst in record["instruments"]:
                conn.execute(
                    """
                    INSERT INTO article_instruments
                        (article_id, instrument, match_type, match_strength, sentiment, relevance_score)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (a["id"], inst["instrument"], inst["match_type"],
                     inst["match_strength"], inst["sentiment"], inst["relevance_score"]),
                )
def get_existing_candle_keys():
    with get_connection() as conn:
        rows = conn.execute("SELECT instrument, timestamp FROM market_candles").fetchall()
        return {(row[0], row[1]) for row in rows}


def save_candles(candles):
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO market_candles
                (instrument, timestamp, open, high, low, close, provider, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (c["instrument"], c["timestamp"], c["open"], c["high"],
                 c["low"], c["close"], c["provider"], c["collected_at"])
                for c in candles
            ],
        )