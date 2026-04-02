import os
import sys
from unittest.mock import MagicMock

# Mock heavy packages that either conflict with pydantic v2 (spacy) or are not
# installed locally (boto3, yfinance, langchain_groq). This lets both the worker
# tests and the service tests import cleanly without real ML dependencies.
for mod in [
    "spacy",
    "boto3",
    "yfinance",
    "langchain_groq",
    "langchain_core",
    "langchain_core.output_parsers",
    "langchain_core.prompts",
    "langchain_core.language_models",
    "app.scripts.aws_bucket_access",
]:
    sys.modules.setdefault(mod, MagicMock())

# Set required env vars before any app module is imported.
# conftest.py is loaded by pytest before test modules are collected.
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "")
os.environ.setdefault("TICKER_STREAM", "test_ticker_redis_stream")
os.environ.setdefault("PREPROC_STREAM", "test_preproc_redis_stream")

# AWS — dummy values so Pydantic validation passes during test collection
os.environ.setdefault("AWS_BUCKET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_BUCKET_SECRET", "test")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("CLEANED_KEY", "test/cleaned.json")
os.environ.setdefault("ALIAS_KEY", "test/alias.json")
os.environ.setdefault("EVENTS_KEY", "test/events.json")

