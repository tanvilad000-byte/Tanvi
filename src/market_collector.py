from dotenv import load_dotenv
load_dotenv()

import os
from datetime import datetime, timedelta, timezone

import requests

from src.database.db import init_db, save_candles
from src.logger import logger

TWELVEDATA_URL = "https://api.twelvedata.com/time_series"
REQUEST_TIMEOUT = 10

INSTRUMENTS = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "XAUUSD": "XAU/USD",
}


def is_valid_candle(open_, high, low, close):
    """
    NEW: rejects candles with physically impossible OHLC relationships.
    A real candle must satisfy: high is the highest value, low is the lowest.
    """
    if high < open_ or high < close or high < low:
        return False
    if low > open_ or low > close:
        return False
    return True


def fetch_candles(instrument_code, twelvedata_symbol, api_key):
    try:
        response = requests.get(
            TWELVEDATA_URL,
            params={
                "symbol": twelvedata_symbol,
                "interval": "1h",
                "outputsize": 24,
                "apikey": api_key,
            },
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 429:
            logger.error(f"Rate limit (429) hit for TwelveData [{instrument_code}] — skipping")
            return []

        response.raise_for_status()
    except requests.exceptions.Timeout:
        logger.error(f"TwelveData request timed out for {instrument_code}")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"TwelveData request failed for {instrument_code}: {e}")
        return []

    data = response.json()

    if data.get("status") != "ok":
        logger.warning(f"TwelveData returned non-ok status for {instrument_code}: {data}")
        return []

    collected_at = datetime.now(timezone.utc).isoformat()
    candles = []
    rejected_count = 0

    for entry in data.get("values", []):
        try:
            open_ = float(entry["open"])
            high = float(entry["high"])
            low = float(entry["low"])
            close = float(entry["close"])
        except (KeyError, ValueError) as e:
            logger.warning(f"Skipping malformed candle for {instrument_code}: {e}")
            rejected_count += 1
            continue

        if not is_valid_candle(open_, high, low, close):
            logger.warning(
                f"Skipping impossible candle for {instrument_code} at {entry.get('datetime')}: "
                f"o={open_} h={high} l={low} c={close}"
            )
            rejected_count += 1
            continue

        candles.append({
            "instrument": instrument_code,
            "timestamp": entry["datetime"],
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "provider": "twelvedata",
            "collected_at": collected_at,
        })

    if rejected_count:
        logger.warning(f"{instrument_code}: rejected {rejected_count} invalid candle(s)")

    return candles


def main():
    init_db()
    api_key = os.getenv("TWELVEDATA_API_KEY")

    if not api_key:
        logger.error("TWELVEDATA_API_KEY not set — skipping market data collection")
        return

    all_candles = []
    for instrument_code, symbol in INSTRUMENTS.items():
        candles = fetch_candles(instrument_code, symbol, api_key)
        logger.info(f"{instrument_code}: {len(candles)} valid candles fetched")
        all_candles.extend(candles)

    if all_candles:
        save_candles(all_candles)

    logger.info(f"Market data collection complete: {len(all_candles)} candles processed")


if __name__ == "__main__":
    main()