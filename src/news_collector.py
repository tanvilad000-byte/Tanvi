import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests

from src.config import NEWS_API_KEY
from src.database.db import init_db, get_existing_article_ids, save_articles
from src.logger import logger

import re



MARKETAUX_URL = "https://api.marketaux.com/v1/news/all"
FINNHUB_URL = "https://finnhub.io/api/v1/news"
REQUEST_TIMEOUT = 10

TARGET_INSTRUMENTS = {"EURUSD", "GBPUSD", "XAUUSD"}

INSTRUMENT_KEYWORDS = {
    "XAUUSD": {
        "xauusd": 0.9, "gold price": 0.8, "gold prices": 0.8,
        "gold rate": 0.7, "gold rates": 0.7, "bullion": 0.6,
        "precious metal": 0.6, "gold hits": 0.6, "gold surge": 0.6,
        "safe haven": 0.3, "safe-haven": 0.3,
    },
    "EURUSD": {
        "eurusd": 0.9, "eur/usd": 0.9, "euro dollar": 0.8,
        "ecb": 0.6, "european central bank": 0.6, "eurozone": 0.5,
        "the euro": 0.4, "us dollar": 0.3, "dollar index": 0.3, "greenback": 0.3,
    },
    "GBPUSD": {
        "gbpusd": 0.9, "gbp/usd": 0.9, "british pound": 0.7,
        "pound sterling": 0.7, "bank of england": 0.6, "sterling": 0.4,
    },
}

MIN_MATCH_STRENGTH = 0.35

GENERIC_TITLE_PATTERNS = ["main events for today", "what to watch", "economic calendar", "week ahead", "day ahead"]


def is_generic_roundup(title):
    return any(p in title.lower() for p in GENERIC_TITLE_PATTERNS)


def make_article_id(url):
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def match_instruments_by_keywords(text):
    text_lower = text.lower()
    results = []
    for instrument, keyword_weights in INSTRUMENT_KEYWORDS.items():
        matched = {kw: w for kw, w in keyword_weights.items() if kw in text_lower}
        if not matched:
            continue
        strength = max(matched.values())
        if strength >= MIN_MATCH_STRENGTH:
            results.append((instrument, strength, list(matched.keys())))
    return results


def validate_published_at(value):
    """
    NEW: rejects malformed timestamps and anything claiming to be from the future.
    A small 5-minute buffer allows for minor clock differences between servers.
    """
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return False

    if dt > datetime.now(timezone.utc) + timedelta(minutes=5):
        return False

    return True


def compute_recency_score(published_at_iso):
    published_dt = datetime.fromisoformat(published_at_iso.replace("Z", "+00:00"))
    hours_old = (datetime.now(timezone.utc) - published_dt).total_seconds() / 3600
    score = 1 - (hours_old / 72)
    return max(0.0, min(1.0, score))


def compute_relevance_score(match_strength, published_at_iso):
    recency = compute_recency_score(published_at_iso)
    return round((0.7 * match_strength) + (0.3 * recency), 3)


def safe_get(dictionary, key, default=None):
    return dictionary.get(key, default)


def fetch_with_retry(url, params, max_attempts=3, base_delay=2):
    """
    Tries a GET request up to max_attempts times, with a short increasing pause
    between failures. Stops immediately on 429 (rate limit) instead of retrying,
    since retrying a rate-limited request wastes quota and will fail again anyway.
    Returns the response, or None if all attempts fail.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)

            if response.status_code == 429:
                logger.error(f"Rate limit (429) hit for {url} — not retrying, would waste quota")
                return None

            response.raise_for_status()
            return response

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout on attempt {attempt}/{max_attempts} for {url}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed on attempt {attempt}/{max_attempts} for {url}: {e}")

        if attempt < max_attempts:
            time.sleep(base_delay * attempt)

    logger.error(f"All {max_attempts} attempts failed for {url}")
    return None


# ---------- MARKETAUX ----------

def clean_marketaux_article(raw_article, run_timestamp):
    title = safe_get(raw_article, "title")
    url = safe_get(raw_article, "url")
    published_at = safe_get(raw_article, "published_at")

    if not title or not url or not published_at:
        logger.warning(f"Marketaux article missing required fields, skipping: id={raw_article.get('uuid')}")
        return None

    if not validate_published_at(published_at):
        logger.warning(f"Marketaux article has invalid/future timestamp, skipping: '{title[:60]}' -> {published_at}")
        return None

    if is_generic_roundup(title):
        return None

    instrument_matches = []

    for entity in raw_article.get("entities", []):
        symbol = entity.get("symbol")
        if symbol in TARGET_INSTRUMENTS:
            strength = min(1.0, entity.get("match_score", 0) / 100)
            instrument_matches.append({
                "instrument": symbol,
                "match_type": "entity",
                "match_strength": strength,
                "sentiment": entity.get("sentiment_score"),
                "relevance_score": compute_relevance_score(strength, published_at),
            })

    if not instrument_matches:
        for instrument, strength, matched_keywords in match_instruments_by_keywords(title):
            logger.info(f"[MARKETAUX KEYWORD] '{title[:60]}' -> {instrument} via {matched_keywords}")
            instrument_matches.append({
                "instrument": instrument,
                "match_type": "keyword",
                "match_strength": strength,
                "sentiment": None,
                "relevance_score": compute_relevance_score(strength, published_at),
            })

    if not instrument_matches:
        return None

    article_id = make_article_id(url)

    return {
        "article": {
            "id": article_id,
            "title": title,
            "source": safe_get(raw_article, "source"),
            "url": url,
            "provider": "marketaux",
            "published_at": published_at,
            "collected_at": run_timestamp,
            "raw_json": json.dumps(raw_article),
            "description": clean_html_and_truncate(safe_get(raw_article, "description")),
        },
        "instruments": instrument_matches,
    }

def fetch_marketaux_articles(run_timestamp):
    published_after = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")
    params = {
        "api_token": NEWS_API_KEY,
        "language": "en",
        "entity_types": "currency",
        "published_after": published_after,
        "limit": 50,
    }

    response = fetch_with_retry(MARKETAUX_URL, params)
    if response is None:
        return []

    data = response.json()
    raw_articles = data.get("data", [])
    logger.info(f"Marketaux: {len(raw_articles)} raw articles received")

    cleaned = [clean_marketaux_article(a, run_timestamp) for a in raw_articles]
    return [c for c in cleaned if c is not None]


# ---------- FINNHUB ----------

def clean_finnhub_article(raw_article, run_timestamp, cutoff_timestamp):
    headline = safe_get(raw_article, "headline")
    url = safe_get(raw_article, "url")
    unix_time = safe_get(raw_article, "datetime")

    if not headline or not url or unix_time is None:
        logger.warning(f"Finnhub article missing required fields, skipping: id={raw_article.get('id')}")
        return None

    if unix_time < cutoff_timestamp:
        return None

    published_at = datetime.fromtimestamp(unix_time, tz=timezone.utc).isoformat()

    if not validate_published_at(published_at):
        logger.warning(f"Finnhub article has invalid/future timestamp, skipping: '{headline[:60]}' -> {published_at}")
        return None

    if is_generic_roundup(headline):
        return None

    search_text = headline + " " + safe_get(raw_article, "summary", "")
    matches = match_instruments_by_keywords(search_text)
    if not matches:
        return None

    instrument_matches = []
    for instrument, strength, matched_keywords in matches:
        logger.info(f"[FINNHUB KEYWORD] '{headline[:60]}' -> {instrument} via {matched_keywords}")
        instrument_matches.append({
            "instrument": instrument,
            "match_type": "keyword",
            "match_strength": strength,
            "sentiment": None,
            "relevance_score": compute_relevance_score(strength, published_at),
        })

    article_id = make_article_id(url)

    return {
        "article": {
            "id": article_id,
            "title": headline,
            "source": safe_get(raw_article, "source"),
            "url": url,
            "provider": "finnhub",
            "published_at": published_at,
            "collected_at": run_timestamp,
            "raw_json": json.dumps(raw_article),
            "description": clean_html_and_truncate(safe_get(raw_article, "summary")),
        },
        "instruments": instrument_matches,
    }


def fetch_finnhub_articles(run_timestamp):
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    if not finnhub_key:
        logger.info("Finnhub skipped: no API key set")
        return []

    cutoff_timestamp = (datetime.now(timezone.utc) - timedelta(hours=24)).timestamp()

    all_raw_articles = []
    for category in ["forex", "general"]:
        response = fetch_with_retry(FINNHUB_URL, {"category": category, "token": finnhub_key})
        if response is None:
            continue

        data = response.json()
        logger.info(f"Finnhub [{category}]: {len(data)} raw articles received")
        all_raw_articles.extend(data)

    cleaned = [clean_finnhub_article(a, run_timestamp, cutoff_timestamp) for a in all_raw_articles]
    return [c for c in cleaned if c is not None]


# ---------- MAIN ----------

def main():
    init_db()
    existing_ids = get_existing_article_ids()

    run_timestamp = datetime.now(timezone.utc).isoformat()

    marketaux_records = fetch_marketaux_articles(run_timestamp)
    finnhub_records = fetch_finnhub_articles(run_timestamp)

    all_records = marketaux_records + finnhub_records

    new_records = []
    seen_in_this_run = set()
    for record in all_records:
        article_id = record["article"]["id"]
        if article_id in existing_ids or article_id in seen_in_this_run:
            continue
        new_records.append(record)
        seen_in_this_run.add(article_id)

    if new_records:
        save_articles(new_records)

    total_instrument_tags = sum(len(r["instruments"]) for r in new_records)

    logger.info(f"New articles added: {len(new_records)}")
    logger.info(f"Total instrument tags created: {total_instrument_tags}")
    logger.info(f"Total articles now in database: {len(existing_ids) + len(new_records)}")


def clean_html_and_truncate(text, max_length=1000):
    if not text:
        return None
    text_no_tags = re.sub(r"<[^>]+>", "", text)  # strip HTML tags
    text_clean = " ".join(text_no_tags.split())  # collapse extra whitespace/newlines
    return text_clean[:max_length]


if __name__ == "__main__":
    main()