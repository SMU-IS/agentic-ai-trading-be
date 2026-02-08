import time
from datetime import datetime, timedelta, timezone
import prawcore
import json

class RedditStreamService:
    def __init__(self, reddit_client, storage, redis_client):
        self.reddit_client = reddit_client
        self.storage = storage
        self.redis = redis_client

    def run(self, base_subreddits):
        print("[*] Reddit stream service started")
        

        while True:
            try:
                subreddits = self.build_subreddit_list(base_subreddits)
                subreddit_str = "+".join(subreddits)
                stream_version = self.redis.get("stream_version")

                print(f"[*] Streaming subreddits: {subreddits}")

                subreddit = self.reddit_client.subreddit(subreddit_str)
                
                for post in subreddit.stream.submissions(skip_existing=True):
                    if self.redis.get("stream_version") != stream_version:
                        print("[*] Stream version changed → rebuilding stream")
                        break

                    self.handle_post(post)

            except prawcore.exceptions.PrawcoreException as e:
                print(f"Reddit API error: {e}")
                time.sleep(5)

    def handle_post(self, post):
        try:
            post_time = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)

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
                    "category": None
                }
            }

            try:
                self.storage.save(row)
                print(f"Flushed r/{post.subreddit} posts to Redis.")
            except Exception as e:
                print(f"Redis write failed for post {post.id}: {e}")
            
            time.sleep(0.1)

        except Exception as e:
            print(f"Failed to process post {post.id}: {e}")

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

