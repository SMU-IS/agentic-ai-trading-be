"""
TradingView Minds — Batch Ingestion
====================================
Activated when the Docker container comes back up after downtime.
Scrapes the most recent Minds posts for every tracked ticker, deduplicates,
and pushes new items into the Redis stream in one batch.

Usage (standalone test):
    python -m app.services.tradingview_minds_batch_ingestion
"""

import json
import time
import logging
from datetime import datetime, timezone

from tradingview_scraper.symbols.minds import Minds

from app.services.storage import get_redis_client, publish_to_stream, check_and_mark_seen
from app.services.entity_watcher import get_tickers_from_redis, get_ticker_candidates

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")


class TradingViewMindsBatchIngestion:
    """
    One-shot batch scraper for TradingView Minds.
    Iterates over all tracked tickers, scrapes recent Minds posts,
    deduplicates via Redis, and publishes to a Redis stream.
    """

    ITEMS_PER_TICKER = 20
    STREAM_NAME = "raw_news_stream"
    DEDUP_SET_NAME = "tradingview_minds"
    INTER_TICKER_DELAY = 2

    def __init__(self, redis_client=None):
        self.redis = redis_client or get_redis_client()
        self.scraper = Minds()

    # ── Row building ──────────────────────────────────────────────────────────

    @staticmethod
    def _dedup_key(mind: dict) -> str:
        """Minds deduplicates by uid."""
        return mind.get("uid", "")

    @staticmethod
    def _build_row(mind: dict, ticker: str, source_label: str = "tradingview_minds_batch") -> dict:
        """Transform a raw Minds item into the unified row schema."""
        author_info = mind.get("author", {})
        created_str = mind.get("created", "")

        try:
            ts = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            ts_iso = ts.isoformat()
        except (ValueError, TypeError):
            ts_iso = created_str or datetime.now(timezone.utc).isoformat()

        uid = mind.get("uid", "")

        symbols = mind.get("symbols", [])
        tickers = [s.split(":")[-1] if ":" in s else s for s in symbols]

        return {
            "id": f"tradingview_minds:{uid}",
            "content_type": "mind",
            "native_id": uid,
            "source": source_label,
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
        """
        Run a single batch ingestion pass over all tracked tickers.
        Returns a summary dict with counts.
        """
        tickers = get_tickers_from_redis(self.redis)

        total_scraped = 0
        total_published = 0
        total_duplicates = 0
        errors = []

        for ticker in tickers:
            candidates = get_ticker_candidates(ticker)
            result = None
            matched_symbol = None

            try:
                for candidate in candidates:
                    logger.info(f"[Minds Batch] Scraping {candidate} ...")
                    result = self.scraper.get_minds(
                        symbol=candidate,
                        sort="recent",
                        limit=self.ITEMS_PER_TICKER
                    )
                    if result.get("status") == "success":
                        matched_symbol = candidate
                        break

                if not matched_symbol:
                    logger.warning(f"[Minds Batch] No data found for {ticker} across all exchanges")
                    continue

                items = result.get("data", [])
                total_scraped += len(items)

                for mind in items:
                    dedup_key = self._dedup_key(mind)
                    if not dedup_key:
                        logger.warning(f"[Minds Batch] Skipping mind with empty uid for {ticker}")
                        continue

                    if check_and_mark_seen(self.redis, dedup_key, self.DEDUP_SET_NAME):
                        total_duplicates += 1
                        continue

                    row = self._build_row(mind, ticker, source_label="tradingview_minds_batch")
                    publish_to_stream(self.redis, self.STREAM_NAME, row)
                    total_published += 1

            except Exception as e:
                logger.error(f"[Minds Batch] Error scraping {ticker}: {e}", exc_info=True)
                errors.append({"ticker": ticker, "error": str(e)})

            time.sleep(self.INTER_TICKER_DELAY)

        summary = {
            "source": "tradingview_minds_batch",
            "tickers_processed": len(tickers),
            "total_scraped": total_scraped,
            "total_published": total_published,
            "total_duplicates": total_duplicates,
            "errors": errors,
        }
        logger.info(f"[Minds Batch] Complete — {json.dumps(summary, indent=2)}")
        return summary


# ── Standalone entry point ────────────────────────────────────────────────────
if __name__ == "__main__":
    ingestion = TradingViewMindsBatchIngestion()
    ingestion.run()
