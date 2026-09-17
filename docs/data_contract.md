# Data Contract — Trading Data Engine (Indian Market Edition)

This document describes exactly what data this pipeline produces.

**Target instrument:** NIFTY 50 (India's benchmark stock index)

## Database location

`data/trading.db` (SQLite)

## Table: `articles`

One row per unique news article (deduplicated by URL hash).

| Column | Type | Meaning |
|---|---|---|
| `id` | TEXT (PK) | SHA-256 hash of the article URL, truncated to 12 chars. |
| `title` | TEXT | Original headline. |
| `description` | TEXT | Cleaned summary (HTML stripped, capped at 1000 chars). May be NULL. |
| `source` | TEXT | Publisher name. |
| `url` | TEXT | Original article URL. |
| `provider` | TEXT | `"marketaux"` or `"finnhub"`. |
| `published_at` | TEXT (ISO 8601, UTC) | Validated: rejected if malformed or future-dated. |
| `collected_at` | TEXT (ISO 8601, UTC) | When our system found this article — use this (not `published_at`) to avoid look-ahead bias. |
| `raw_json` | TEXT | Full original API response, preserved for reprocessing. |

## Table: `article_instruments`

| Column | Type | Meaning |
|---|---|---|
| `instrument` | TEXT | Always `NIFTY50` currently. |
| `match_type` | TEXT | Always `"keyword"` — Marketaux entity matching is not used for this instrument (no verified entity-symbol mapping exists for the Nifty 50 index). |
| `match_strength` | REAL (0–1) | Confidence based on strongest matched keyword. Direct India-market terms (`nifty`, `sensex`, `rbi`) score 0.5–0.9. Global macro terms (`federal reserve`, `inflation`, `oil prices`) score 0.3–0.4 — included because global macro news demonstrably affects Indian markets, but weighted lower since it's a weaker, more indirect signal. |
| `sentiment` | REAL or NULL | **Always NULL currently** — no entity-based sentiment source is used for this instrument. NULL means "not available," not neutral. |
| `relevance_score` | REAL (0–1) | `0.7 × match_strength + 0.3 × recency`. |

## Table: `market_candles`

| Column | Type | Meaning |
|---|---|---|
| `instrument` | TEXT | Always `NIFTY50`. |
| `timestamp` | TEXT | Hourly candle time, IST (`+05:30`), as provided by Yahoo Finance via `yfinance`. |
| `open`, `high`, `low`, `close` | REAL | Rounded to 2 decimal places. Validated for physical consistency. |
| `volume` | REAL | Real trading volume — available because this is an exchange-traded index/proxy, unlike OTC forex. |
| `provider` | TEXT | `"yfinance"`. |

## Known limitations

- **`yfinance` is unofficial** — it scrapes Yahoo Finance rather than using a sanctioned API. It can break without warning if Yahoo changes something. Monitor `logs/market_collector.log` for sustained failures.
- **News coverage is inherently sparse** for a single index — expect roughly 1-3 relevant articles per collection cycle, not a constant stream.
- **No entity-based matching** — 100% keyword-based, meaning some false positives/negatives are expected and inherent to the approach, not a bug.
- **This pipeline replaced two earlier instrument sets** during development (EUR/USD-GBP/USD-XAU/USD, then individual NSE stocks) before settling on NIFTY 50. Earlier session history may reference those; this document reflects only the current, final state.

## Example query

```sql
SELECT a.title, a.description, ai.relevance_score
FROM articles a
JOIN article_instruments ai ON a.id = ai.article_id
WHERE ai.relevance_score > 0.5
ORDER BY a.published_at DESC;
```
