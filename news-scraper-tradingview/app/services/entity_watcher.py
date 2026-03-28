"""
Watches the Redis hash 'all_identified_tickers' for new tickers,
pushes them into a batch_queue, and bumps a stream_version flag
so that streaming ingestion loops can pick up changes.

Also exposes helper functions used by the ingestion scripts.
"""

import time
import logging

logger = logging.getLogger(__name__)

# ── Exchange prefixes to try for Minds API ───────────────────────────────────
# TradingView Minds requires EXCHANGE:SYMBOL format but we don't store exchange
# info in Redis, so callers should try these in order until one succeeds.
EXCHANGE_CANDIDATES = ["NASDAQ", "NYSE", "AMEX"]

# ── Fixed top-10 tickers always scraped ──────────────────────────────────────
TOP_10_TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK.B", "JPM", "V"]


class EntityWatcherService:
\
    def __init__(self, redis_client, hash_key="all_identified_tickers"):
        self.redis = redis_client
        self.hash_key = hash_key

    def run(self, poll_interval=5):
        print(f"[*] Watching hash '{self.hash_key}' for new entities...")

        processed_set = "entity_processed_set"

        while True:
            entities = self.redis.hgetall(self.hash_key)

            updated = False

            for ticker in entities:
                ticker = ticker.decode() if isinstance(ticker, bytes) else ticker
                if self.redis.sismember(processed_set, ticker):
                    continue

                print(f"[+] New entity detected: {ticker}")
                self.redis.lpush("batch_queue", ticker)
                self.redis.sadd(processed_set, ticker)
                updated = True

            if updated:
                self.redis.set("stream_version", time.time())

            time.sleep(poll_interval)


# ── Helper functions used by ingestion scripts ────────────────────────────────

def get_hot_tickers_from_event_stream(redis_client) -> list:
    """
    Scan 'eventidentification:ticker:*' keys to find hot tickers identified
    from Reddit data this week.  Returns a deduplicated list of ticker strings
    that are NOT already in TOP_10_TICKERS.
    """
    try:
        keys = redis_client.keys("eventidentification:ticker:*")
        hot = []
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            # Key format: eventidentification:ticker:SYMBOL
            parts = key_str.split(":")
            if len(parts) >= 3:
                ticker = parts[2].upper()
                if ticker not in TOP_10_TICKERS and ticker not in hot:
                    hot.append(ticker)
        if hot:
            logger.info(f"[EntityWatcher] Found {len(hot)} hot tickers from event stream: {hot}")
        return hot
    except Exception as e:
        logger.error(f"[EntityWatcher] Failed to read hot tickers from event stream: {e}")
        return []


def get_tickers_from_redis(redis_client) -> list:
    """
    Build the final ticker list for scraping:
      1. Start with the fixed TOP_10_TICKERS (always included).
      2. Append hot tickers from 'eventidentification:ticker:*' that are not
         already in the top-10.
    Returns a deduplicated list of plain ticker strings.
    """
    tickers: list[str] = list(TOP_10_TICKERS)  # start with fixed base

    hot_tickers = get_hot_tickers_from_event_stream(redis_client)
    for t in hot_tickers:
        if t not in tickers:
            tickers.append(t)

    logger.info(f"[EntityWatcher] Final ticker list ({len(tickers)}): {tickers}")
    return tickers


def get_ticker_candidates(ticker: str) -> list[str]:
    """
    Return a list of exchange-prefixed candidates to try for the Minds API.
    e.g. 'AAPL' → ['NASDAQ:AAPL', 'NYSE:AAPL', 'AMEX:AAPL']

    If the ticker already contains ':', return it as-is in a single-item list.
    """
    if ":" in ticker:
        return [ticker]
    return [f"{exchange}:{ticker}" for exchange in EXCHANGE_CANDIDATES]