from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta, timezone

import yfinance as yf

from src.database.db import init_db, get_connection
from src.logger import logger

INSTRUMENTS = {
    "NIFTY50": "^NSEI",
}

INITIAL_LOOKBACK_DAYS = 180   # only used when the table is empty
OVERLAP_DAYS = 2              # re-fetch recent days so final values replace partial ones
CANDLE_LENGTH = timedelta(minutes=60)
IST = timezone(timedelta(hours=5, minutes=30))


def is_valid_candle(open_, high, low, close):
    if high < open_ or high < close or high < low:
        return False
    if low > open_ or low > close:
        return False
    return True


def get_latest_candle_date(instrument_code):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(timestamp) FROM market_candles WHERE instrument = ?",
            (instrument_code,),
        ).fetchone()
    return row[0]


def count_candles(instrument_code):
    with get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM market_candles WHERE instrument = ?",
            (instrument_code,),
        ).fetchone()[0]


def compute_start_date(instrument_code):
    latest = get_latest_candle_date(instrument_code)
    if latest is None:
        return (datetime.now(timezone.utc) - timedelta(days=INITIAL_LOOKBACK_DAYS)).date()
    latest_date = datetime.strptime(latest[:10], "%Y-%m-%d").date()
    return latest_date - timedelta(days=OVERLAP_DAYS)


def upsert_candles(candles):
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO market_candles
                (instrument, timestamp, open, high, low, close, volume, provider, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(instrument, timestamp) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                collected_at = excluded.collected_at
            """,
            [
                (c["instrument"], c["timestamp"], c["open"], c["high"], c["low"],
                 c["close"], c["volume"], c["provider"], c["collected_at"])
                for c in candles
            ],
        )


def fetch_candles(instrument_code, yf_ticker):
    start = compute_start_date(instrument_code)
    logger.info(f"{instrument_code}: fetching from {start}")

    try:
        data = yf.download(yf_ticker, start=start.isoformat(), interval="1h",
                           auto_adjust=True, progress=False)
    except Exception as e:
        logger.error(f"yfinance request failed for {instrument_code}: {e}")
        return []

    if data.empty:
        logger.warning(f"yfinance returned no data for {instrument_code}")
        return []

    now_utc = datetime.now(timezone.utc)
    collected_at = now_utc.isoformat()
    candles = []
    rejected = 0
    still_forming = 0

    for timestamp, row in data.iterrows():
        candle_start = timestamp.to_pydatetime()
        if candle_start.tzinfo is None:
            candle_start = candle_start.replace(tzinfo=IST)

        # A candle that has not finished yet has partial values, so skip it for now.
        if candle_start + CANDLE_LENGTH > now_utc:
            still_forming += 1
            continue

        try:
            open_ = round(float(row[("Open", yf_ticker)]), 2)
            high = round(float(row[("High", yf_ticker)]), 2)
            low = round(float(row[("Low", yf_ticker)]), 2)
            close = round(float(row[("Close", yf_ticker)]), 2)
            volume = float(row[("Volume", yf_ticker)])
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Skipping malformed candle for {instrument_code}: {e}")
            rejected += 1
            continue

        if not is_valid_candle(open_, high, low, close):
            logger.warning(f"Skipping impossible candle for {instrument_code} at {timestamp}")
            rejected += 1
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

    if rejected:
        logger.warning(f"{instrument_code}: rejected {rejected} invalid candle(s)")
    if still_forming:
        logger.info(f"{instrument_code}: skipped {still_forming} candle(s) still forming")

    return candles


def main():
    init_db()

    for instrument_code, yf_ticker in INSTRUMENTS.items():
        before = count_candles(instrument_code)
        candles = fetch_candles(instrument_code, yf_ticker)
        if candles:
            upsert_candles(candles)
        after = count_candles(instrument_code)
        logger.info(
            f"{instrument_code}: {len(candles)} complete candles fetched, "
            f"{after - before} new, {after} total"
        )


if __name__ == "__main__":
    main()
