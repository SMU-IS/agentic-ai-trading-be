import os
import sys
from unittest.mock import MagicMock

# Mock heavy/unavailable packages before any app module is imported
for mod in [
    "boto3",
    "app.scripts.aws_bucket_access",
    "app.services._03_event_identification",
    "nomic",
    "langchain_groq",
    "langchain_core",
    "langchain_core.output_parsers",
    "langchain_core.prompts",
    "langchain_core.language_models",
    "langchain_core.callbacks",
]:
    sys.modules.setdefault(mod, MagicMock())

# Set required env vars before any app module is imported.
# conftest.py is loaded by pytest before test modules are collected.
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "")
os.environ.setdefault("TICKER_STREAM", "test_ticker_redis_stream")
os.environ.setdefault("EVENT_STREAM", "test_event_redis_stream")
os.environ.setdefault("AWS_BUCKET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_BUCKET_SECRET", "test")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("EVENTS_KEY", "test/events.json")
os.environ.setdefault("NOMIC_API_KEY", "test")
