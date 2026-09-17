import json
import sqlite3
from pathlib import Path


DB_PATH = "data/trading.db"
OUTPUT_PATH = "data/processed/ai_input.json"


def prepare_ai_data():
    """
    Read clean NIFTY50 market and news data from SQLite
    and prepare a JSON file for the AI Engineer.
    """

    # Make sure the output directory exists
    Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # ---------------------------------------------------------
        # 1. Get the latest NIFTY50 market candle
        # ---------------------------------------------------------
        market_row = conn.execute(
            """
            SELECT
                instrument,
                timestamp,
                open,
                high,
                low,
                close
            FROM market_candles
            WHERE instrument = 'NIFTY50'
            ORDER BY timestamp DESC
            LIMIT 1
            """
        ).fetchone()

        # ---------------------------------------------------------
        # 2. Get relevant NIFTY50 news
        # ---------------------------------------------------------
        news_rows = conn.execute(
            """
            SELECT
                a.id AS article_id,
                a.title,
                a.description,
                a.source,
                a.url,
                a.published_at,
                a.collected_at,
                ai.instrument,
                ai.match_strength,
                ai.relevance_score
            FROM articles a
            JOIN article_instruments ai
                ON a.id = ai.article_id
            WHERE ai.instrument = 'NIFTY50'
            ORDER BY ai.relevance_score DESC
            """
        ).fetchall()

        # ---------------------------------------------------------
        # 3. Convert database rows into normal Python dictionaries
        # ---------------------------------------------------------
        market_data = dict(market_row) if market_row else None

        news_data = [dict(row) for row in news_rows]

        # ---------------------------------------------------------
        # 4. Create the final AI input structure
        # ---------------------------------------------------------
        ai_data = {
            "instrument": "NIFTY50",
            "market": market_data,
            "news": news_data
        }

        # ---------------------------------------------------------
        # 5. Write JSON file
        # ---------------------------------------------------------
        with open(OUTPUT_PATH, "w", encoding="utf-8") as file:
            json.dump(ai_data, file, indent=4, ensure_ascii=False)

        print(f"AI data prepared successfully.")
        print(f"Output file: {OUTPUT_PATH}")
        print(f"News articles included: {len(news_data)}")
        print(f"Market candle included: {'Yes' if market_data else 'No'}")

    finally:
        conn.close()


if __name__ == "__main__":
    prepare_ai_data()