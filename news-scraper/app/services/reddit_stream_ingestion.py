import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from app.core.logger import logger
import prawcore
import json

class RedditStreamService:
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

    def run(self, base_subreddits, stop_event):

        logger.info("[*] Reddit stream service started")
        subreddit_str = "+".join(base_subreddits)
        subreddit = self.reddit_client.subreddit(subreddit_str) 
              
        while True:

            if self.should_stop(stop_event):
                logger.info("🛑 Stream scraper stopped")
                return
            
            try:
                # stream_version = self.redis.get("stream_version")

                logger.info(f"[*] Streaming subreddits: {base_subreddits}")
                
                for post in subreddit.stream.submissions(skip_existing=True):
                    if self.should_stop(stop_event):
                        logger.info("🛑 Stream stopping immediately...")
                        return
                    
                    # if self.redis.get("stream_version") != stream_version:
                    #     print("[*] Stream version changed → rebuilding stream")
                    #     break

                    self.handle_post(post)

            except prawcore.exceptions.PrawcoreException:
                logger.exception("Reddit API error")
                time.sleep(5)

    def handle_post(self, post):
        POST_TIMESTAMP = "post_timestamps"
        try:
            post_time = datetime.fromtimestamp(post.created_utc, tz=timezone.utc).astimezone(self.sg_tz)

            row = {
                "id": f"reddit:{post.id}",
                "content_type": "post",
                "native_id": post.id,
                "source": "reddit_stream",
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
                    "category": None,
                }
            }

            self.storage.save(row)
            logger.info(f"Flushed r/{post.subreddit} posts to Redis.")


            sg_now = datetime.now(ZoneInfo("Asia/Singapore")).isoformat()

            post_key = f"{POST_TIMESTAMP}:reddit:{post.id}"
            self.redis.hset(
                post_key,
                mapping={
                    "scraped_timestamp": sg_now,
                    "posted_timestamp":  post_time.isoformat(),
                }
            )
            self.redis.expire(post_key, 345600)  # 4 days
            logger.info(f"⏱️ Post {post.id}: Timestamped at Scraping Stage")

            post_id = row["native_id"]
            reddit_post_time = datetime.fromisoformat(row["timestamps"]).timestamp()
            now_ts = datetime.now().timestamp()

            # Rolling posts per hour
            self.redis.zadd("newsscraper:metrics:posts_1d", {post_id: now_ts})

            # Average latency (overall)
            latency = now_ts - reddit_post_time
            self.redis.incrbyfloat("newsscraper:metrics:latency_sum", latency)
            self.redis.incr("newsscraper:metrics:latency_count")

            # latency per day
            latency_key = "newsscraper:metrics:latency_1d"   
            latency_value_key = "newsscraper:metrics:latency_values" 

            pipe = self.redis.pipeline()
            pipe.zadd(latency_key, {post_id: now_ts})       
            pipe.hset(latency_value_key, post_id, latency)  
            pipe.execute()
            
            time.sleep(0.1)

        except Exception:
            logger.exception(f"Failed to process post {post.id}")

    def build_subreddit_list(self, base_subreddits):
        subs = set(base_subreddits)

        entities = self.redis.hgetall("all_identified_tickers")
        for ticker, entity_json in entities.items():
            ticker_str = ticker.decode().lower() if isinstance(ticker, bytes) else ticker.lower()
            subs.add(ticker_str)

            
            entity_data = json.loads(entity_json.decode()) if isinstance(entity_json, bytes) else json.loads(entity_json)

            official = entity_data.get("OfficialName")
            if official:
                subs.add(self.normalise(official))

            for alias in entity_data.get("Aliases", []):
                subs.add(self.normalise(alias))

        return list(subs)


    def normalise(self, name):
        return "".join(c for c in name.lower() if c.isalnum())                        

