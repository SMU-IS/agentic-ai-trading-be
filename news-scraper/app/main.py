import logging
import threading
from contextlib import asynccontextmanager

import praw
from fastapi import FastAPI

from app.core.config import env_config
from app.services.entity_watcher import EntityWatcherService
from app.services.reddit_batch_ingestion import RedditBatchService
from app.services.reddit_stream_ingestion import RedditStreamService
from app.services.storage import RedisStreamStorage

logger = logging.getLogger("uvicorn.error")


def run_stream_mode(reddit, storage, redis_client, base_subreddits):
    print("[*] STREAM MODE: Starting RedditStreamService")
    stream_service = RedditStreamService(reddit, storage, redis_client)
    stream_service.run(base_subreddits)


def run_batch_mode(reddit, storage, redis_client, base_subreddits):
    hash_key = "all_identified_tickers"
    existing_tickers = [
        t.decode() if isinstance(t, bytes) else t for t in redis_client.hkeys(hash_key)
    ]

    batch_service = RedditBatchService(reddit, storage, redis_client)
    resolved_subs = set(base_subreddits)

    for ticker in existing_tickers:
        subs_for_ticker = batch_service.resolve_subreddits_for_ticker(ticker)
        resolved_subs.update(subs_for_ticker)

    initial_batch_subs = list(resolved_subs)
    print(f"[*] Running initial batch for: {initial_batch_subs}")
    batch_service.run(initial_batch_subs)

    batch_service.run_worker()


def run_watcher_mode(redis_client):
    print("[*] WATCHER MODE: Starting EntityWatcherService")
    hash_key = "all_identified_tickers"
    entity_watcher = EntityWatcherService(redis_client, hash_key)
    entity_watcher.run()


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = RedisStreamStorage()
    redis_client = storage.r

    reddit = praw.Reddit(
        client_id=env_config.reddit_client_id,
        client_secret=env_config.reddit_client_secret,
        user_agent=env_config.reddit_user_agent,
    )

    base_subreddits = [
        "wallstreetbets",
        "stocks",
        "investing",
        "options",
        "stockmarket",
    ]
    if env_config.auto_scrape:
        print("Auto scrape is enabled")
        threading.Thread(
            target=run_stream_mode,
            args=(reddit, storage, redis_client, base_subreddits),
            daemon=True,
        ).start()

        threading.Thread(
            target=run_batch_mode,
            args=(reddit, storage, redis_client, base_subreddits),
            daemon=True,
        ).start()

        threading.Thread(
            target=run_watcher_mode,
            args=(redis_client,),
            daemon=True,
        ).start()

    else:
        print("Auto scrape disabled")

    yield


app = FastAPI(
    title="News Scraper Service",
    description="Scraps Reddit for news and stores in Redis",
    lifespan=lifespan,
)


@app.get("/healthcheck")
def healthcheck():
    try:
        redis_client = RedisStreamStorage().r
        redis_client.ping()

        return {"status": "News Scraper Service is healthy"}

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "News Scraper Service is unhealthy"}
