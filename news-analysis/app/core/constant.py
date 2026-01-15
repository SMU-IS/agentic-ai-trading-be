from enum import Enum


class APIPath(str, Enum):
    PREPROCESS = "/preprocess"


class LLMProviders(str, Enum):
    OLLAMA = "ollama"


class StorageProviders(str, Enum):
    QDRANT_OLLAMA = "qdrant_ollama"
