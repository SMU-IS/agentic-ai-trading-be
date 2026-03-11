import time
import json
from datetime import datetime, timedelta, timezone
import prawcore
from zoneinfo import ZoneInfo
from app.core.logger import logger

POST_TIMESTAMP = "post_timestamps"

class RedditBatchService:
    def __init__(self, reddit_client, storage, redis_client):
        self.reddit_client = reddit_client
        self.storage = storage
        self.redis = redis_client
        self.sg_tz = timezone(timedelta(hours=8))

    def run_worker(self, stop_event, days=180, batch_size=50):
        logger.info("[*] Batch worker started, waiting for tickers...")

        processed_key = "batch_processed_tickers"

        while not stop_event.is_set():
            result = self.redis.brpop("batch_queue", timeout=5)
            
            if stop_event.is_set():
                break
            if result is None:
                continue

            _, ticker = result
            ticker = ticker.decode() if isinstance(ticker, bytes) else ticker

            if self.redis.sismember(processed_key, ticker):
                logger.info(f"[~] Ticker {ticker} already processed, skipping")
                continue

            logger.info(f"[+] Running batch for ticker: {ticker}")
            subreddits = self.resolve_subreddits_for_ticker(ticker)

            self.run(subreddits, days, batch_size)
            self.redis.sadd(processed_key, ticker)
        
        logger.info("[*] Batch worker stopped")

    def resolve_subreddits_for_ticker(self, ticker):

        entity_json = self.redis.hget("all_identified_tickers", ticker)
        if not entity_json:
            return []

        entity = json.loads(entity_json)

        subs = {ticker.lower()}

        official = entity.get("OfficialName")
        if official:
            subs.add(self.normalise(official))

        for alias in entity.get("Aliases", []):
            subs.add(self.normalise(alias))

        return list(subs)

    def normalise(self, name):
        return "".join(c for c in name.lower() if c.isalnum())

    def run(self, subreddits, days=5, batch_size=50, sleep_seconds=0.1):
        new_post_counter = "newsscraper:post_ingested"
        self.redis.set("newsscraper:ingestion_start_time", datetime.now().timestamp())
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        buffer = []
        logger.info(f"[*] Batch scraping subreddits: {subreddits}")
        for sub in subreddits:
            try:  
                subreddit = self.reddit_client.subreddit(sub)
                logger.info(f"Fetching posts from r/{sub}...")

                for post in subreddit.new(limit=None):
                    try:
                        sg_tz = timezone(timedelta(hours=8))
                        post_time = datetime.fromtimestamp(post.created_utc, tz=timezone.utc).astimezone(sg_tz)
                        if post_time < cutoff:
                            break

                        row = {
                            "id": f"reddit:{post.id}",
                            "content_type": "post",
                            "native_id": post.id,
                            "source": "reddit_batch",
                            "author": str(post.author),
                            "url": post.url,
                            "timestamps": post_time.isoformat(),
                            "content":{
                                "title": post.title,
                                "body": post.selftext
                            },
                            "engagement":{
                                "total_comments": post.num_comments,
                                "score": post.score,
                                "upvote_ratio": post.upvote_ratio,
                            },
                            "metadata":{
                                "subreddit": post.subreddit.display_name,
                                "category": None
                            }
                        }

                        buffer.append(row)
                        self.redis.incr(new_post_counter)
                        total = int(self.redis.get("newsscraper:post_ingested"))
                        start = float(self.redis.get("newsscraper:ingestion_start_time"))

                        hours = (datetime.now().timestamp() - start) / 3600

                        avg = total / hours
                        self.redis.set("newsscraper:avg_per_hour", avg)

                        sg_now = datetime.now(self.sg_tz).isoformat()

                        self.redis.hset(
                            f"{POST_TIMESTAMP}:reddit:{post.id}",
                            mapping={
                                "scraped_timestamp": sg_now,
                                "vectorised_timestamp": ""
                            }
                        )

                        logger.info(
                            "⏱️ Post %s timestamped at scraping stage (batch)",
                            post.id,
                        )


                        if len(buffer) >= batch_size:
                            try:
                                self.storage.save_batch(buffer)
                                logger.info(f"Flushed {len(buffer)} posts to Redis.")
                                buffer.clear()
                            except Exception as e:
                                logger.exception(f"Redis batch write failed")
                                buffer.clear()

                        if sleep_seconds:
                            time.sleep(sleep_seconds)
                    except Exception as e:
                        logger.exception(f"Failed to process post in r/{sub}")
                        continue

            except prawcore.exceptions.PrawcoreException as e:
                logger.exception(f"Reddit API error for r/{sub}")
                time.sleep(5)
                continue
            
        if buffer:
            self.storage.save_batch(buffer)
            logger.info(f"Flushed {len(buffer)} posts to Redis (final).")
