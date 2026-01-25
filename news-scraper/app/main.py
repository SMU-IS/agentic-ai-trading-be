import sys
import praw
from services.storage import RedisStreamStorage
from services.reddit_stream_ingestion import RedditStreamService
from services.reddit_batch_ingestion import RedditBatchService
from config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT

SUBREDDITS = ["wallstreetbets", "stocks", "investing", "options",
             "securityanalysis", "stockmarket", "techstocks",
             "tsla", "aapl", "nvda", "msft"]

mode = sys.argv[1] if len(sys.argv) > 1 else "stream"

reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT
)
storage = RedisStreamStorage()

if mode == "batch":
    RedditBatchService(reddit, storage).run(SUBREDDITS)
elif mode == "stream":
    RedditStreamService(reddit, storage).run("+".join(SUBREDDITS))
else:
    raise ValueError("Use: stream or batch")
