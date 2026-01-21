import time
from datetime import datetime, timedelta, timezone


class RedditBatchService:
    def __init__(self, reddit_client, storage):
        self.reddit_client = reddit_client
        self.storage = storage

    def run(self, subreddits, days=180, batch_size=50, sleep_seconds=0.0):
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        buffer = []

        for sub in subreddits:
            subreddit = self.reddit_client.subreddit(sub)
            print(f"Fetching posts from r/{sub}...")

            for post in subreddit.new(limit=None):
                post_time = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                if post_time < cutoff:
                    break

                row = {
                    "type": "post",
                    "source": "reddit_batch",
                    "post_id": post.id,
                    "post_url": post.url,
                    "title": post.title,
                    "body": post.selftext,
                    "author": str(post.author),
                    "created_utc": post_time.isoformat(),
                    "total_comments": post.num_comments,
                    "score": post.score,
                    "upvote_ratio": post.upvote_ratio,
                    "subreddit": post.subreddit.display_name,
                    "domain": post.domain,
                }

                buffer.append(row)

                if len(buffer) >= batch_size:
                    self.storage.save_batch(buffer)
                    print(f"Flushed {len(buffer)} posts to Redis.")
                    buffer.clear()

                if sleep_seconds:
                    time.sleep(sleep_seconds)

        if buffer:
            self.storage.save_batch(buffer)
            print(f"Flushed {len(buffer)} posts to Redis (final).")
