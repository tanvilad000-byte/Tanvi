from dotenv import load_dotenv
load_dotenv()

import os
import requests
from src.database.db import init_db, save_candles
from src.logger import logger

TWELVEDATA_URL = "https://api.twelvedata.com/time_series"

INSTRUMENTS = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "XAUUSD": "XAU/USD",
}


def fetch_historical(instrument_code, symbol, api_key, outputsize=1000):
    response = requests.get(
        TWELVEDATA_URL,
        params={
            "symbol": symbol,
            "interval": "1h",
            "outputsize": outputsize,  # up to 5000 on free tier, in one call
            "apikey": api_key,
        },
        timeout=15,
    )
    data = response.json()

    if data.get("status") != "ok":
        logger.error(f"Historical fetch failed for {instrument_code}: {data}")
        return []

    from datetime import datetime, timezone
    collected_at = datetime.now(timezone.utc).isoformat()

    candles = []
    for entry in data.get("values", []):
        try:
            o, h, l, c = float(entry["open"]), float(entry["high"]), float(entry["low"]), float(entry["close"])
        except (KeyError, ValueError):
            continue
        if h < o or h < c or h < l or l > o or l > c:
            continue  # skip impossible candles, same rule as your live collector
        candles.append({
            "instrument": instrument_code, "timestamp": entry["datetime"],
            "open": o, "high": h, "low": l, "close": c,
            "provider": "twelvedata", "collected_at": collected_at,
        })
    return candles


def main():
    init_db()
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        logger.error("TWELVEDATA_API_KEY not set")
        return

    for instrument_code, symbol in INSTRUMENTS.items():
        candles = fetch_historical(instrument_code, symbol, api_key, outputsize=1000)
        logger.info(f"{instrument_code}: fetched {len(candles)} historical candles")
        if candles:
            save_candles(candles)


if __name__ == "__main__":
    main()
