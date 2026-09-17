import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from src.config import NEWS_API_KEY
from src.database.db import init_db, get_existing_article_ids, save_articles
from src.logger import logger

MARKETAUX_URL = "https://api.marketaux.com/v1/news/all"
FINNHUB_URL = "https://finnhub.io/api/v1/news"
REQUEST_TIMEOUT = 10

TARGET_INSTRUMENTS = {"NIFTY50"}

INSTRUMENT_KEYWORDS = {
    "NIFTY50": {
        "nifty 50": 0.9, "nifty50": 0.9, "sensex": 0.8, "nifty": 0.7,
        "indian markets": 0.7, "indian stocks": 0.7, "bse ": 0.6, "nse ": 0.6,
        "rbi": 0.6, "reserve bank of india": 0.6, "fii": 0.5, "dii": 0.5,
        "rupee": 0.5, "indian rupee": 0.6,
        "federal reserve": 0.4, "fed rate": 0.4, "inflation": 0.3,
        "oil prices": 0.3, "crude oil": 0.3, "interest rate": 0.3,
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


def clean_html_and_truncate(text, max_length=1000):
    if not text:
        return None
    text_no_tags = re.sub(r"<[^>]+>", "", text)
    text_clean = " ".join(text_no_tags.split())
    return text_clean[:max_length]


def fetch_with_retry(url, params, max_attempts=3, base_delay=2):
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if response.status_code == 429:
                logger.error(f"Rate limit (429) hit for {url} — not retrying")
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


class Stats:
    def __init__(self, provider_name):
        self.provider = provider_name
        self.fetched = 0
        self.rejected = 0
        self.relevant = 0
        self.duplicates = 0
        self.saved = 0

    def report(self):
        return (
            f"{self.provider}:\n"
            f"  Fetched:    {self.fetched}\n"
            f"  Rejected:   {self.rejected}\n"
            f"  Relevant:   {self.relevant}\n"
            f"  Duplicates: {self.duplicates}\n"
            f"  Saved:      {self.saved}"
        )


# ---------- MARKETAUX ----------

def clean_marketaux_article(raw_article, run_timestamp, stats):
    title = safe_get(raw_article, "title")
    url = safe_get(raw_article, "url")
    published_at = safe_get(raw_article, "published_at")

    if not title or not url or not published_at:
        stats.rejected += 1
        return None

    if not validate_published_at(published_at):
        stats.rejected += 1
        return None

    if is_generic_roundup(title):
        stats.rejected += 1
        return None

    search_text = title + " " + safe_get(raw_article, "description", "")
    matches = match_instruments_by_keywords(search_text)
    if not matches:
        stats.rejected += 1
        return None

    stats.relevant += 1
    instrument_matches = []
    for instrument, strength, matched_keywords in matches:
        logger.info(f"[MARKETAUX KEYWORD] '{title[:60]}' -> {instrument} via {matched_keywords}")
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


def fetch_marketaux_articles(run_timestamp, stats):
    published_after = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")
    params = {
        "api_token": NEWS_API_KEY,
        "language": "en",
        "countries": "in",
        "published_after": published_after,
        "limit": 50,
    }

    response = fetch_with_retry(MARKETAUX_URL, params)
    if response is None:
        return []

    data = response.json()
    raw_articles = data.get("data", [])
    stats.fetched = len(raw_articles)

    cleaned = [clean_marketaux_article(a, run_timestamp, stats) for a in raw_articles]
    return [c for c in cleaned if c is not None]


# ---------- FINNHUB ----------

def clean_finnhub_article(raw_article, run_timestamp, cutoff_timestamp, stats):
    headline = safe_get(raw_article, "headline")
    url = safe_get(raw_article, "url")
    unix_time = safe_get(raw_article, "datetime")

    if not headline or not url or unix_time is None:
        stats.rejected += 1
        return None

    if unix_time < cutoff_timestamp:
        stats.rejected += 1
        return None

    published_at = datetime.fromtimestamp(unix_time, tz=timezone.utc).isoformat()

    if not validate_published_at(published_at):
        stats.rejected += 1
        return None

    if is_generic_roundup(headline):
        stats.rejected += 1
        return None

    search_text = headline + " " + safe_get(raw_article, "summary", "")
    matches = match_instruments_by_keywords(search_text)
    if not matches:
        stats.rejected += 1
        return None

    stats.relevant += 1
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


def fetch_finnhub_articles(run_timestamp, stats):
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    if not finnhub_key:
        logger.info("Finnhub skipped: no API key set")
        return []

    cutoff_timestamp = (datetime.now(timezone.utc) - timedelta(hours=24)).timestamp()

    response = fetch_with_retry(FINNHUB_URL, {"category": "general", "token": finnhub_key})
    all_raw_articles = response.json() if response else []
    stats.fetched = len(all_raw_articles)

    
    cleaned = [clean_finnhub_article(a, run_timestamp, cutoff_timestamp, stats) for a in all_raw_articles]
    return [c for c in cleaned if c is not None]

# ---------- MAIN ----------

def main():
    init_db()
    existing_ids = get_existing_article_ids()
    run_timestamp = datetime.now(timezone.utc).isoformat()

    marketaux_stats = Stats("Marketaux")
    finnhub_stats = Stats("Finnhub")

    marketaux_records = fetch_marketaux_articles(run_timestamp, marketaux_stats)
    finnhub_records = fetch_finnhub_articles(run_timestamp, finnhub_stats)

    new_records = []
    seen_in_this_run = set()

    for record, stats in [(r, marketaux_stats) for r in marketaux_records] + \
                          [(r, finnhub_stats) for r in finnhub_records]:
        article_id = record["article"]["id"]
        if article_id in existing_ids or article_id in seen_in_this_run:
            stats.duplicates += 1
            continue
        new_records.append(record)
        seen_in_this_run.add(article_id)
        stats.saved += 1

    if new_records:
        save_articles(new_records)

    print("=" * 40)
    print("NEWS COLLECTION SUMMARY")
    print("=" * 40)
    print(marketaux_stats.report())
    print(finnhub_stats.report())
    print("=" * 40)

    logger.info(f"New articles added: {len(new_records)}")
    logger.info(f"Total articles now in database: {len(existing_ids) + len(new_records)}")


if __name__ == "__main__":
    main()