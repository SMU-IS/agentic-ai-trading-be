import sys
from unittest.mock import MagicMock

for mod in [
    "langchain_google_genai",
    "langchain_ollama",
    "langchain_nomic",
    "langchain_qdrant",
    "nomic",
    "asyncpg",
]:
    sys.modules.setdefault(mod, MagicMock())

import os

# Set all required env vars before any app module is imported.
os.environ.setdefault("LLM_PROVIDER", "nomic")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("NOMIC_API_KEY", "test-nomic-key")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("STORAGE_PROVIDER", "qdrant_nomic")
os.environ.setdefault("QDRANT_API_KEY", "test-qdrant-key")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "")
os.environ.setdefault("SENTIMENT_STREAM", "test_sentiment_stream")
os.environ.setdefault("AGGREGATOR_STREAM", "test_aggregator_stream")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("TEXT_EMBEDDING_MODEL", "nomic-embed-text-v1.5")
