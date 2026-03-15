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

def get_tickers_from_redis(redis_client) -> list:
    """
    Retrieve all tickers from the Redis hash 'all_identified_tickers'.
    Returns a list of plain ticker strings (e.g. ['AAPL', 'TSLA', ...]).
    Returns an empty list if the hash is empty (the caller should handle this).
    """
    try:
        ticker_hash = redis_client.hgetall("all_identified_tickers")
        if ticker_hash:
            tickers = [
                t.decode() if isinstance(t, bytes) else t
                for t in ticker_hash.keys()
            ]
            logger.info(f"Loaded {len(tickers)} tickers from Redis: {tickers[:10]}...")
            return tickers
        else:
            logger.warning("No tickers found in Redis 'all_identified_tickers'.")
            return []
    except Exception as e:
        logger.error(f"Failed to read tickers from Redis: {e}")
        return []


def get_ticker_candidates(ticker: str) -> list[str]:
    """
    Return a list of exchange-prefixed candidates to try for the Minds API.
    e.g. 'AAPL' → ['NASDAQ:AAPL', 'NYSE:AAPL', 'AMEX:AAPL']

    If the ticker already contains ':', return it as-is in a single-item list.
    """
    if ":" in ticker:
        return [ticker]
    return [f"{exchange}:{ticker}" for exchange in EXCHANGE_CANDIDATES]