import os

# Set required env vars before any app module is imported.
# conftest.py is loaded by pytest before test modules are collected.
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "")
os.environ.setdefault("EVENT_STREAM", "test_event_redis_stream")
os.environ.setdefault("SENTIMENT_STREAM", "test_sentiment_redis_stream")

