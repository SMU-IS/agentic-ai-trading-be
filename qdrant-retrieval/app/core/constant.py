from enum import Enum


class APIPath(str, Enum):
    HEALTH_CHECK = "/healthcheck"
    QUERY = "/query"
    QUERY_TICKER_EVENTS = "/query-ticker-events"


class StorageProviders(str, Enum):
    QDRANT_OLLAMA = "qdrant_ollama"
    QDRANT_GEMINI = "qdrant_gemini"
