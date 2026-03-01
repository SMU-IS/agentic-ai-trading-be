import os

# Set required env vars before any app module is imported.
# conftest.py is loaded by pytest before test modules are collected.
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "")
os.environ.setdefault("SENTIMENT_STREAM", "sentiment_stream")
os.environ.setdefault("EVENT_STREAM", "event_stream")
os.environ.setdefault("LARGE_LANGUAGE_MODEL_LLAMA_LOCAL", "llama3:8b")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("GROQ_API_KEY", "gsk_test_key_for_unit_tests_only")
os.environ.setdefault("LARGE_LANGUAGE_MODEL_LLAMA", "llama-3.3-70b-versatile")
