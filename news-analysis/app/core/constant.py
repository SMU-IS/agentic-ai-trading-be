from enum import Enum


class APIPath(str, Enum):
    HEALTH_CHECK = "/healthcheck"
    PREPROCESS = "/preprocess"


class LLMProviders(str, Enum):
    OLLAMA = "ollama"


class StorageProviders(str, Enum):
    QDRANT_OLLAMA = "qdrant_ollama"
