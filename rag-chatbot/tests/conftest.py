"""
conftest.py

Injects mock environment variables at module load time, before pytest begins
collecting and importing test modules.

This prevents pydantic_settings from raising a ValidationError when EnvConfig()
is instantiated at import time in app/core/config.py.
"""

import os

os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault("LANGSMITH_ENDPOINT", "http://mock-endpoint")
os.environ.setdefault("LANGSMITH_API_KEY", "mock-api-key")
os.environ.setdefault("LANGSMITH_PROJECT", "mock-proj")
os.environ.setdefault("LLM_PROVIDER", "gemini")
os.environ.setdefault("LARGE_LANGUAGE_MODEL", "mock-model")
os.environ.setdefault("MAX_COMPLETION_TOKEN", "100")
os.environ.setdefault("TEMPERATURE", "0.5")
os.environ.setdefault("LLM_API_KEY", "mock-key")
os.environ.setdefault("QDRANT_RETRIEVAL_QUERY_URL", "http://mock")
os.environ.setdefault("ORDER_DETAILS_QUERY_URL", "http://mock")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "mock")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "mock")
os.environ.setdefault("AWS_S3_BUCKET_NAME", "mock")
os.environ.setdefault("AWS_S3_FILE_NAME", "mock")
os.environ.setdefault("POSTGRES_USER", "mock")
os.environ.setdefault("POSTGRES_PASSWORD", "mock")
os.environ.setdefault("POSTGRES_DB", "mock")
os.environ.setdefault("POSTGRES_HOST", "mock")
os.environ.setdefault("REDIS_HOST", "mock")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "mock")
os.environ.setdefault("SSL_MODE", "true")
