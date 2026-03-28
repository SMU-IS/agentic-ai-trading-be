import time
import json
import threading
from datetime import datetime, timedelta, timezone
import prawcore
from app.core.logger import logger

POST_TIMESTAMP = "post_timestamps"

class RedditBatchService:
    def __init__(self, reddit_client, storage, redis_client):
        self.reddit_client = reddit_client
        self.storage = storage
        self.redis = redis_client
        self.sg_tz = timezone(timedelta(hours=8))

    def should_stop(self, stop_event):
        if stop_event and stop_event.is_set():
            return True

        running_flag = self.redis.get("newsscraper:reddit:running")

        if running_flag is None or running_flag != "1":
            return True

        return False

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

    def run(self, subreddits, stop_event=None, days=5, batch_size=0, sleep_seconds=0.1):
        
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    
        logger.info(f"[*] Batch scraping subreddits: {subreddits}")

        threads = []
        max_threads = 5
        semaphore = threading.Semaphore(max_threads)

        for sub in subreddits:
            t = threading.Thread(
                target=self.scrape_with_limit,
                args=(semaphore, sub, stop_event, cutoff, batch_size, sleep_seconds),
                daemon=True
            )
            t.start()
            threads.append(t)

        for t in threads:
            t.join()
    def scrape_with_limit(self, semaphore, sub, stop_event, cutoff, batch_size, sleep_seconds):
        with semaphore:  
            self.scrape_subreddit(sub, stop_event, cutoff, batch_size, sleep_seconds)

    def scrape_subreddit(self, sub, stop_event, cutoff, batch_size, sleep_seconds):

        buffer = []
        
        try:
            subreddit = self.reddit_client.subreddit(sub)
            logger.info(f"Fetching posts from r/{sub}...")

            for post in subreddit.new(limit=None):
                
                if self.should_stop(stop_event):
                    logger.info("🛑 Batch scraper stopped mid-stream")
                    return
                
                post_key = f"{POST_TIMESTAMP}:reddit:{post.id}"

                if self.redis.exists(post_key):
                    logger.info(f"Skipping existing post {post.id}")
                    continue

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
                        logger.info(f"Flushed {len(buffer)} posts from r/{sub} to Redis.")
                        buffer.clear()
                    except Exception as e:
                        logger.exception(f"Redis batch write failed")
                        buffer.clear()

                post_id = row["native_id"]
                now_ts = datetime.now().timestamp()
                self.redis.zadd("newsscraper:metrics:posts_1d", {post_id: now_ts})

                if sleep_seconds:
                    time.sleep(sleep_seconds)

        except prawcore.exceptions.PrawcoreException as e:
            logger.exception(f"Reddit API error for r/{sub}")
            time.sleep(5)
            
        if buffer:
            self.storage.save_batch(buffer)
            logger.info(f"Flushed {len(buffer)} posts to Redis (final).")
