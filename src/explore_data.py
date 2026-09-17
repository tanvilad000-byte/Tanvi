import sqlite3
import pandas as pd

conn = sqlite3.connect("data/trading.db")

print("=== ARTICLES + THEIR INSTRUMENT MATCHES ===")
articles_df = pd.read_sql_query("""
    SELECT a.title, a.provider, ai.instrument, ai.match_type, ai.relevance_score, a.published_at
    FROM articles a
    JOIN article_instruments ai ON a.id = ai.article_id
    ORDER BY ai.relevance_score DESC
""", conn)
print(articles_df)

print("\n=== AVERAGE RELEVANCE SCORE PER INSTRUMENT ===")
print(articles_df.groupby("instrument")["relevance_score"].mean())

print("\n=== ARTICLE COUNT PER PROVIDER ===")
print(articles_df["provider"].value_counts())

print("\n=== LATEST MARKET CANDLE PER INSTRUMENT ===")
candles_df = pd.read_sql_query("""
    SELECT instrument, timestamp, open, high, low, close
    FROM market_candles
    ORDER BY timestamp DESC
""", conn)
latest_per_instrument = candles_df.groupby("instrument").first()
print(latest_per_instrument)

print("\n=== PRICE VOLATILITY (highest - lowest) PER INSTRUMENT, last 24 candles ===")
print(candles_df.groupby("instrument").agg(
    highest=("high", "max"),
    lowest=("low", "min")
).assign(range=lambda df: df["highest"] - df["lowest"]))

conn.close()
