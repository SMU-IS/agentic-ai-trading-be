import os

# Set required env vars before any app module is imported.
# conftest.py is loaded by pytest before test modules are collected.
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "")
os.environ.setdefault("NEWS_STREAM", "test_news_stream")
os.environ.setdefault("PREPROC_STREAM", "test_preproc_redis_stream")

