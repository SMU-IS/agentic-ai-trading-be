import time
from datetime import datetime, timedelta, timezone

class RedditStreamService:
    def __init__(self, reddit_client, storage):
        self.reddit_client = reddit_client
        self.storage = storage

    def run(self, subreddits):
        subreddit = self.reddit_client.subreddit(subreddits)

        for post in subreddit.stream.submissions(skip_existing=True):
            post_time = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)

            self.storage.save({
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
            })

            time.sleep(0.1)
