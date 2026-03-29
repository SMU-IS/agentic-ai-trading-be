"""
TradingView Ideas — Batch Ingestion
=====================================
Activated when the Docker container comes back up after downtime.
Scrapes recent Ideas for every tracked ticker, deduplicates, and pushes
new items into the Redis stream.

Usage (standalone test):
    python -m app.services.tradingview_ideas_batch_ingestion
"""

import json
import time
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from tradingview_scraper.symbols.ideas import Ideas

from app.services.storage import get_redis_client, publish_to_stream, check_and_mark_seen
from app.services.entity_watcher import get_tickers_from_redis

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")

POST_TIMESTAMP = "post_timestamps"


class TradingViewIdeasBatchIngestion:
    """
    One-shot batch scraper for TradingView Ideas.
    Iterates over all tracked tickers, scrapes recent Ideas,
    deduplicates via Redis, and publishes to a Redis stream.
    """

    ITEMS_PER_TICKER = 20
    PAGES_PER_TICKER = 5
    STREAM_NAME = "raw_news_stream"
    DEDUP_SET_NAME = "tradingview_ideas"
    INTER_TICKER_DELAY = 2
    BATCH_MAX_AGE_DAYS = 5

    def __init__(self, redis_client=None):
        self.redis = redis_client or get_redis_client()
        self.scraper = Ideas()

    # ── Row building ──────────────────────────────────────────────────────────

    @staticmethod
    def _parse_post_time(idea: dict) -> datetime | None:
        """Parse the post creation time as a UTC datetime."""
        raw_ts = idea.get("timestamp", 0)
        try:
            return datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            return None

    @staticmethod
    def _dedup_key(idea: dict) -> str:
        """Ideas deduplicates by author:timestamp:title."""
        author = idea.get("author", "unknown")
        timestamp = idea.get("timestamp", "")
        title = idea.get("title", "")
        return f"{author}:{timestamp}:{title}"

    @staticmethod
    def _build_row(idea: dict, ticker: str, source_label: str = "tradingview_ideas_batch") -> dict:
        """Transform a raw Ideas item into the unified row schema."""
        sg_tz = ZoneInfo("Asia/Singapore")
        raw_ts = idea.get("timestamp", 0)
        try:
            ts_iso = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc).astimezone(sg_tz).isoformat()
        except (ValueError, TypeError, OSError):
            ts_iso = datetime.now(sg_tz).isoformat()

        return {
            "id": f"tradingview_ideas:{idea.get('author', 'unknown')}:{raw_ts}",
            "content_type": "idea",
            "native_id": f"{idea.get('author', 'unknown')}:{raw_ts}:{idea.get('title', '')}",
            "source": source_label,
            "author": idea.get("author", "unknown"),
            "url": idea.get("chart_url", ""),
            "timestamps": ts_iso,
            "content": {
                "title": idea.get("title", ""),
                "body": idea.get("description", ""),
            },
            "engagement": {
                "total_comments": idea.get("comments_count", 0),
                "score": idea.get("likes_count", 0),
                "upvote_ratio": None,
            },
            "metadata": {
                "ticker": ticker,
                "source_section": "ideas",
                "preview_image": idea.get("preview_image", []),
                "views_count": idea.get("views_count", 0),
                "category": None,
            },
        }

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(self):
        """
        Run a single batch ingestion pass over all tracked tickers.
        Returns a summary dict with counts.
        """
        tickers = get_tickers_from_redis(self.redis)

        total_scraped = 0
        total_published = 0
        total_duplicates = 0
        total_too_old = 0
        errors = []

        cutoff = datetime.now(timezone.utc) - timedelta(days=self.BATCH_MAX_AGE_DAYS)

        for ticker in tickers:
            logger.info(f"[Ideas Batch] Scraping ideas for {ticker} ...")

            try:
                # Ideas.scrape() takes a plain symbol (no exchange prefix)
                result = self.scraper.scrape(
                    symbol=ticker,
                    startPage=1,
                    endPage=self.PAGES_PER_TICKER,
                    sort="recent"
                )

                if not isinstance(result, list):
                    logger.warning(f"[Ideas Batch] Unexpected result type for {ticker}: {type(result)}")
                    errors.append({"ticker": ticker, "error": f"unexpected type: {type(result)}"})
                    continue

                items = result[:self.ITEMS_PER_TICKER]
                total_scraped += len(items)

                for idea in items:
                    # Time boundary: skip posts older than BATCH_MAX_AGE_DAYS
                    post_time = self._parse_post_time(idea)
                    if post_time and post_time < cutoff:
                        total_too_old += 1
                        continue

                    dedup_key = self._dedup_key(idea)
                    if not dedup_key or dedup_key == "unknown::":
                        logger.warning(f"[Ideas Batch] Skipping idea with empty dedup key for {ticker}")
                        continue

                    if check_and_mark_seen(self.redis, dedup_key, self.DEDUP_SET_NAME):
                        total_duplicates += 1
                        continue

                    row = self._build_row(idea, ticker, source_label="tradingview_ideas_batch")
                    publish_to_stream(self.redis, self.STREAM_NAME, row)

                    sg_now = datetime.now(ZoneInfo("Asia/Singapore")).isoformat()
                    self.redis.hset(
                        f"{POST_TIMESTAMP}:{row['id']}",
                        mapping={
                            "scraped_timestamp": sg_now,
                        }
                    )
                    self.redis.expire(f"{POST_TIMESTAMP}:{row['id']}", 345600)  # 4 days

                    logger.info(f"⏱️ Post {row['id']}: Timestamped at Scraping Stage")

                    total_published += 1

            except Exception as e:
                logger.error(f"[Ideas Batch] Error scraping {ticker}: {e}", exc_info=True)
                errors.append({"ticker": ticker, "error": str(e)})

            time.sleep(self.INTER_TICKER_DELAY)

        summary = {
            "source": "tradingview_ideas_batch",
            "tickers_processed": len(tickers),
            "total_scraped": total_scraped,
            "total_published": total_published,
            "total_duplicates": total_duplicates,
            "total_too_old": total_too_old,
            "errors": errors,
        }
        logger.info(f"[Ideas Batch] Complete — {json.dumps(summary, indent=2)}")
        return summary


# ── Standalone entry point ────────────────────────────────────────────────────
if __name__ == "__main__":
    ingestion = TradingViewIdeasBatchIngestion()
    ingestion.run()
