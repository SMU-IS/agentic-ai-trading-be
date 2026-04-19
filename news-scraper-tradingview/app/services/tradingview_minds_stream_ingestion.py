"""
TradingView Minds — Stream Ingestion
======================================
Activated when running in cloud / real-time mode.
Continuously polls TradingView Minds for each tracked ticker in a round-robin
fashion, deduplicating at both in-memory and Redis levels, and pushes new items
into the Redis stream.

Usage (standalone test):
    python -m app.services.tradingview_minds_stream_ingestion
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from tradingview_scraper.symbols.minds import Minds

from app.services.storage import get_redis_client, publish_to_stream, check_and_mark_seen
from app.services.entity_watcher import get_tickers_from_redis, get_ticker_candidates

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")

POST_TIMESTAMP = "post_timestamps"


class TradingViewMindsStreamIngestion:
    """
    Continuous polling scraper for TradingView Minds.
    Uses dual-layer deduplication:
      1. In-memory set for fast filtering within a session
      2. Redis keys with 3-day TTL for persistence across restarts
    """

    ITEMS_PER_TICKER = 5
    STREAM_NAME = "raw_news_stream"
    DEDUP_SET_NAME = "tradingview_minds"
    POLL_INTERVAL = 60           # seconds between full cycles
    INTER_TICKER_DELAY = 3       # seconds between individual ticker scrapes
    TICKER_REFRESH_INTERVAL = 300  # re-read ticker list every 5 min
    MAX_MEMORY_CACHE = 50_000
    STREAM_BOOTSTRAP_MINUTES = 15  # on first run (no HWM), only look back this far
    HWM_KEY_PREFIX = "hwm:tradingview_minds"  # per-ticker high-water mark in Redis

    def __init__(self, redis_client=None):
        self.redis = redis_client or get_redis_client()
        self.scraper = Minds()
        self.seen_in_memory: set = set()
        self._running = True

    # ── Time filtering ─────────────────────────────────────────────────────────

    @staticmethod
    def _parse_post_time(mind: dict) -> datetime | None:
        """Parse the post creation time as a UTC datetime."""
        created_str = mind.get("created", "")
        try:
            return datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None

    def _get_hwm(self, ticker: str) -> datetime:
        """Get the high-water mark for a ticker. Falls back to now - bootstrap window."""
        key = f"{self.HWM_KEY_PREFIX}:{ticker}"
        val = self.redis.get(key)
        if val:
            try:
                return datetime.fromisoformat(val)
            except (ValueError, TypeError):
                pass
        return datetime.now(timezone.utc) - timedelta(minutes=self.STREAM_BOOTSTRAP_MINUTES)

    def _set_hwm(self, ticker: str, ts: datetime):
        """Update the high-water mark for a ticker."""
        key = f"{self.HWM_KEY_PREFIX}:{ticker}"
        self.redis.set(key, ts.isoformat(), ex=7 * 86400)  # expire after 7 days of inactivity

    # ── Row building ──────────────────────────────────────────────────────────

    @staticmethod
    def _dedup_key(mind: dict) -> str:
        """Minds deduplicates by uid."""
        return mind.get("uid", "")

    @staticmethod
    def _build_row(mind: dict, ticker: str) -> dict:
        """Transform a raw Minds item into the unified row schema."""
        author_info = mind.get("author", {})
        created_str = mind.get("created", "")

        sg_tz = ZoneInfo("Asia/Singapore")
        try:
            ts = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            ts_iso = ts.astimezone(sg_tz).isoformat()
        except (ValueError, TypeError):
            ts_iso = created_str or datetime.now(sg_tz).isoformat()

        uid = mind.get("uid", "")

        symbols = mind.get("symbols", [])
        tickers = [s.split(":")[-1] if ":" in s else s for s in symbols]

        return {
            "id": f"tradingview_minds:{uid}",
            "content_type": "mind",
            "native_id": uid,
            "source": "tradingview_minds_stream",
            "author": author_info.get("username", "unknown"),
            "url": mind.get("url", ""),
            "timestamps": ts_iso,
            "content": {
                "title": "",
                "body": mind.get("text", "")
            },
            "engagement": {
                "total_comments": mind.get("total_comments", 0),
                "score": mind.get("total_likes", 0),
                "upvote_ratio": None,
            },
            "metadata": {
                "ticker": tickers,
                "symbols": symbols,
                "source_section": "minds",
                "category": None,
            },
        }

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(self):
        """Continuously poll TradingView Minds in a round-robin across tickers."""
        tickers = get_tickers_from_redis(self.redis)
        last_ticker_refresh = time.time()
        cycle_count = 0

        logger.info(f"[Minds Stream] Starting with {len(tickers)} tickers, polling every {self.POLL_INTERVAL}s")

        while self._running:
            cycle_count += 1
            cycle_published = 0
            cycle_duplicates = 0
            cycle_start = time.time()

            # Periodically refresh ticker list
            if time.time() - last_ticker_refresh > self.TICKER_REFRESH_INTERVAL:
                tickers = get_tickers_from_redis(self.redis)
                last_ticker_refresh = time.time()
                logger.info(f"[Minds Stream] Refreshed tickers: {len(tickers)} active")

            for ticker_idx, ticker in enumerate(tickers):
                if not self._running:
                    break

                if ticker_idx > 0 and ticker_idx % 20 == 0:
                    logger.info(f"[Minds Stream] Cycle {cycle_count} progress: {ticker_idx}/{len(tickers)} tickers")

                candidates = get_ticker_candidates(ticker)
                result = None
                matched_symbol = None

                try:
                    for candidate in candidates:
                        result = self.scraper.get_minds(
                            symbol=candidate,
                            sort="recent",
                            limit=self.ITEMS_PER_TICKER
                        )
                        if result.get("status") == "success":
                            matched_symbol = candidate
                            break

                    if not matched_symbol:
                        continue

                    items = result.get("data", [])

                    # Per-ticker high-water mark: only accept posts newer than HWM
                    hwm = self._get_hwm(ticker)
                    max_post_time = hwm  # track newest post to update HWM

                    for mind in items:
                        # Time boundary: skip posts at or before the high-water mark
                        post_time = self._parse_post_time(mind)
                        if post_time and post_time <= hwm:
                            cycle_duplicates += 1
                            continue

                        if post_time and post_time > max_post_time:
                            max_post_time = post_time

                        dedup_key = self._dedup_key(mind)
                        if not dedup_key:
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

                        # Layer 3: preproc dedup check
                        preproc_dedup_key = f"preproc_dedup:{dedup_key}"
                        if self.redis.exists(preproc_dedup_key):
                            self.seen_in_memory.add(dedup_key)
                            cycle_duplicates += 1
                            continue

                        self.seen_in_memory.add(dedup_key)
                        row = self._build_row(mind, ticker)
                        publish_to_stream(self.redis, self.STREAM_NAME, row)

                        sg_now = datetime.now(ZoneInfo("Asia/Singapore")).isoformat()
                        post_key = f"{POST_TIMESTAMP}:{row['id']}"
                        if not self.redis.exists(post_key):
                            self.redis.hset(
                                post_key,
                                mapping={
                                    "scraped_timestamp": sg_now,
                                    "posted_timestamp":  row["timestamps"],
                                }
                            )
                            self.redis.expire(post_key, 345600)  # 4 days

                        logger.info(f"⏱️ Post {row['id']}: Timestamped at Scraping Stage")

                        cycle_published += 1

                    # Update high-water mark for this ticker
                    if max_post_time > hwm:
                        self._set_hwm(ticker, max_post_time)

                except Exception as e:
                    logger.error(f"[Minds Stream] Error scraping {ticker}: {e}", exc_info=True)

                time.sleep(self.INTER_TICKER_DELAY)

            cycle_elapsed = time.time() - cycle_start
            logger.info(
                f"[Minds Stream] Cycle {cycle_count} done in {cycle_elapsed:.1f}s — "
                f"published={cycle_published}, duplicates={cycle_duplicates}, "
                f"in_memory_cache={len(self.seen_in_memory)}"
            )

            # Prevent in-memory set from growing unbounded
            if len(self.seen_in_memory) > self.MAX_MEMORY_CACHE:
                logger.info("[Minds Stream] Pruning in-memory dedup set")
                self.seen_in_memory.clear()

            # Wait for the remainder of the poll interval
            remaining = self.POLL_INTERVAL - cycle_elapsed
            if remaining > 0 and self._running:
                time.sleep(remaining)

        logger.info("[Minds Stream] Stopped.")


# ── Standalone entry point ────────────────────────────────────────────────────
if __name__ == "__main__":
    ingestion = TradingViewMindsStreamIngestion()
    ingestion.run()
