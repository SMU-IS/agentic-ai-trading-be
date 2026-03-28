from enum import Enum


class APIPath(str, Enum):
    VECTORISE = "/vectorise"
    NEWS = "/news"
    QUERY = "/query"
    QUERY_TICKER_EVENTS = "/ticker-events"


class StorageProviders(str, Enum):
    QDRANT_OLLAMA = "qdrant_ollama"
    QDRANT_GEMINI = "qdrant_gemini"
    QDRANT_NOMIC = "qdrant_nomic"
