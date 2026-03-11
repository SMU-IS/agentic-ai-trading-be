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

    def run(self, base_subreddits, stop_event):

        logger.info("[*] Reddit stream service started")
        subreddit_str = "+".join(base_subreddits)
        subreddit = self.reddit_client.subreddit(subreddit_str) 
              
        while not stop_event.is_set():
            try:
                # stream_version = self.redis.get("stream_version")

                logger.info(f"[*] Streaming subreddits: {base_subreddits}")
                
                for post in subreddit.stream.submissions(skip_existing=True):
                    if stop_event.is_set():
                        logger.info("[*] Stream stopping...")
                        break
                    
                    # if self.redis.get("stream_version") != stream_version:
                    #     print("[*] Stream version changed → rebuilding stream")
                    #     break

                    self.handle_post(post)

            except prawcore.exceptions.PrawcoreException as e:
                logger.exception(f"Reddit API error")
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

            self.redis.hset(
                f"{POST_TIMESTAMP}:reddit:{post.id}",
                mapping={
                    "scraped_timestamp": sg_now,
                    "vectorised_timestamp": "",
                }
            )
            logger.info(f"⏱️ Post {post.id}: Timestamped at Scraping Stage")
            
            time.sleep(0.1)

        except Exception as e:
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

