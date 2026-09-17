from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timezone

import yfinance as yf

from src.database.db import init_db, save_candles
from src.logger import logger

INSTRUMENTS = {
    "NIFTY50": "^NSEI",
}


def is_valid_candle(open_, high, low, close):
    if high < open_ or high < close or high < low:
        return False
    if low > open_ or low > close:
        return False
    return True


def fetch_candles(instrument_code, yf_ticker):
    try:
        data = yf.download(yf_ticker, period="5d", interval="1h", auto_adjust=True, progress=False)
    except Exception as e:
        logger.error(f"yfinance request failed for {instrument_code}: {e}")
        return []

    if data.empty:
        logger.warning(f"yfinance returned no data for {instrument_code}")
        return []

    collected_at = datetime.now(timezone.utc).isoformat()
    candles = []
    rejected_count = 0

    for timestamp, row in data.iterrows():
        try:
            open_ = round(float(row[("Open", yf_ticker)]), 2)
            high = round(float(row[("High", yf_ticker)]), 2)
            low = round(float(row[("Low", yf_ticker)]), 2)
            close = round(float(row[("Close", yf_ticker)]), 2)
            volume = float(row[("Volume", yf_ticker)])
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Skipping malformed candle for {instrument_code}: {e}")
            rejected_count += 1
            continue

        if not is_valid_candle(open_, high, low, close):
            logger.warning(f"Skipping impossible candle for {instrument_code} at {timestamp}")
            rejected_count += 1
            continue

        candles.append({
            "instrument": instrument_code,
            "timestamp": str(timestamp),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "provider": "yfinance",
            "collected_at": collected_at,
        })

    if rejected_count:
        logger.warning(f"{instrument_code}: rejected {rejected_count} invalid candle(s)")

    return candles


def main():
    init_db()

    all_candles = []
    for instrument_code, yf_ticker in INSTRUMENTS.items():
        candles = fetch_candles(instrument_code, yf_ticker)
        logger.info(f"{instrument_code}: {len(candles)} valid candles fetched")
        all_candles.extend(candles)

    if all_candles:
        save_candles(all_candles)

    logger.info(f"Market data collection complete: {len(all_candles)} candles processed")


if __name__ == "__main__":
    main()
