"""
TradingView Ideas — Stream Ingestion
======================================
Activated when running in cloud / real-time mode.
Continuously polls TradingView Ideas for each tracked ticker in a round-robin
fashion, deduplicating at both in-memory and Redis levels, and pushes new items
into the Redis stream.

Usage (standalone test):
    python -m app.services.tradingview_ideas_stream_ingestion
"""

import time
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from tradingview_scraper.symbols.ideas import Ideas

from app.services.storage import get_redis_client, publish_to_stream, check_and_mark_seen
from app.services.entity_watcher import get_tickers_from_redis

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")

POST_TIMESTAMP = "post_timestamps"


class TradingViewIdeasStreamIngestion:
    """
    Continuous polling scraper for TradingView Ideas.
    Uses dual-layer deduplication:
      1. In-memory set for fast filtering within a session
      2. Redis keys with 3-day TTL for persistence across restarts
    """

    ITEMS_PER_TICKER = 5
    STREAM_NAME = "raw_news_stream"
    DEDUP_SET_NAME = "tradingview_ideas"
    POLL_INTERVAL = 120          # Ideas update less frequently than Minds
    INTER_TICKER_DELAY = 3
    TICKER_REFRESH_INTERVAL = 300
    MAX_MEMORY_CACHE = 50_000

    def __init__(self, redis_client=None):
        self.redis = redis_client or get_redis_client()
        self.scraper = Ideas()
        self.seen_in_memory: set = set()
        self._running = True

    # ── Row building ──────────────────────────────────────────────────────────

    @staticmethod
    def _dedup_key(idea: dict) -> str:
        """Ideas deduplicates by author:timestamp:title."""
        author = idea.get("author", "unknown")
        timestamp = idea.get("timestamp", "")
        title = idea.get("title", "")
        return f"{author}:{timestamp}:{title}"

    @staticmethod
    def _build_row(idea: dict, ticker: str) -> dict:
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
            "source": "tradingview_ideas_stream",
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
        """Continuously poll TradingView Ideas in a round-robin across tickers."""
        tickers = get_tickers_from_redis(self.redis)
        last_ticker_refresh = time.time()
        cycle_count = 0

        logger.info(f"[Ideas Stream] Starting with {len(tickers)} tickers, polling every {self.POLL_INTERVAL}s")

        while self._running:
            cycle_count += 1
            cycle_published = 0
            cycle_duplicates = 0
            cycle_start = time.time()

            # Periodically refresh ticker list
            if time.time() - last_ticker_refresh > self.TICKER_REFRESH_INTERVAL:
                tickers = get_tickers_from_redis(self.redis)
                last_ticker_refresh = time.time()
                logger.info(f"[Ideas Stream] Refreshed tickers: {len(tickers)} active")

            for ticker_idx, ticker in enumerate(tickers):
                if not self._running:
                    break

                if ticker_idx > 0 and ticker_idx % 20 == 0:
                    logger.info(f"[Ideas Stream] Cycle {cycle_count} progress: {ticker_idx}/{len(tickers)} tickers")

                try:
                    result = self.scraper.scrape(
                        symbol=ticker,
                        startPage=1,
                        endPage=1,
                        sort="recent"
                    )

                    if not isinstance(result, list):
                        logger.warning(f"[Ideas Stream] Unexpected result for {ticker}")
                        continue

                    items = result[:self.ITEMS_PER_TICKER]

                    for idea in items:
                        dedup_key = self._dedup_key(idea)
                        if not dedup_key or dedup_key == "unknown::":
                            continue

                        # Layer 1: In-memory dedup
                        if dedup_key in self.seen_in_memory:
                            cycle_duplicates += 1
                            continue

                        # Layer 2: Redis dedup (persistent, 3-day TTL)
                        if check_and_mark_seen(self.redis, dedup_key, self.DEDUP_SET_NAME):
                            self.seen_in_memory.add(dedup_key)
                            cycle_duplicates += 1
                            continue

                        self.seen_in_memory.add(dedup_key)
                        row = self._build_row(idea, ticker)
                        publish_to_stream(self.redis, self.STREAM_NAME, row)

                        sg_now = datetime.now(ZoneInfo("Asia/Singapore")).isoformat()
                        self.redis.hset(
                            f"{POST_TIMESTAMP}:{row['id']}",
                            mapping={
                                "scraped_timestamp": sg_now,
                                "posted_timestamp":  row["timestamps"],
                            }
                        )
                        self.redis.expire(f"{POST_TIMESTAMP}:{row['id']}", 345600)  # 4 days

                        logger.info(f"⏱️ Post {row['id']}: Timestamped at Scraping Stage")

                        cycle_published += 1

                except Exception as e:
                    logger.error(f"[Ideas Stream] Error scraping {ticker}: {e}", exc_info=True)

                time.sleep(self.INTER_TICKER_DELAY)

            cycle_elapsed = time.time() - cycle_start
            logger.info(
                f"[Ideas Stream] Cycle {cycle_count} done in {cycle_elapsed:.1f}s — "
                f"published={cycle_published}, duplicates={cycle_duplicates}, "
                f"in_memory_cache={len(self.seen_in_memory)}"
            )

            # Prevent in-memory set from growing unbounded
            if len(self.seen_in_memory) > self.MAX_MEMORY_CACHE:
                logger.info("[Ideas Stream] Pruning in-memory dedup set")
                self.seen_in_memory.clear()

            # Wait for the remainder of the poll interval
            remaining = self.POLL_INTERVAL - cycle_elapsed
            if remaining > 0 and self._running:
                time.sleep(remaining)

        logger.info("[Ideas Stream] Stopped.")


# ── Standalone entry point ────────────────────────────────────────────────────
if __name__ == "__main__":
    ingestion = TradingViewIdeasStreamIngestion()
    ingestion.run()
