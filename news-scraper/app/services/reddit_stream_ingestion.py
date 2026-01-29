import time
from datetime import datetime, timedelta, timezone
import prawcore

class RedditStreamService:
    def __init__(self, reddit_client, storage):
        self.reddit_client = reddit_client
        self.storage = storage

    def run(self, subreddits):
        subreddit = self.reddit_client.subreddit(subreddits)

        while True:
            try:
                for post in subreddit.stream.submissions(skip_existing=True): 
                    try:

                        post_time = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)

                        row = {
                            "type": "post",
                            "source": "reddit_stream",
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

                        try:
                            self.storage.save(row)
                        except Exception as e:
                            print(f"Redis write failed for post {post.id}: {e}")
                        
                        time.sleep(0.1)

                    except Exception as e:
                        print(f"Failed to process post {post.id}: {e}")
                        continue

            except prawcore.exceptions.PrawcoreException as e:
                print(f"Reddit API error: {e}")
                time.sleep(5)
                continue
            
            except Exception as e:
                print(f"Unexpected error: {e}")
                continue

