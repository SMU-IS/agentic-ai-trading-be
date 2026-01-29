import time
from datetime import datetime, timedelta, timezone
import prawcore


class RedditBatchService:
    def __init__(self, reddit_client, storage):
        self.reddit_client = reddit_client
        self.storage = storage

    def run(self, subreddits, days=180, batch_size=50, sleep_seconds=0.0):
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
            
            except Exception as e:
                print(f"Unexpected erorr for r/{sub}")
                continue
            
        if buffer:
            try:
                self.storage.save_batch(buffer)
                print(f"Flushed {len(buffer)} posts to Redis (final).")
            except Exception as e:
                print(f"Final Redit flush failed: {e}")
