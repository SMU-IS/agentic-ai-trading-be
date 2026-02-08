import time
import json
from datetime import datetime, timedelta, timezone
import prawcore

class RedditBatchService:
    def __init__(self, reddit_client, storage, redis_client):
        self.reddit_client = reddit_client
        self.storage = storage
        self.redis = redis_client

    def run_worker(self, days=180, batch_size=50):
        print("[*] Batch worker started, waiting for tickers...")

        processed_key = "batch_processed_tickers"

        while True:
            _, ticker = self.redis.brpop("batch_queue")
            ticker = ticker.decode() if isinstance(ticker, bytes) else ticker

            if self.redis.sismember(processed_key, ticker):
                print(f"[~] Ticker {ticker} already processed, skipping")
                continue

            print(f"[+] Running batch for ticker: {ticker}")
            subreddits = self.resolve_subreddits_for_ticker(ticker)
            
            # print(subreddits)
            self.run(subreddits, days, batch_size)
            self.redis.sadd(processed_key, ticker)

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

    def run(self, subreddits, days=180, batch_size=50, sleep_seconds=0.1):
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        buffer = []
        for sub in subreddits:
            try:
                subreddit = self.reddit_client.subreddit(sub)
                print(f"Fetching posts from r/{sub}...")

                for post in subreddit.new(limit=None):
                    try:
                        post_time = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
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

                        if len(buffer) >= batch_size:
                            try:
                                self.storage.save_batch(buffer)
                                print(f"Flushed {len(buffer)} posts to Redis.")
                                buffer.clear()
                            except Exception as e:
                                print(f"Redis batch write failed: {e}")
                                buffer.clear()

                        if sleep_seconds:
                            time.sleep(sleep_seconds)
                    except Exception as e:
                        print(f"Failed to process post in r/{sub}: {e}")
                        continue

            except prawcore.exceptions.PrawcoreException as e:
                print(f"Reddit API error for r/{sub}: {e}")
                time.sleep(5)
                continue
            
        if buffer:
            self.storage.save_batch(buffer)
            print(f"Flushed {len(buffer)} posts to Redis (final).")
